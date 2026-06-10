"""GDP Agent 基础配置节点。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.gdp.agent.middlewares.business_guardrail import GDPToolApprovalContext
from app.gdp.agent.middlewares.idempotency import find_successful_infra_config_step
from app.gdp.agent.nodes.events import emit_waiting_user_event
from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.infra_config_tools import (
    resolve_infra_basis,
    upsert_datasource_from_agent,
    upsert_environment_from_agent,
    upsert_service_endpoint_from_agent,
    upsert_system_from_agent,
)
from app.gdp.agent.tools.registry import assert_gdp_registered_tool_allowed
from app.gdp.datagen.config.base.models import DatasourceConfig, EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_infra_config_node(
    *,
    task_service: DatagenTaskService,
    base_repository: BaseConfigRepository,
):
    """构造系统、环境、服务端点和数据源配置节点。"""

    async def infra_config(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        user_inputs = state.get("user_inputs") or {}
        infra_payload = _extract_infra_payload(user_inputs)
        if infra_payload is None:
            source_hint = _extract_source_hint(user_inputs)
            basis = await resolve_infra_basis(
                base_repository,
                query=task_run.userIntent,
                env_code=task_run.envCode,
                sys_code=source_hint.get("sysCode"),
                datasource_code=source_hint.get("datasourceCode"),
                resource_type=source_hint.get("resourceType") or "HTTP",
            )
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.INFRA_CONFIG.value,
                "resumePhase": DatagenTaskPhase.INFRA_CONFIG.value,
                "questionType": "INFRA_CONFIG_REQUIRED",
                "question": "Source 配置依赖的基础配置不完整，请补充系统、环境、服务端点或数据源信息。",
                "details": {
                    "goal": task_run.userIntent,
                    "envCode": task_run.envCode,
                    "basis": basis,
                    "expectedPayload": {
                        "infra": {
                            "system": "可选 SysConfig",
                            "environment": "可选 EnvironmentConfig",
                            "serviceEndpoint": "HTTP Source 需要的 ServiceEndpointConfig",
                            "datasource": "SQL Source 需要的 DatasourceConfig",
                        }
                    },
                },
            }
            await task_service.record_task_step(
                task_run_id,
                phase=DatagenTaskPhase.INFRA_CONFIG,
                step_type=DatagenTaskStepType.CONFIG_INFRA,
                goal="解析并补齐 Source 依赖的基础配置。",
                status=DatagenTaskStepStatus.WAITING_USER,
                selected_resource={"missingFields": basis["missingFields"]},
                output={"basis": basis},
            )
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="基础配置不完整，等待用户补充。")
            emit_waiting_user_event(pending, message="基础配置不完整，等待用户补充。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "infraConfigRequired": True,
                    "infraBasis": basis,
                },
            }

        reused_step = find_successful_infra_config_step(
            await task_service.list_steps(task_run_id),
            infra_payload=infra_payload,
        )
        if reused_step:
            output = reused_step.output or {}
            saved = output.get("saved") if isinstance(output.get("saved"), dict) else {}
            await task_service.move_to_phase(
                task_run_id,
                status=DatagenTaskStatus.RUNNING,
                phase=DatagenTaskPhase.SOURCE_CONFIG,
                event_type="INFRA_CONFIG_REUSED",
                message="已复用本任务内成功保存过的基础配置，回到 Source 配置分支继续处理。",
                payload={
                    "taskStepId": reused_step.taskStepId,
                    "resourceTypes": sorted(saved),
                    "idempotentReuse": True,
                },
            )
            return {
                "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "decision_context": {
                    "lastSceneResult": None,
                    "infraConfigResult": {
                        "success": True,
                        "saved": sorted(saved),
                        "idempotentReuse": True,
                    },
                },
                "last_result_ref": {
                    "ref_type": "INFRA_CONFIG",
                    "task_step_id": reused_step.taskStepId,
                    "summary": {
                        "success": True,
                        "resourceTypes": sorted(saved),
                        "idempotentReuse": True,
                    },
                },
            }

        try:
            saved = await _upsert_infra(base_repository, infra_payload)
        except ValidationError as exc:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.INFRA_CONFIG.value,
                "resumePhase": DatagenTaskPhase.INFRA_CONFIG.value,
                "questionType": "INFRA_CONFIG_INVALID",
                "question": "基础配置结构不完整或字段类型不正确，请修正后继续。",
                "details": {"errors": exc.errors(), "received": infra_payload},
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="基础配置校验失败，等待用户修正。")
            emit_waiting_user_event(pending, message="基础配置校验失败，等待用户修正。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "infraConfigInvalid": True,
                    "infraConfigErrors": exc.errors(),
                },
            }

        await task_service.record_task_step(
            task_run_id,
            phase=DatagenTaskPhase.INFRA_CONFIG,
            step_type=DatagenTaskStepType.CONFIG_INFRA,
            goal="保存系统、环境、服务端点或数据源基础配置。",
            status=DatagenTaskStepStatus.SUCCESS,
            selected_resource={"resourceTypes": sorted(saved)},
            input_binding=infra_payload,
            output={"saved": saved},
        )
        await task_service.move_to_phase(
            task_run_id,
            status=DatagenTaskStatus.RUNNING,
            phase=DatagenTaskPhase.SOURCE_CONFIG,
            event_type="INFRA_CONFIG_SAVED",
            message="已保存基础配置，回到 Source 配置分支继续处理。",
            payload={"saved": saved},
        )
        return {
            "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
            "decision_context": {
                "lastSceneResult": None,
                "infraConfigResult": {"success": True, "saved": sorted(saved)},
            },
            "last_result_ref": {
                "ref_type": "INFRA_CONFIG",
                "summary": {"success": True, "resourceTypes": sorted(saved)},
            },
        }

    return infra_config


def _extract_infra_payload(user_inputs: dict[str, Any]) -> dict[str, Any] | None:
    infra = user_inputs.get("infra") or user_inputs.get("infraConfig")
    if isinstance(infra, dict):
        return infra
    keys = {"system", "environment", "serviceEndpoint", "datasource"}
    if any(isinstance(user_inputs.get(key), dict) for key in keys):
        return {key: user_inputs[key] for key in keys if isinstance(user_inputs.get(key), dict)}
    return None


def _extract_source_hint(user_inputs: dict[str, Any]) -> dict[str, str | None]:
    source_payload = user_inputs.get("source") or user_inputs.get("sourceConfig") or {}
    if not isinstance(source_payload, dict):
        source_payload = {}
    config = source_payload.get("config") if isinstance(source_payload.get("config"), dict) else {}
    http_source = user_inputs.get("httpSource") or user_inputs.get("http_source")
    sql_source = user_inputs.get("sqlSource") or user_inputs.get("sql_source")
    if isinstance(http_source, dict):
        config = http_source
        source_type = "HTTP"
    elif isinstance(sql_source, dict):
        config = sql_source
        source_type = "SQL"
    else:
        source_type = str(source_payload.get("sourceType") or user_inputs.get("sourceType") or "HTTP").upper()
    return {
        "sysCode": _optional_str(config.get("sysCode")),
        "datasourceCode": _optional_str(config.get("datasourceCode")),
        "resourceType": source_type,
    }


async def _upsert_infra(base_repository: BaseConfigRepository, payload: dict[str, Any]) -> dict[str, Any]:
    saved: dict[str, Any] = {}
    system = payload.get("system")
    if isinstance(system, dict):
        config = SysConfig.model_validate(system)
        _assert_infra_config_allowed("upsert_system_from_agent", config)
        saved["system"] = (
            await upsert_system_from_agent(base_repository, config=config)
        )["system"]

    environment = payload.get("environment")
    if isinstance(environment, dict):
        config = EnvironmentConfig.model_validate(environment)
        _assert_infra_config_allowed("upsert_environment_from_agent", config)
        saved["environment"] = (
            await upsert_environment_from_agent(base_repository, config=config)
        )["environment"]

    service_endpoint = payload.get("serviceEndpoint")
    if isinstance(service_endpoint, dict):
        config = ServiceEndpointConfig.model_validate(service_endpoint)
        _assert_infra_config_allowed("upsert_service_endpoint_from_agent", config)
        saved["serviceEndpoint"] = (
            await upsert_service_endpoint_from_agent(
                base_repository,
                config=config,
            )
        )["serviceEndpoint"]

    datasource = payload.get("datasource")
    if isinstance(datasource, dict):
        config = DatasourceConfig.model_validate(datasource)
        _assert_infra_config_allowed("upsert_datasource_from_agent", config)
        saved["datasource"] = (
            await upsert_datasource_from_agent(base_repository, config=config)
        )["datasource"]

    if not saved:
        raise ValidationError.from_exception_data(
            "InfraConfigPayload",
            [
                {
                    "type": "value_error",
                    "loc": ("infra",),
                    "msg": "infra 至少需要包含 system、environment、serviceEndpoint 或 datasource 之一。",
                    "input": payload,
                    "ctx": {"error": ValueError("infra 至少需要包含一项基础配置。")},
                }
            ],
        )
    return saved


def _assert_infra_config_allowed(tool_name: str, config: SysConfig | EnvironmentConfig | ServiceEndpointConfig | DatasourceConfig) -> None:
    assert_gdp_registered_tool_allowed(
        tool_name,
        {"config": config},
        GDPToolApprovalContext(
            allowConfigWrite=True,
            reason="用户已提交基础配置 payload，允许保存配置。",
        ),
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None and str(value).strip() else None
