"""GDP Agent 业务副作用 Guardrail 工具。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field


class GDPToolApprovalContext(BaseModel):
    """GDP Agent 工具审批上下文。"""

    approvedToolNames: list[str] = Field(default_factory=list, description="本次运行已审批通过的工具名称。")
    approvedApprovalKeys: list[str] = Field(default_factory=list, description="本次运行已审批通过的工具调用幂等键。")
    allowConfigWrite: bool = Field(default=False, description="是否允许本次运行执行配置写入类工具。")
    allowBusinessWrite: bool = Field(default=False, description="是否允许本次运行执行业务写入类工具。")
    operator: str | None = Field(default=None, description="审批或运行操作者标识，用于审计归因。")
    reason: str | None = Field(default=None, description="审批原因或策略命中说明。")


class GDPToolGuardrailDecision(BaseModel):
    """GDP Agent 工具 Guardrail 判定结果。"""

    allowed: bool = Field(..., description="是否允许执行工具。")
    toolName: str = Field(..., description="被判定的工具名称。")
    sideEffectLevel: str = Field(..., description="工具副作用等级。")
    requiresApproval: bool = Field(..., description="工具是否要求审批。")
    approvalKey: str | None = Field(default=None, description="基于工具幂等字段生成的审批键。")
    reason: str = Field(..., description="允许或拦截的原因。")


class GDPToolGuardrailError(PermissionError):
    """GDP Agent 工具调用被业务 Guardrail 拦截。"""

    def __init__(self, decision: GDPToolGuardrailDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason)


def user_submitted_config_write_context(*, source: str, operator: str | None = None) -> GDPToolApprovalContext:
    """构造"用户提交配置 payload 即视为确认保存"的标准审批上下文。

    产品策略（已拍板，见 tools/registry.py 模块文档）：配置写入类工具
    （``upsert_*_from_agent`` 等 ``CONFIG_WRITE``）在用户显式提交配置 payload 的
    场景下不要求二次审批，**提交动作本身即为确认**。所有配置写路径（主图节点、
    Agent API）必须复用本 helper 构造审批上下文，禁止各自手写
    ``allowConfigWrite=True``，避免治理口径漂移。

    Args:
        source: 放行来源说明（如 ``"source_config 节点"`` / ``"Agent API"``），用于审计归因。
        operator: 操作者标识，可为空。
    """

    return GDPToolApprovalContext(
        allowConfigWrite=True,
        operator=operator,
        reason=f"{source}：用户已提交配置 payload，按【提交即确认】策略放行配置写入。",
    )


def user_submitted_probe_context(*, source: str, operator: str | None = None) -> GDPToolApprovalContext:
    """构造"用户显式提交连通性探测请求"的标准审批上下文。

    适用于 ``test_http_source_from_agent`` / ``test_sql_source_from_agent`` 等由用户
    主动发起的业务探测（``BUSINESS_WRITE``）。与配置写同理：用户提交探测请求本身
    即为确认，统一经本 helper 放行，禁止各自手写 ``allowBusinessWrite=True``。
    注意：场景执行（``run_datagen_scene_for_task``）不适用本策略，仍走显式确认/审批键。
    """

    return GDPToolApprovalContext(
        allowBusinessWrite=True,
        operator=operator,
        reason=f"{source}：用户已显式提交业务探测请求，按【提交即确认】策略放行。",
    )


class GuardedGDPTool(BaseTool):
    """带 GDP 业务 Guardrail 的 LangChain 工具包装器。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    wrapped_tool: BaseTool = Field(..., exclude=True, description="被包装的原始 LangChain 工具。")
    gdp_tool_spec: Any = Field(..., description="工具治理元数据，来自 GDPToolSpec。")
    approval_context: GDPToolApprovalContext = Field(default_factory=GDPToolApprovalContext, description="本次工具集合的审批上下文。")

    def _run(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        tool_input = _tool_input_from_call(args, kwargs)
        decision = evaluate_gdp_tool_guardrail(self.gdp_tool_spec, tool_input, self.approval_context)
        if not decision.allowed:
            raise GDPToolGuardrailError(decision)
        return self.wrapped_tool.invoke(tool_input)

    async def _arun(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        tool_input = _tool_input_from_call(args, kwargs)
        decision = evaluate_gdp_tool_guardrail(self.gdp_tool_spec, tool_input, self.approval_context)
        if not decision.allowed:
            raise GDPToolGuardrailError(decision)
        return await self.wrapped_tool.ainvoke(tool_input)


def wrap_gdp_tool_guardrail(
    tool: BaseTool,
    spec: Any,
    approval_context: GDPToolApprovalContext | dict[str, Any] | None = None,
) -> BaseTool:
    """给单个模型可见工具套用 GDP 业务 Guardrail。"""

    context = _normalize_approval_context(approval_context)
    return GuardedGDPTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        return_direct=tool.return_direct,
        wrapped_tool=tool,
        gdp_tool_spec=spec,
        approval_context=context,
    )


def wrap_gdp_tools_guardrail(
    tools: list[BaseTool],
    specs_by_name: dict[str, Any],
    approval_context: GDPToolApprovalContext | dict[str, Any] | None = None,
) -> list[BaseTool]:
    """给一组模型可见工具套用 GDP 业务 Guardrail。"""

    return [
        wrap_gdp_tool_guardrail(tool, specs_by_name[tool.name], approval_context)
        for tool in tools
        if tool.name in specs_by_name
    ]


def evaluate_gdp_tool_guardrail(
    spec: Any,
    tool_input: Any = None,
    approval_context: GDPToolApprovalContext | dict[str, Any] | None = None,
) -> GDPToolGuardrailDecision:
    """根据工具元数据和审批上下文判断是否允许执行。"""

    context = _normalize_approval_context(approval_context)
    tool_name = str(getattr(spec, "name"))
    side_effect_level = _enum_value(getattr(spec, "sideEffectLevel", "NONE"))
    requires_approval = bool(getattr(spec, "requiresApproval", False))
    approval_key = build_gdp_tool_approval_key(spec, tool_input)

    if side_effect_level == "NONE" and not requires_approval:
        return _decision(True, tool_name, side_effect_level, requires_approval, approval_key, "无副作用工具允许执行。")
    if tool_name in context.approvedToolNames:
        return _decision(True, tool_name, side_effect_level, requires_approval, approval_key, "工具名称已通过审批。")
    if approval_key and approval_key in context.approvedApprovalKeys:
        return _decision(True, tool_name, side_effect_level, requires_approval, approval_key, "工具调用幂等键已通过审批。")
    if side_effect_level == "CONFIG_WRITE" and context.allowConfigWrite:
        return _decision(True, tool_name, side_effect_level, requires_approval, approval_key, "本次运行允许配置写入工具。")
    if side_effect_level == "BUSINESS_WRITE" and context.allowBusinessWrite:
        return _decision(True, tool_name, side_effect_level, requires_approval, approval_key, "本次运行允许业务写入工具。")
    if requires_approval:
        return _decision(False, tool_name, side_effect_level, requires_approval, approval_key, "工具需要审批，当前审批上下文未放行。")
    return _decision(True, tool_name, side_effect_level, requires_approval, approval_key, "工具未要求审批。")


def build_gdp_tool_approval_key(spec: Any, tool_input: Any = None) -> str | None:
    """基于工具幂等字段生成稳定审批键。"""

    fields = list(getattr(spec, "idempotencyKeyFields", []) or [])
    if not fields:
        return None
    normalized_input = _model_dump(tool_input)
    payload = {field: _read_path(normalized_input, field) for field in fields}
    return f"{getattr(spec, 'name')}:{_stable_json(payload)}"


def _decision(
    allowed: bool,
    tool_name: str,
    side_effect_level: str,
    requires_approval: bool,
    approval_key: str | None,
    reason: str,
) -> GDPToolGuardrailDecision:
    return GDPToolGuardrailDecision(
        allowed=allowed,
        toolName=tool_name,
        sideEffectLevel=side_effect_level,
        requiresApproval=requires_approval,
        approvalKey=approval_key,
        reason=reason,
    )


def _normalize_approval_context(
    value: GDPToolApprovalContext | dict[str, Any] | None,
) -> GDPToolApprovalContext:
    if isinstance(value, GDPToolApprovalContext):
        return value
    return GDPToolApprovalContext.model_validate(value or {})


def _tool_input_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if kwargs:
        return kwargs
    if len(args) == 1:
        return args[0]
    if args:
        return list(args)
    return {}


def _read_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return None
    return _model_dump(current)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, tuple):
        return [_model_dump(item) for item in value]
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))
