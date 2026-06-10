"""GDP Agent MCP 能力策略 Pydantic 数据模型。

本模块描述 GDP 对外部 MCP 能力的安全接入契约。GDP 主 Agent 只识别
注册后的 capability，不直接暴露原始 MCP server tool。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.gdp.datagen.config.task.models import DatagenTaskPhase


class GDPMCPSideEffectLevel(StrEnum):
    """GDP MCP 能力副作用等级。"""

    NONE = "NONE"
    CONFIG_WRITE = "CONFIG_WRITE"
    BUSINESS_WRITE = "BUSINESS_WRITE"


class GDPMCPOutputSensitivity(StrEnum):
    """GDP MCP 能力输出敏感等级。"""

    PUBLIC = "PUBLIC"
    SENSITIVE = "SENSITIVE"
    LARGE = "LARGE"


class GDPMCPOutputVariablePolicy(StrEnum):
    """GDP MCP 能力输出进入任务上下文的策略。"""

    NONE = "NONE"
    SUMMARY_ONLY = "SUMMARY_ONLY"
    VISIBLE_VARIABLE = "VISIBLE_VARIABLE"
    STORAGE_REF = "STORAGE_REF"


class GDPMCPCapabilityPolicy(BaseModel):
    """GDP MCP 能力注册和治理策略。"""

    capabilityName: str = Field(..., min_length=1, description="GDP 内部能力名称，模型和节点只引用该名称，不直接引用 MCP tool。")
    mcpServerName: str = Field(..., min_length=1, description="后续实际调用时使用的 MCP server 名称。")
    mcpToolName: str = Field(..., min_length=1, description="后续实际调用时使用的 MCP tool 名称，不直接暴露给主 Agent。")
    description: str = Field(..., min_length=1, description="能力用途说明。")
    allowedPhases: list[DatagenTaskPhase] = Field(default_factory=list, description="允许使用该能力的 GDP Agent 阶段。")
    envCodes: list[str] = Field(default_factory=list, description="允许使用该能力的环境编码。为空表示不按环境限制。")
    sideEffectLevel: GDPMCPSideEffectLevel = Field(..., description="能力副作用等级，用于审批和审计策略。")
    approvalRequired: bool = Field(default=False, description="该能力是否必须经过审批。")
    idempotencyKeyFields: list[str] = Field(default_factory=list, description="从调用参数中生成审批/幂等键的字段路径。")
    outputSensitivity: GDPMCPOutputSensitivity = Field(default=GDPMCPOutputSensitivity.PUBLIC, description="能力输出敏感等级。")
    outputVariablePolicy: GDPMCPOutputVariablePolicy = Field(default=GDPMCPOutputVariablePolicy.SUMMARY_ONLY, description="能力输出进入 state、变量栈或外置存储的策略。")
    auditEventType: str = Field(default="MCP_CAPABILITY_EVALUATED", description="评估或调用该能力时建议记录的 TaskEvent 类型。")


class GDPMCPCapabilityEvaluateRequest(BaseModel):
    """GDP MCP 能力策略评估请求。"""

    capabilityName: str = Field(..., min_length=1, description="待评估的 GDP MCP capability 名称。")
    phase: DatagenTaskPhase = Field(..., description="当前 GDP Agent 阶段。")
    envCode: str | None = Field(default=None, description="当前任务环境编码。")
    arguments: dict[str, Any] = Field(default_factory=dict, description="计划传给能力的结构化参数，用于审批键和策略判断。")
    approvedApprovalKeys: list[str] = Field(default_factory=list, description="本次运行已审批通过的 capability 幂等键。")
    allowConfigWrite: bool = Field(default=False, description="是否允许配置写入类 MCP 能力。")
    allowBusinessWrite: bool = Field(default=False, description="是否允许业务写入类 MCP 能力。")


class GDPMCPCapabilityDecision(BaseModel):
    """GDP MCP 能力策略评估结果。"""

    allowed: bool = Field(..., description="是否允许本次 capability 调用。")
    capabilityName: str = Field(..., description="被评估的 GDP MCP capability 名称。")
    phase: str | None = Field(default=None, description="评估时的 GDP Agent 阶段。")
    mcpServerName: str | None = Field(default=None, description="通过评估后可使用的 MCP server 名称。")
    mcpToolName: str | None = Field(default=None, description="通过评估后可使用的 MCP tool 名称。")
    sideEffectLevel: str | None = Field(default=None, description="能力副作用等级。")
    requiresApproval: bool = Field(default=False, description="本次能力是否要求审批。")
    approvalKey: str | None = Field(default=None, description="基于 capability 和幂等字段生成的审批键。")
    outputSensitivity: str | None = Field(default=None, description="能力输出敏感等级。")
    outputVariablePolicy: str | None = Field(default=None, description="能力输出进入上下文的策略。")
    reason: str = Field(..., description="允许或拒绝的原因说明。")


class GDPMCPCapabilityPlanRequest(BaseModel):
    """GDP MCP 能力调用计划请求。"""

    taskRunId: str = Field(..., min_length=1, description="造数任务运行 ID，用于绑定 MCP capability 审计事件。")
    capabilityName: str = Field(..., min_length=1, description="待计划调用的 GDP MCP capability 名称。")
    phase: DatagenTaskPhase | None = Field(default=None, description="计划调用所在 GDP Agent 阶段。为空时使用 TaskRun 当前阶段。")
    envCode: str | None = Field(default=None, description="计划调用使用的环境编码。为空时使用 TaskRun 当前环境。")
    arguments: dict[str, Any] = Field(default_factory=dict, description="计划传给 capability 的结构化参数。")
    approvedApprovalKeys: list[str] = Field(default_factory=list, description="本次运行已审批通过的 capability 审批键。")
    allowConfigWrite: bool = Field(default=False, description="是否允许配置写入类 MCP capability。")
    allowBusinessWrite: bool = Field(default=False, description="是否允许业务写入类 MCP capability。")


class GDPMCPCapabilityCallSpec(BaseModel):
    """GDP MCP 能力内部调用规格。"""

    taskRunId: str = Field(..., description="绑定的造数任务运行 ID。")
    capabilityName: str = Field(..., description="GDP MCP capability 名称。")
    phase: str = Field(..., description="计划调用所在 GDP Agent 阶段。")
    envCode: str | None = Field(default=None, description="计划调用使用的环境编码。")
    mcpServerName: str = Field(..., description="内部 MCP server 名称，仅供适配层使用。")
    mcpToolName: str = Field(..., description="内部 MCP tool 名称，仅供适配层使用。")
    arguments: dict[str, Any] = Field(default_factory=dict, description="传给 MCP tool 的结构化参数。")
    approvalKey: str | None = Field(default=None, description="本次调用的审批或幂等键。")
    outputSensitivity: str | None = Field(default=None, description="能力输出敏感等级。")
    outputVariablePolicy: str | None = Field(default=None, description="能力输出进入上下文的策略。")
    auditEventType: str = Field(..., description="计划调用通过后写入的 TaskEvent 类型。")


class GDPMCPCapabilityPlanResponse(BaseModel):
    """GDP MCP 能力调用计划响应。"""

    decision: GDPMCPCapabilityDecision = Field(..., description="本次 capability 调用策略评估结果。")
    callSpec: GDPMCPCapabilityCallSpec | None = Field(default=None, description="允许调用时生成的内部 MCP 调用规格。")
    resultRef: dict[str, Any] | None = Field(default=None, description="写入 state 或 TaskEvent 的轻量能力结果引用。")
    executionMode: str = Field(
        default="EXTERNAL_EXECUTOR",
        description="MCP 执行模式。当前 GDP 只生成受控调用计划，真实 MCP tool 由外部执行器调用。",
    )


class GDPMCPCapabilityResultApplyRequest(BaseModel):
    """GDP MCP 能力结果归并请求。"""

    taskRunId: str = Field(..., min_length=1, description="造数任务运行 ID，用于把 MCP 结果绑定回任务生命周期。")
    capabilityName: str = Field(..., min_length=1, description="产生该结果的 GDP MCP capability 名称。")
    phase: DatagenTaskPhase | None = Field(default=None, description="结果归并所在 GDP Agent 阶段。为空时使用 TaskRun 当前阶段。")
    outputVariablePolicy: GDPMCPOutputVariablePolicy | None = Field(
        default=None,
        description="已废弃，仅为兼容保留。归并时永远以服务端 registry 按 capabilityName 注册的策略为准，本字段会被忽略。",
    )
    outputSensitivity: GDPMCPOutputSensitivity | None = Field(
        default=None,
        description="已废弃，仅为兼容保留。归并时永远以服务端 registry 按 capabilityName 注册的策略为准，本字段会被忽略。",
    )
    success: bool = Field(..., description="MCP capability 是否执行成功。")
    output: dict[str, Any] = Field(default_factory=dict, description="MCP capability 结构化输出。完整输出只落业务表或外部存储，不直接进入 Prompt。")
    storageRef: str | None = Field(default=None, description="大对象或敏感输出的外置存储引用。")
    errorType: str | None = Field(default=None, description="MCP capability 执行失败类型。")
    errorMessage: str | None = Field(default=None, description="MCP capability 执行失败说明。")


class GDPMCPCapabilityResultApplyResponse(BaseModel):
    """GDP MCP 能力结果归并响应。"""

    resultRef: dict[str, Any] = Field(..., description="可写入 GDPState.result_refs 的轻量 MCP 结果引用。")
    visibleVariables: list[str] = Field(default_factory=list, description="本次归并写入变量栈的变量名列表。")
    eventType: str = Field(..., description="本次归并写入的 TaskEvent 类型。")
    nextAction: str = Field(
        default="CALL_TASK_CONTINUE",
        description="结果归并后的建议动作。外部调用方按需调用任务 continue 接口继续推进 GDP 图。",
    )
