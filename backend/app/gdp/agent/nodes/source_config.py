"""GDP Agent Source 配置节点。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.source_config_tools import upsert_http_source_from_agent, upsert_sql_source_from_agent
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_source_config_node(
    *,
    task_service: DatagenTaskService,
    base_repository: BaseConfigRepository,
    http_source_service: HttpSourceService,
    sql_source_service: SqlSourceService,
):
    """构造 HTTP/SQL Source 配置节点。"""

    async def source_config(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        user_inputs = state.get("user_inputs") or {}
        source_payload = _extract_source_payload(user_inputs)
        if source_payload is None:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "resumePhase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "questionType": "SOURCE_CONFIG_REQUIRED",
                "question": "当前缺少可用于生成场景的 HTTP/SQL Source，请补充接口或 SQL 配置信息。",
                "details": {
                    "goal": task_run.userIntent,
                    "envCode": task_run.envCode,
                    "expectedPayload": {
                        "sourceType": "HTTP 或 SQL",
                        "config": "HttpSourceConfig 或 SqlSourceConfig 结构",
                    },
                },
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="缺少 Source 配置，等待用户补充。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "last_tool_result": {"resourceMissing": True, "resourceType": "SOURCE"},
            }

        try:
            result = await _upsert_source(
                source_payload,
                env_code=task_run.envCode,
                base_repository=base_repository,
                http_source_service=http_source_service,
                sql_source_service=sql_source_service,
            )
        except ValidationError as exc:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "resumePhase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "questionType": "SOURCE_CONFIG_INVALID",
                "question": "Source 配置结构不完整或字段类型不正确，请修正后继续。",
                "details": {"errors": exc.errors(), "received": source_payload},
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="Source 配置校验失败，等待用户修正。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "last_tool_result": {"sourceConfigInvalid": True, "errors": exc.errors()},
            }

        if not result.get("success"):
            await task_service.record_task_step(
                task_run_id,
                phase=DatagenTaskPhase.SOURCE_CONFIG,
                step_type=_source_step_type(source_payload),
                goal="保存 Source 配置前检查基础配置依赖。",
                status=DatagenTaskStepStatus.WAITING_USER,
                selected_resource=_source_step_resource(source_payload),
                input_binding=source_payload,
                output=result,
            )
            await task_service.move_to_phase(
                task_run_id,
                status=DatagenTaskStatus.RUNNING,
                phase=DatagenTaskPhase.INFRA_CONFIG,
                event_type="SOURCE_INFRA_MISSING",
                message="Source 配置依赖的基础配置不完整，需要进入基础配置分支。",
                payload=result,
            )
            return {
                "current_phase": DatagenTaskPhase.INFRA_CONFIG.value,
                "last_tool_result": {"sourceConfigResult": result},
            }

        await task_service.record_task_step(
            task_run_id,
            phase=DatagenTaskPhase.SOURCE_CONFIG,
            step_type=_source_step_type(source_payload),
            goal="保存 HTTP/SQL Source 配置。",
            status=DatagenTaskStepStatus.SUCCESS,
            selected_resource=_source_step_resource(source_payload, result=result),
            input_binding=source_payload,
            output=result,
        )
        await task_service.move_to_phase(
            task_run_id,
            status=DatagenTaskStatus.RUNNING,
            phase=DatagenTaskPhase.SCENE_DESIGN,
            event_type="SOURCE_CONFIG_SAVED",
            message="已保存 Source 配置，回到场景设计分支继续生成场景。",
            payload=result,
        )
        return {
            "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
            "last_tool_result": {"sourceConfigResult": result},
        }

    return source_config


def _source_step_type(payload: dict[str, Any]) -> DatagenTaskStepType:
    source_type = str(payload.get("sourceType") or "").upper()
    if source_type == "SQL":
        return DatagenTaskStepType.CONFIG_SQL_SOURCE
    return DatagenTaskStepType.CONFIG_HTTP_SOURCE


def _source_step_resource(payload: dict[str, Any], *, result: dict[str, Any] | None = None) -> dict[str, Any]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    saved_source = (result or {}).get("source") if isinstance((result or {}).get("source"), dict) else {}
    return {
        "sourceType": str(payload.get("sourceType") or "").upper(),
        "sourceCode": saved_source.get("sourceCode") or config.get("sourceCode"),
        "sysCode": saved_source.get("sysCode") or config.get("sysCode"),
    }


def _extract_source_payload(user_inputs: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("source", "sourceConfig"):
        value = user_inputs.get(key)
        if isinstance(value, dict):
            return value

    http_source = user_inputs.get("httpSource") or user_inputs.get("http_source")
    if isinstance(http_source, dict):
        return {"sourceType": "HTTP", "config": http_source}

    sql_source = user_inputs.get("sqlSource") or user_inputs.get("sql_source")
    if isinstance(sql_source, dict):
        return {"sourceType": "SQL", "config": sql_source}

    source_type = str(user_inputs.get("sourceType") or "").upper()
    config = user_inputs.get("config")
    if source_type in {"HTTP", "SQL"} and isinstance(config, dict):
        return {"sourceType": source_type, "config": config}
    return None


async def _upsert_source(
    payload: dict[str, Any],
    *,
    env_code: str,
    base_repository: BaseConfigRepository,
    http_source_service: HttpSourceService,
    sql_source_service: SqlSourceService,
) -> dict[str, Any]:
    source_type = str(payload.get("sourceType") or "").upper()
    config_payload = payload.get("config")
    if source_type == "HTTP":
        return await upsert_http_source_from_agent(
            http_source_service,
            base_repository,
            config=HttpSourceConfig.model_validate(config_payload),
            env_code=env_code,
        )
    if source_type == "SQL":
        return await upsert_sql_source_from_agent(
            sql_source_service,
            base_repository,
            config=SqlSourceConfig.model_validate(config_payload),
            env_code=env_code,
        )
    raise ValidationError.from_exception_data(
        "SourceConfigPayload",
        [
            {
                "type": "value_error",
                "loc": ("sourceType",),
                "msg": "sourceType 必须是 HTTP 或 SQL。",
                "input": payload.get("sourceType"),
                "ctx": {"error": ValueError("sourceType 必须是 HTTP 或 SQL。")},
            }
        ],
    )
