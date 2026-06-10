"""GDP Agent 工具能力注册表。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.gdp.agent.middlewares.business_guardrail import (
    GDPToolApprovalContext,
    GDPToolGuardrailDecision,
    GDPToolGuardrailError,
    build_gdp_tool_approval_key,
    evaluate_gdp_tool_guardrail,
    wrap_gdp_tools_guardrail,
)
from app.gdp.agent.tools.infra_config_tools import build_infra_config_tools
from app.gdp.agent.tools.scene_design_tools import build_scene_design_tools
from app.gdp.agent.tools.scene_tools import build_scene_tools
from app.gdp.agent.tools.source_config_tools import build_source_config_tools
from app.gdp.agent.tools.task_tools import build_task_tools
from app.gdp.datagen.config.task.models import DatagenTaskPhase


class GDPToolSideEffectLevel(StrEnum):
    """GDP Agent 工具副作用等级。"""

    NONE = "NONE"
    CONFIG_WRITE = "CONFIG_WRITE"
    BUSINESS_WRITE = "BUSINESS_WRITE"


class GDPToolOutputTarget(StrEnum):
    """GDP Agent 工具输出治理目标。"""

    STATE = "STATE"
    TASK_STEP = "TASK_STEP"
    TASK_EVENT = "TASK_EVENT"
    VARIABLE_STACK = "VARIABLE_STACK"
    STORAGE_REF = "STORAGE_REF"


class GDPToolSpec(BaseModel):
    """GDP Agent 工具暴露和治理元数据。"""

    name: str = Field(..., min_length=1, description="工具名称，必须与 LangChain Tool 的 name 完全一致。")
    phase: list[DatagenTaskPhase] = Field(default_factory=list, description="允许暴露该工具的造数任务阶段。")
    sideEffectLevel: GDPToolSideEffectLevel = Field(..., description="工具副作用等级，用于审批、幂等和审计策略。")
    requiresApproval: bool = Field(default=False, description="是否必须经过用户或策略审批后才能执行。")
    idempotencyKeyFields: list[str] = Field(default_factory=list, description="生成幂等键时使用的入参字段路径。")
    outputTarget: GDPToolOutputTarget = Field(..., description="工具主输出应落入的业务权威位置或运行时引用类型。")
    sensitiveOutput: bool = Field(default=False, description="工具输出是否可能包含敏感值或大对象，敏感输出不得直接注入 Prompt。")


_ACTIVE_TASK_PHASES = (
    DatagenTaskPhase.INTAKE,
    DatagenTaskPhase.SCENE_FULFILLMENT,
    DatagenTaskPhase.SCENE_EXECUTING,
    DatagenTaskPhase.PROGRESS_REFLECTION,
    DatagenTaskPhase.SCENE_DESIGN,
    DatagenTaskPhase.SOURCE_CONFIG,
    DatagenTaskPhase.INFRA_CONFIG,
    DatagenTaskPhase.WAITING_USER,
)


def _spec(
    name: str,
    phase: tuple[DatagenTaskPhase, ...],
    *,
    side_effect_level: GDPToolSideEffectLevel = GDPToolSideEffectLevel.NONE,
    requires_approval: bool = False,
    idempotency_key_fields: tuple[str, ...] = (),
    output_target: GDPToolOutputTarget = GDPToolOutputTarget.STATE,
    sensitive_output: bool = False,
) -> GDPToolSpec:
    return GDPToolSpec(
        name=name,
        phase=list(phase),
        sideEffectLevel=side_effect_level,
        requiresApproval=requires_approval,
        idempotencyKeyFields=list(idempotency_key_fields),
        outputTarget=output_target,
        sensitiveOutput=sensitive_output,
    )


_TOOL_SPECS: tuple[GDPToolSpec, ...] = (
    _spec("get_datagen_task_state", _ACTIVE_TASK_PHASES),
    _spec("search_scene_contracts", (DatagenTaskPhase.SCENE_FULFILLMENT,)),
    _spec(
        "get_scene_contract",
        (DatagenTaskPhase.SCENE_FULFILLMENT, DatagenTaskPhase.SCENE_EXECUTING),
    ),
    _spec(
        "bind_scene_inputs",
        (DatagenTaskPhase.SCENE_FULFILLMENT, DatagenTaskPhase.SCENE_EXECUTING),
    ),
    _spec(
        "run_datagen_scene_for_task",
        (DatagenTaskPhase.SCENE_EXECUTING,),
        side_effect_level=GDPToolSideEffectLevel.BUSINESS_WRITE,
        requires_approval=True,
        idempotency_key_fields=("task_run_id", "scene_code", "env_code", "input_params"),
        output_target=GDPToolOutputTarget.TASK_STEP,
        sensitive_output=True,
    ),
    _spec("reflect_scene_result", (DatagenTaskPhase.PROGRESS_REFLECTION,)),
    _spec("search_source_contracts", (DatagenTaskPhase.SCENE_DESIGN,)),
    _spec("compose_scene_draft_from_source", (DatagenTaskPhase.SCENE_DESIGN,)),
    _spec(
        "publish_scene_from_source",
        (DatagenTaskPhase.SCENE_DESIGN,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("task_run_id", "source_contract.sourceCode"),
        output_target=GDPToolOutputTarget.TASK_STEP,
    ),
    _spec("resolve_http_source_basis", (DatagenTaskPhase.SOURCE_CONFIG,)),
    _spec("resolve_sql_source_basis", (DatagenTaskPhase.SOURCE_CONFIG,)),
    _spec(
        "upsert_http_source_from_agent",
        (DatagenTaskPhase.SOURCE_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("config.sourceCode",),
        output_target=GDPToolOutputTarget.TASK_EVENT,
    ),
    _spec(
        "upsert_sql_source_from_agent",
        (DatagenTaskPhase.SOURCE_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("config.sourceCode",),
        output_target=GDPToolOutputTarget.TASK_EVENT,
    ),
    _spec(
        "test_http_source_from_agent",
        (DatagenTaskPhase.SOURCE_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.BUSINESS_WRITE,
        requires_approval=True,
        idempotency_key_fields=("request.sourceCode", "request.envCode", "request.inputs"),
        output_target=GDPToolOutputTarget.STORAGE_REF,
        sensitive_output=True,
    ),
    _spec(
        "test_sql_source_from_agent",
        (DatagenTaskPhase.SOURCE_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.BUSINESS_WRITE,
        requires_approval=True,
        idempotency_key_fields=("request.sourceCode", "request.envCode", "request.params"),
        output_target=GDPToolOutputTarget.STORAGE_REF,
        sensitive_output=True,
    ),
    _spec(
        "parse_sql_source_from_agent",
        (DatagenTaskPhase.SOURCE_CONFIG,),
        sensitive_output=True,
    ),
    _spec("resolve_infra_basis", (DatagenTaskPhase.INFRA_CONFIG,)),
    _spec(
        "upsert_system_from_agent",
        (DatagenTaskPhase.INFRA_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("config.sysCode",),
        output_target=GDPToolOutputTarget.TASK_EVENT,
    ),
    _spec(
        "upsert_environment_from_agent",
        (DatagenTaskPhase.INFRA_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("config.envCode",),
        output_target=GDPToolOutputTarget.TASK_EVENT,
    ),
    _spec(
        "upsert_service_endpoint_from_agent",
        (DatagenTaskPhase.INFRA_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("config.envCode", "config.sysCode"),
        output_target=GDPToolOutputTarget.TASK_EVENT,
    ),
    _spec(
        "upsert_datasource_from_agent",
        (DatagenTaskPhase.INFRA_CONFIG,),
        side_effect_level=GDPToolSideEffectLevel.CONFIG_WRITE,
        requires_approval=True,
        idempotency_key_fields=("config.envCode", "config.sysCode", "config.datasourceCode"),
        output_target=GDPToolOutputTarget.TASK_EVENT,
    ),
)


def get_gdp_tool_specs(phase: DatagenTaskPhase | str | None = None) -> list[GDPToolSpec]:
    """按阶段读取 GDP Agent 工具治理元数据。"""

    target_phase = _normalize_phase(phase)
    specs = _TOOL_SPECS if target_phase is None else tuple(item for item in _TOOL_SPECS if target_phase in item.phase)
    return [item.model_copy(deep=True) for item in specs]


def get_gdp_tools(
    services: Any,
    phase: DatagenTaskPhase | str | None = None,
    *,
    approval_context: GDPToolApprovalContext | dict[str, Any] | None = None,
    guardrails_enabled: bool = True,
) -> list[BaseTool]:
    """按阶段构造 GDP Agent 可暴露给模型的 LangChain 工具。"""

    specs = get_gdp_tool_specs(phase)
    specs_by_name = {item.name: item for item in specs}
    allowed_names = set(specs_by_name)
    tools = [
        *build_task_tools(services.task_service, getattr(services, "subtask_service", None)),
        *build_scene_tools(
            catalog_service=services.catalog_service,
            task_service=services.task_service,
            scene_service=services.scene_service,
        ),
        *build_scene_design_tools(
            catalog_service=services.catalog_service,
            task_service=services.task_service,
            scene_service=services.scene_service,
            http_source_repository=services.http_source_repository,
            sql_source_repository=services.sql_source_repository,
        ),
        *build_source_config_tools(
            base_repository=services.base_repository,
            http_source_service=services.http_source_service,
            sql_source_service=services.sql_source_service,
            sql_execution_service=services.sql_execution_service,
        ),
        *build_infra_config_tools(services.base_repository),
    ]
    selected_tools = [tool for tool in tools if tool.name in allowed_names]
    if not guardrails_enabled:
        return selected_tools
    return wrap_gdp_tools_guardrail(selected_tools, specs_by_name, approval_context)


def _normalize_phase(phase: DatagenTaskPhase | str | None) -> DatagenTaskPhase | None:
    if phase is None or isinstance(phase, DatagenTaskPhase):
        return phase
    return DatagenTaskPhase(str(phase))
