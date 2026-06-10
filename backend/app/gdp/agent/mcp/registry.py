"""GDP Agent MCP capability 注册和策略评估。"""

from __future__ import annotations

import json
from typing import Any

from app.gdp.agent.mcp.models import (
    GDPMCPCapabilityDecision,
    GDPMCPCapabilityPolicy,
    GDPMCPOutputSensitivity,
    GDPMCPOutputVariablePolicy,
    GDPMCPSideEffectLevel,
)
from app.gdp.datagen.config.task.models import DatagenTaskPhase

_MCP_CAPABILITIES: tuple[GDPMCPCapabilityPolicy, ...] = (
    GDPMCPCapabilityPolicy(
        capabilityName="gdp-mcp-knowledge-search",
        mcpServerName="knowledge-base",
        mcpToolName="search_datagen_knowledge",
        description="搜索企业造数知识库、接口规范或历史方案摘要。",
        allowedPhases=[
            DatagenTaskPhase.SCENE_DESIGN,
            DatagenTaskPhase.SOURCE_CONFIG,
            DatagenTaskPhase.INFRA_CONFIG,
            DatagenTaskPhase.PROGRESS_REFLECTION,
        ],
        sideEffectLevel=GDPMCPSideEffectLevel.NONE,
        approvalRequired=False,
        idempotencyKeyFields=["query"],
        outputSensitivity=GDPMCPOutputSensitivity.PUBLIC,
        outputVariablePolicy=GDPMCPOutputVariablePolicy.SUMMARY_ONLY,
    ),
    GDPMCPCapabilityPolicy(
        capabilityName="gdp-mcp-approval-ticket",
        mcpServerName="approval-workflow",
        mcpToolName="create_datagen_approval_ticket",
        description="为高风险造数动作创建外部审批单，并把审批单号作为任务事件引用。",
        allowedPhases=[
            DatagenTaskPhase.SCENE_EXECUTING,
            DatagenTaskPhase.SOURCE_CONFIG,
            DatagenTaskPhase.INFRA_CONFIG,
        ],
        envCodes=["DEV", "TEST", "PRE"],
        sideEffectLevel=GDPMCPSideEffectLevel.CONFIG_WRITE,
        approvalRequired=True,
        idempotencyKeyFields=["taskRunId", "ticketType"],
        outputSensitivity=GDPMCPOutputSensitivity.SENSITIVE,
        outputVariablePolicy=GDPMCPOutputVariablePolicy.STORAGE_REF,
        auditEventType="MCP_APPROVAL_TICKET_REQUESTED",
    ),
    GDPMCPCapabilityPolicy(
        capabilityName="gdp-mcp-quality-check",
        mcpServerName="data-quality",
        mcpToolName="validate_datagen_result",
        description="调用外部数据质量规则校验造数结果摘要。",
        allowedPhases=[DatagenTaskPhase.SCENE_EXECUTING, DatagenTaskPhase.PROGRESS_REFLECTION],
        sideEffectLevel=GDPMCPSideEffectLevel.NONE,
        approvalRequired=False,
        idempotencyKeyFields=["taskRunId", "sceneRunId"],
        outputSensitivity=GDPMCPOutputSensitivity.SENSITIVE,
        outputVariablePolicy=GDPMCPOutputVariablePolicy.SUMMARY_ONLY,
        auditEventType="MCP_QUALITY_CHECKED",
    ),
    GDPMCPCapabilityPolicy(
        capabilityName="gdp-mcp-variable-enrichment",
        mcpServerName="data-enrichment",
        mcpToolName="enrich_datagen_variables",
        description="根据外部规则补全当前造数任务可继续消费的变量摘要。",
        allowedPhases=[DatagenTaskPhase.PROGRESS_REFLECTION],
        sideEffectLevel=GDPMCPSideEffectLevel.NONE,
        approvalRequired=False,
        idempotencyKeyFields=["taskRunId", "variableNames"],
        outputSensitivity=GDPMCPOutputSensitivity.SENSITIVE,
        outputVariablePolicy=GDPMCPOutputVariablePolicy.VISIBLE_VARIABLE,
        auditEventType="MCP_VARIABLES_ENRICHED",
    ),
)


def list_gdp_mcp_capabilities() -> list[GDPMCPCapabilityPolicy]:
    """列出 GDP 已注册 MCP capability。"""

    return [item.model_copy(deep=True) for item in _MCP_CAPABILITIES]


def get_gdp_mcp_capability(capability_name: str) -> GDPMCPCapabilityPolicy:
    """按 capability 名称读取 GDP MCP 策略。"""

    for item in _MCP_CAPABILITIES:
        if item.capabilityName == capability_name:
            return item.model_copy(deep=True)
    raise KeyError(capability_name)


def list_gdp_mcp_capabilities_for_phase(phase: DatagenTaskPhase | str | None) -> list[GDPMCPCapabilityPolicy]:
    """按 GDP Agent 阶段列出允许使用的 MCP capability。"""

    normalized = _normalize_phase(phase)
    if normalized is None:
        return []
    return [item.model_copy(deep=True) for item in _MCP_CAPABILITIES if normalized in item.allowedPhases]


def evaluate_gdp_mcp_capability(
    *,
    capability_name: str,
    phase: DatagenTaskPhase | str | None,
    env_code: str | None,
    arguments: dict[str, Any] | None = None,
    approved_approval_keys: list[str | None] | None = None,
    allow_config_write: bool = False,
    allow_business_write: bool = False,
) -> GDPMCPCapabilityDecision:
    """评估一次 GDP MCP capability 计划调用是否允许。"""

    capability = _find_capability(capability_name)
    normalized_phase = _normalize_phase(phase)
    if capability is None:
        return GDPMCPCapabilityDecision(
            allowed=False,
            capabilityName=capability_name,
            phase=normalized_phase.value if normalized_phase else None,
            reason="MCP 能力未在 GDP registry 注册，禁止暴露原始 MCP tool。",
        )
    approval_key = _approval_key(capability, arguments or {})
    decision = _base_decision(capability, normalized_phase, approval_key)
    if normalized_phase is None or normalized_phase not in capability.allowedPhases:
        return decision.model_copy(update={"allowed": False, "reason": "当前 GDP 阶段不允许使用该 MCP capability。"})
    if capability.envCodes and (env_code is None or env_code not in capability.envCodes):
        return decision.model_copy(update={"allowed": False, "reason": "当前环境不允许使用该 MCP capability。"})
    if not capability.approvalRequired:
        return decision.model_copy(update={"allowed": True, "reason": "无审批要求的 MCP capability 允许使用。"})
    approved_keys = {key for key in approved_approval_keys or [] if key}
    if approval_key and approval_key in approved_keys:
        return decision.model_copy(update={"allowed": True, "reason": "MCP capability 审批键已通过审批。"})
    if capability.sideEffectLevel == GDPMCPSideEffectLevel.CONFIG_WRITE and allow_config_write:
        return decision.model_copy(update={"allowed": True, "reason": "本次运行允许配置写入类 MCP capability。"})
    if capability.sideEffectLevel == GDPMCPSideEffectLevel.BUSINESS_WRITE and allow_business_write:
        return decision.model_copy(update={"allowed": True, "reason": "本次运行允许业务写入类 MCP capability。"})
    return decision.model_copy(update={"allowed": False, "reason": "MCP capability 需要审批，当前审批上下文未放行。"})


def _find_capability(capability_name: str) -> GDPMCPCapabilityPolicy | None:
    for item in _MCP_CAPABILITIES:
        if item.capabilityName == capability_name:
            return item
    return None


def _base_decision(
    capability: GDPMCPCapabilityPolicy,
    phase: DatagenTaskPhase | None,
    approval_key: str | None,
) -> GDPMCPCapabilityDecision:
    return GDPMCPCapabilityDecision(
        allowed=False,
        capabilityName=capability.capabilityName,
        phase=phase.value if phase else None,
        mcpServerName=capability.mcpServerName,
        mcpToolName=capability.mcpToolName,
        sideEffectLevel=capability.sideEffectLevel.value,
        requiresApproval=capability.approvalRequired,
        approvalKey=approval_key,
        outputSensitivity=capability.outputSensitivity.value,
        outputVariablePolicy=capability.outputVariablePolicy.value,
        reason="待评估。",
    )


def _approval_key(capability: GDPMCPCapabilityPolicy, arguments: dict[str, Any]) -> str | None:
    if not capability.idempotencyKeyFields:
        return None
    payload = {field: _read_path(arguments, field) for field in capability.idempotencyKeyFields}
    return f"{capability.capabilityName}:{json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"


def _read_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _normalize_phase(phase: DatagenTaskPhase | str | None) -> DatagenTaskPhase | None:
    if phase is None:
        return None
    if isinstance(phase, DatagenTaskPhase):
        return phase
    try:
        return DatagenTaskPhase(str(phase))
    except ValueError:
        return None
