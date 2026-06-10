"""GDP Agent 结构化模型决策数据模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GDPGoalSubtask(BaseModel):
    """模型拆解出的造数子目标，用于后续阶段理解任务链路。"""

    goal: str = Field(..., min_length=1, description="子目标自然语言描述，必须能追溯到用户总体造数目标。")
    phaseHint: str | None = Field(default=None, description="建议进入的 GDP 阶段，例如 SCENE_FULFILLMENT、SCENE_DESIGN 或 SOURCE_CONFIG。")
    requiredInputs: list[str] = Field(default_factory=list, description="完成该子目标需要的用户输入、变量或上游产出名称。")
    expectedOutputs: list[str] = Field(default_factory=list, description="该子目标完成后预期产生的业务输出名称。")


class GDPGoalNormalizationDecision(BaseModel):
    """用户造数目标归一化决策，供 intake 节点创建任务和生成审计事件。"""

    normalizedIntent: str = Field(..., min_length=1, description="归一化后的造数目标，表达清晰但不改变用户原意。")
    envCode: str | None = Field(default=None, description="模型从用户目标中识别出的环境编码，例如 DEV、TEST、PRE、PROD；无法确定时为空。")
    taskType: str | None = Field(default=None, description="任务类型标签，例如 CREATE_ORDER、PAY_ORDER、QUERY_ORDER 或 CUSTOM。")
    businessDomain: str | None = Field(default=None, description="业务域标签，例如 交易、支付、会员、营销；无法确定时为空。")
    userInputs: dict[str, Any] = Field(default_factory=dict, description="模型从用户自然语言中抽取的结构化输入，用户显式输入优先级更高。")
    subGoals: list[GDPGoalSubtask] = Field(default_factory=list, description="模型拆解出的子目标列表，用于后续子任务或阶段规划。")
    missingInformation: list[str] = Field(default_factory=list, description="缺失但后续可能需要向用户追问的信息。")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型对归一化结果的置信度，0 到 1。")
    reason: str = Field(..., min_length=1, description="模型给出该归一化结果的中文原因。")


class GDPReflectionDecision(BaseModel):
    """场景执行结果反思决策，供 progress_reflection 节点判断是否完成或继续推进。"""

    completed: bool = Field(..., description="当前场景执行结果是否已经满足用户总体造数目标。")
    nextAction: Literal["FINISH_OR_VERIFY", "SEARCH_NEXT_SCENE", "FAIL_TASK"] = Field(..., description="下一步动作：完成、继续搜索下一场景或终止任务。")
    reason: str = Field(..., min_length=1, description="模型判断当前结果是否满足目标的中文原因。")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型对反思结论的置信度，0 到 1。")
    missingInformation: list[str] = Field(default_factory=list, description="如果尚未完成，仍缺失的业务信息或变量。")
    evidence: list[str] = Field(default_factory=list, description="模型用于支撑判断的关键输出字段、状态或错误信息。")


class GDPSceneCandidateDecision(BaseModel):
    """历史场景候选选择决策，供 scene_fulfillment 节点在候选内做最终判断。"""

    decision: Literal["USE_SCENE", "ASK_USER", "NO_MATCH"] = Field(..., description="候选处理建议：使用某个场景、要求用户确认或判定无匹配场景。")
    sceneCode: str | None = Field(default=None, description="建议使用或推荐给用户确认的场景编码，必须来自候选列表；无匹配时为空。")
    reason: str = Field(..., min_length=1, description="模型选择、追问或放弃候选的中文原因。")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型对候选决策的置信度，0 到 1。")
    missingInputs: list[str] = Field(default_factory=list, description="模型判断该场景仍缺失的必填入参名称。")
    requiresUserConfirmation: bool = Field(default=False, description="除业务写入审批外，模型是否认为本次候选选择仍需要用户确认。")
    candidateRank: list[str] = Field(default_factory=list, description="模型按匹配程度给出的候选场景编码排序。")
    evidence: list[str] = Field(default_factory=list, description="支撑候选判断的契约字段、规则分数或变量证据。")


class GDPSourceCandidateDecision(BaseModel):
    """HTTP/SQL Source 候选选择决策，供 scene_design 节点在候选内做最终判断。"""

    decision: Literal["USE_SOURCE", "ASK_USER", "NO_MATCH"] = Field(..., description="候选处理建议：使用某个 Source、要求用户确认或判定无匹配 Source。")
    sourceCode: str | None = Field(default=None, description="建议使用或推荐给用户确认的 Source 编码，必须来自候选列表；无匹配时为空。")
    sourceType: str | None = Field(default=None, description="候选 Source 类型，例如 HTTP 或 SQL，用于审计展示。")
    reason: str = Field(..., min_length=1, description="模型选择、追问或放弃 Source 的中文原因。")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型对 Source 候选决策的置信度，0 到 1。")
    missingInputs: list[str] = Field(default_factory=list, description="模型判断该 Source 生成场景仍缺失的必填入参名称。")
    requiresUserConfirmation: bool = Field(default=False, description="除配置写入审批外，模型是否认为本次 Source 选择仍需要用户确认。")
    generationStrategy: str | None = Field(default=None, description="如果使用该 Source，建议生成场景的简要策略说明。")
    candidateRank: list[str] = Field(default_factory=list, description="模型按匹配程度给出的候选 Source 编码排序。")
    evidence: list[str] = Field(default_factory=list, description="支撑候选判断的契约字段、规则分数或变量证据。")


class GDPSourceConfigDraftDecision(BaseModel):
    """缺少 HTTP/SQL Source 时的模型配置草稿决策，供 source_config 节点追问用户。"""

    decision: Literal["DRAFT_SOURCE", "ASK_USER", "NO_DRAFT"] = Field(..., description="草稿处理建议：生成配置草稿、追问用户或暂不生成草稿。")
    sourceType: Literal["HTTP", "SQL"] | None = Field(default=None, description="草稿 Source 类型。生成草稿时必须是 HTTP 或 SQL；无法判断时为空。")
    configDraft: dict[str, Any] = Field(default_factory=dict, description="模型生成的 HttpSourceConfig 或 SqlSourceConfig 草稿 JSON，仅供用户确认编辑，不会自动保存。")
    infraReadiness: dict[str, Any] = Field(
        default_factory=dict,
        description="模型基于基础配置摘要判断出的基础配置可用性、推荐 sysCode/datasourceCode 和仍需补齐的基础配置缺口。",
    )
    missingInformation: list[str] = Field(default_factory=list, description="继续完善 Source 配置前需要用户补充的信息。")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型对草稿可用性的置信度，0 到 1。")
    reason: str = Field(..., min_length=1, description="模型生成草稿、追问或放弃草稿的中文原因。")
    assumptions: list[str] = Field(default_factory=list, description="模型生成草稿时做出的显式假设，用户确认前不能当作事实。")
    evidence: list[str] = Field(default_factory=list, description="支撑草稿的用户目标、输入、变量或上下文证据。")


class GDPSceneDraftEnhancementDecision(BaseModel):
    """模型对 SceneDefinition 场景草稿的补全建议，仅用于审批预览和后续校验链。"""

    decision: Literal["ENHANCE_SCENE", "KEEP_ORIGINAL", "ASK_USER"] = Field(
        ...,
        description="草稿处理建议：补全场景草稿、保持后端原草稿或提示仍需用户补充信息。",
    )
    sceneDraft: dict[str, Any] = Field(
        default_factory=dict,
        description="模型补全后的 SceneDefinition 草稿 JSON。仅在 ENHANCE_SCENE 时使用，并且仍需后端保护字段合并和 Pydantic 校验。",
    )
    missingInformation: list[str] = Field(default_factory=list, description="模型认为继续补全或发布前仍缺失的信息。")
    confidence: float = Field(default=0.0, ge=0, le=1, description="模型对草稿补全建议的置信度，0 到 1。")
    reason: str = Field(..., min_length=1, description="模型补全、保留原草稿或建议追问的中文原因。")
    assumptions: list[str] = Field(default_factory=list, description="模型补全时做出的显式假设，审批通过前不能当作事实。")
    evidence: list[str] = Field(default_factory=list, description="支撑草稿补全的用户目标、Source 契约、字段或上下文证据。")
