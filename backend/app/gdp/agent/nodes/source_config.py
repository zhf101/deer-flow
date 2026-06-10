"""GDP Agent Source 配置节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from app.gdp.agent.llm.decision import draft_gdp_source_config
from app.gdp.agent.llm.events import llm_decision_payload, llm_failure_payload
from app.gdp.agent.llm.schemas import GDPSourceConfigDraftDecision
from app.gdp.agent.middlewares.business_guardrail import GDPToolApprovalContext
from app.gdp.agent.middlewares.idempotency import find_successful_source_config_step
from app.gdp.agent.nodes.events import emit_waiting_user_event
from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.infra_config_tools import resolve_infra_basis
from app.gdp.agent.tools.registry import assert_gdp_registered_tool_allowed
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
from deerflow.config.app_config import AppConfig


def build_source_config_node(
    *,
    task_service: DatagenTaskService,
    base_repository: BaseConfigRepository,
    http_source_service: HttpSourceService,
    sql_source_service: SqlSourceService,
    app_config: AppConfig | None = None,
    llm_enabled: bool = False,
    llm_model: Any | None = None,
):
    """构造 HTTP/SQL Source 配置节点。"""

    async def source_config(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        user_inputs = state.get("user_inputs") or {}
        source_payload = _extract_source_payload(user_inputs)
        if source_payload is None:
            visible_variables = [_visible_variable_summary(item) for item in task_run.visibleVariables]
            infra_summary = await _build_source_config_infra_summary(
                base_repository,
                goal=task_run.userIntent,
                env_code=task_run.envCode,
                user_inputs=user_inputs,
            )
            await task_service.record_event(
                task_run_id,
                event_type="SOURCE_CONFIG_INFRA_BASIS_RESOLVED",
                phase=DatagenTaskPhase.SOURCE_CONFIG,
                message="已在生成 Source 草稿前读取基础配置摘要。",
                payload=infra_summary,
            )
            llm_decision, llm_state_update = await _try_draft_source_config_with_llm(
                task_service,
                task_run_id,
                goal=task_run.userIntent,
                env_code=task_run.envCode,
                user_inputs=user_inputs,
                visible_variables=visible_variables,
                context_summary=state.get("context_summary") or {},
                infra_summary=infra_summary,
                normalized_goal=state.get("normalized_goal") or task_run.normalizedGoal,
                config=config,
                app_config=app_config,
                llm_enabled=llm_enabled,
                llm_model=llm_model,
            )
            details = _source_config_required_details(task_run, llm_decision, infra_summary)
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "resumePhase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "questionType": "SOURCE_CONFIG_REQUIRED",
                "question": "当前缺少可用于生成场景的 HTTP/SQL Source，请补充接口或 SQL 配置信息。",
                "details": details,
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="缺少 Source 配置，等待用户补充。")
            emit_waiting_user_event(pending, message="缺少 Source 配置，等待用户补充。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "sourceConfigRequired": True,
                    "resourceType": "SOURCE",
                    "sourceConfigInfraSummary": _infra_context_summary(infra_summary),
                    **_llm_source_draft_context(llm_decision),
                },
                **llm_state_update,
            }

        reused_step = find_successful_source_config_step(
            await task_service.list_steps(task_run_id),
            source_payload=source_payload,
        )
        if reused_step:
            reused_result = dict(reused_step.output or {})
            await task_service.move_to_phase(
                task_run_id,
                status=DatagenTaskStatus.RUNNING,
                phase=DatagenTaskPhase.SCENE_DESIGN,
                event_type="SOURCE_CONFIG_REUSED",
                message="已复用本任务内成功保存过的 Source 配置，回到场景设计分支继续生成场景。",
                payload={
                    "taskStepId": reused_step.taskStepId,
                    "source": _source_step_resource(source_payload, result=reused_result),
                    "idempotentReuse": True,
                },
            )
            return {
                "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
                "decision_context": {
                    "lastSceneResult": None,
                    "sourceConfigResult": {
                        **_source_result_summary(reused_result),
                        "idempotentReuse": True,
                    },
                },
                "last_result_ref": {
                    **_source_result_ref(source_payload, reused_result),
                    "task_step_id": reused_step.taskStepId,
                },
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
            emit_waiting_user_event(pending, message="Source 配置校验失败，等待用户修正。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "sourceConfigInvalid": True,
                    "sourceConfigErrors": exc.errors(),
                },
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
                "decision_context": {
                    "lastSceneResult": None,
                    "sourceConfigResult": _source_result_summary(result),
                    "sourceConfigNeedsInfra": True,
                },
                "last_result_ref": _source_result_ref(source_payload, result),
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
            "decision_context": {
                "lastSceneResult": None,
                "sourceConfigResult": _source_result_summary(result),
            },
            "last_result_ref": _source_result_ref(source_payload, result),
        }

    return source_config


async def _build_source_config_infra_summary(
    base_repository: BaseConfigRepository,
    *,
    goal: str,
    env_code: str,
    user_inputs: dict[str, Any],
) -> dict[str, Any]:
    """在模型生成 Source 草稿前汇总基础配置现状和缺口。"""

    hints = _extract_source_config_infra_hints(user_inputs)
    systems = await base_repository.list_systems()
    environments = await base_repository.list_environments()
    endpoints = await base_repository.list_service_endpoints(env_code=env_code, sys_code=hints.get("sysCode"))
    datasources = await base_repository.list_datasources(env_code=env_code, sys_code=hints.get("sysCode"))
    http_basis = await resolve_infra_basis(
        base_repository,
        query=goal,
        env_code=env_code,
        sys_code=hints.get("sysCode"),
        resource_type="HTTP",
    )
    sql_basis = await resolve_infra_basis(
        base_repository,
        query=goal,
        env_code=env_code,
        sys_code=hints.get("sysCode"),
        datasource_code=hints.get("datasourceCode"),
        resource_type="SQL",
    )
    sanitized_http_basis = _sanitize_infra_basis(http_basis)
    sanitized_sql_basis = _sanitize_infra_basis(sql_basis)
    return {
        "envCode": env_code,
        "hints": hints,
        "availableSystems": [_system_summary(item) for item in systems],
        "availableEnvironments": [_environment_summary(item) for item in environments],
        "availableServiceEndpoints": [_service_endpoint_summary(item) for item in endpoints],
        "availableDatasources": [_datasource_summary(item) for item in datasources],
        "httpReadiness": sanitized_http_basis,
        "sqlReadiness": sanitized_sql_basis,
        "missingInfraFields": _merge_infra_missing_fields(sanitized_http_basis, sanitized_sql_basis),
        "guidance": {
            "http": "HTTP Source 草稿应优先引用已有 sysCode；若 serviceEndpoint 缺失，需要先补服务端点。",
            "sql": "SQL Source 草稿应优先引用已有 sysCode 和 datasourceCode；若 datasource 缺失，需要先补数据源。",
        },
    }


async def _try_draft_source_config_with_llm(
    task_service: DatagenTaskService,
    task_run_id: str,
    *,
    goal: str,
    env_code: str,
    user_inputs: dict[str, Any],
    visible_variables: list[dict[str, Any]],
    context_summary: dict[str, Any],
    infra_summary: dict[str, Any],
    normalized_goal: dict[str, Any],
    config: RunnableConfig | None,
    app_config: AppConfig | None,
    llm_enabled: bool,
    llm_model: Any | None,
) -> tuple[GDPSourceConfigDraftDecision | None, dict[str, Any]]:
    """调用模型生成 Source 配置草稿，失败时保留原追问流程。"""

    if not llm_enabled:
        return None, {}
    try:
        decision = await draft_gdp_source_config(
            goal=goal,
            env_code=env_code,
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            context_summary=context_summary,
            infra_summary=infra_summary,
            normalized_goal=normalized_goal,
            config=config,
            app_config=app_config,
            model=llm_model,
        )
        _validate_source_config_draft_decision(decision)
        event = await task_service.record_event(
            task_run_id,
            event_type="LLM_SOURCE_CONFIG_DRAFTED",
            phase=DatagenTaskPhase.SOURCE_CONFIG,
            message="模型已生成 Source 配置草稿或追问信息。",
            payload=llm_decision_payload(decision),
        )
        return decision, _source_draft_llm_state_update(decision, event.eventId, event.eventType)
    except Exception as exc:
        event = await task_service.record_event(
            task_run_id,
            event_type="LLM_SOURCE_CONFIG_DRAFT_FAILED",
            phase=DatagenTaskPhase.SOURCE_CONFIG,
            message="模型生成 Source 配置草稿失败，已回退到普通追问。",
            payload=llm_failure_payload(exc),
        )
        return None, {
            "last_llm_decision": {
                "decisionType": "source_config_draft",
                "decisionSource": "fallback_rule",
                "errorType": type(exc).__name__,
            },
            "llm_decision_refs": [
                {
                    "eventId": event.eventId,
                    "eventType": event.eventType,
                    "decisionType": "source_config_draft",
                }
            ],
        }


def _validate_source_config_draft_decision(decision: GDPSourceConfigDraftDecision) -> None:
    """校验模型草稿的基本形态，具体字段仍由后续 Pydantic 保存链校验。"""

    if decision.decision != "DRAFT_SOURCE":
        return
    if decision.sourceType not in {"HTTP", "SQL"}:
        raise ValueError("模型 Source 配置草稿缺少有效 sourceType。")
    if not decision.configDraft:
        raise ValueError("模型 Source 配置草稿缺少 configDraft。")


def _source_config_required_details(
    task_run: Any,
    llm_decision: GDPSourceConfigDraftDecision | None,
    infra_summary: dict[str, Any],
) -> dict[str, Any]:
    """构造缺 Source 时给前后端展示的追问详情。"""

    details: dict[str, Any] = {
        "goal": task_run.userIntent,
        "envCode": task_run.envCode,
        "infraSummary": infra_summary,
        "infraMissingFields": infra_summary.get("missingInfraFields") or [],
        "expectedPayload": {
            "sourceType": "HTTP 或 SQL",
            "config": "HttpSourceConfig 或 SqlSourceConfig 结构",
        },
    }
    if llm_decision is None:
        return details
    details["llmDraft"] = llm_decision.model_dump(mode="json")
    if llm_decision.decision == "DRAFT_SOURCE":
        details["suggestedPayload"] = {
            "sourceType": llm_decision.sourceType,
            "config": llm_decision.configDraft,
        }
    if llm_decision.missingInformation:
        details["missingInformation"] = llm_decision.missingInformation
    return details


def _source_draft_llm_state_update(
    decision: GDPSourceConfigDraftDecision,
    event_id: str,
    event_type: str,
) -> dict[str, Any]:
    """生成 Source 配置草稿模型决策的 checkpoint 摘要。"""

    return {
        "last_llm_decision": {
            "decisionType": "source_config_draft",
            "decision": decision.decision,
            "sourceType": decision.sourceType,
            "confidence": decision.confidence,
            "reason": decision.reason,
        },
        "llm_decision_refs": [
            {
                "eventId": event_id,
                "eventType": event_type,
                "decisionType": "source_config_draft",
            }
        ],
    }


def _llm_source_draft_context(decision: GDPSourceConfigDraftDecision | None) -> dict[str, Any]:
    """把模型 Source 配置草稿写入轻量决策上下文。"""

    if decision is None:
        return {}
    return {"llmSourceConfigDraft": decision.model_dump(mode="json")}


def _infra_context_summary(infra_summary: dict[str, Any]) -> dict[str, Any]:
    """生成 checkpoint 中的轻量基础配置摘要。"""

    return {
        "envCode": infra_summary.get("envCode"),
        "missingInfraFields": infra_summary.get("missingInfraFields") or [],
        "httpReady": (infra_summary.get("httpReadiness") or {}).get("ready"),
        "sqlReady": (infra_summary.get("sqlReadiness") or {}).get("ready"),
        "availableSystemCodes": [item.get("sysCode") for item in infra_summary.get("availableSystems") or []],
        "availableDatasourceCodes": [item.get("datasourceCode") for item in infra_summary.get("availableDatasources") or []],
    }


def _extract_source_config_infra_hints(user_inputs: dict[str, Any]) -> dict[str, str | None]:
    """从用户输入中提取 Source 草稿前可用的基础配置提示。"""

    config = user_inputs.get("config") if isinstance(user_inputs.get("config"), dict) else {}
    source = user_inputs.get("source") or user_inputs.get("sourceConfig") or {}
    if isinstance(source, dict) and isinstance(source.get("config"), dict):
        config = {**config, **source["config"]}
    for key in ("httpSource", "http_source", "sqlSource", "sql_source"):
        if isinstance(user_inputs.get(key), dict):
            config = {**config, **user_inputs[key]}
    source_type = user_inputs.get("sourceType")
    if not source_type and isinstance(source, dict):
        source_type = source.get("sourceType")
    return {
        "sourceType": _optional_str(source_type),
        "sysCode": _optional_str(user_inputs.get("sysCode") or config.get("sysCode")),
        "datasourceCode": _optional_str(user_inputs.get("datasourceCode") or config.get("datasourceCode")),
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sanitize_infra_basis(basis: dict[str, Any]) -> dict[str, Any]:
    """去除基础配置中的敏感连接信息，仅保留模型决策需要的事实。"""

    return {
        "matchedSystems": [
            _system_dict_summary(item)
            for item in basis.get("matchedSystems") or []
            if isinstance(item, dict)
        ],
        "matchedEnvironments": [
            _environment_dict_summary(item)
            for item in basis.get("matchedEnvironments") or []
            if isinstance(item, dict)
        ],
        "matchedServiceEndpoints": [
            _service_endpoint_dict_summary(item)
            for item in basis.get("matchedServiceEndpoints") or []
            if isinstance(item, dict)
        ],
        "matchedDatasources": [
            _datasource_dict_summary(item)
            for item in basis.get("matchedDatasources") or []
            if isinstance(item, dict)
        ],
        "confidence": basis.get("confidence"),
        "missingFields": basis.get("missingFields") or [],
        "ready": bool(basis.get("ready")),
    }


def _merge_infra_missing_fields(
    http_basis: dict[str, Any],
    sql_basis: dict[str, Any],
) -> list[str]:
    """合并 HTTP/SQL 两类 Source 的基础配置缺口。"""

    result: list[str] = []
    for field in http_basis.get("missingFields") or []:
        _append_missing_field(result, str(field), prefix="HTTP")
    for field in sql_basis.get("missingFields") or []:
        _append_missing_field(result, str(field), prefix="SQL")
    return result


def _append_missing_field(result: list[str], field: str, *, prefix: str) -> None:
    key = field if field in {"system", "environment"} else f"{prefix}.{field}"
    if key not in result:
        result.append(key)


def _system_summary(item: Any) -> dict[str, Any]:
    return _system_dict_summary(item.model_dump(mode="json"))


def _environment_summary(item: Any) -> dict[str, Any]:
    return _environment_dict_summary(item.model_dump(mode="json"))


def _service_endpoint_summary(item: Any) -> dict[str, Any]:
    return _service_endpoint_dict_summary(item.model_dump(mode="json"))


def _datasource_summary(item: Any) -> dict[str, Any]:
    return _datasource_dict_summary(item.model_dump(mode="json"))


def _system_dict_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sysCode": item.get("sysCode"),
        "sysName": item.get("sysName"),
        "status": item.get("status"),
        "remark": item.get("remark"),
        "score": item.get("score"),
        "reasons": item.get("reasons") or [],
    }


def _environment_dict_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "envCode": item.get("envCode"),
        "envName": item.get("envName"),
        "status": item.get("status"),
        "remark": item.get("remark"),
    }


def _service_endpoint_dict_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "envCode": item.get("envCode"),
        "sysCode": item.get("sysCode"),
        "status": item.get("status"),
        "configured": bool(item.get("baseUrl")),
    }


def _datasource_dict_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "envCode": item.get("envCode"),
        "sysCode": item.get("sysCode"),
        "datasourceCode": item.get("datasourceCode"),
        "datasourceName": item.get("datasourceName"),
        "dbType": item.get("dbType"),
        "databaseName": item.get("databaseName"),
        "status": item.get("status"),
    }


def _visible_variable_summary(variable: Any) -> dict[str, Any]:
    return {
        "name": variable.name,
        "semanticType": variable.semanticType,
        "label": variable.label,
        "valueSchema": variable.valueSchema,
        "valuePreview": None if variable.sensitive else variable.valuePreview,
        "valueSize": variable.valueSize.model_dump(mode="json") if variable.valueSize else None,
        "sensitive": variable.sensitive,
        "confidence": variable.confidence,
    }


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


def _source_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    basis = result.get("basis") if isinstance(result.get("basis"), dict) else {}
    return {
        "success": result.get("success"),
        "sourceCode": source.get("sourceCode"),
        "sysCode": source.get("sysCode"),
        "missingFields": result.get("missingFields") or basis.get("missingFields") or [],
    }


def _source_result_ref(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    return {
        "ref_type": f"{str(payload.get('sourceType') or 'SOURCE').upper()}_SOURCE",
        "source_code": source.get("sourceCode") or _source_step_resource(payload, result=result).get("sourceCode"),
        "summary": _source_result_summary(result),
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
        config = HttpSourceConfig.model_validate(config_payload)
        _assert_source_config_allowed("upsert_http_source_from_agent", config, payload)
        return await upsert_http_source_from_agent(
            http_source_service,
            base_repository,
            config=config,
            env_code=env_code,
        )
    if source_type == "SQL":
        config = SqlSourceConfig.model_validate(config_payload)
        _assert_source_config_allowed("upsert_sql_source_from_agent", config, payload)
        return await upsert_sql_source_from_agent(
            sql_source_service,
            base_repository,
            config=config,
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


def _assert_source_config_allowed(tool_name: str, config: HttpSourceConfig | SqlSourceConfig, payload: dict[str, Any]) -> None:
    assert_gdp_registered_tool_allowed(
        tool_name,
        {
            "config": config,
            "sourceType": payload.get("sourceType"),
        },
        GDPToolApprovalContext(
            allowConfigWrite=True,
            reason="用户已提交 Source 配置 payload，允许保存配置。",
        ),
    )
