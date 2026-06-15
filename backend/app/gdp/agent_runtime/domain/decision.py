"""决策审计领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .identifiers import ActionId, StepId, StorageRef, TaskRunId


class DecisionKind(StrEnum):
    """决策类型，标识系统做出的选择属于哪个业务环节。

    SCENE_SEARCH：场景检索决策——记录系统搜到了哪些候选。
    SCENE_SELECTION：场景选择决策——记录系统/用户选了哪个候选、为什么。
    APPROVAL_REQUIREMENT：审批要求决策——记录为什么需要用户审批或审批结果。
    """

    SCENE_SEARCH = "SCENE_SEARCH"
    SCENE_SELECTION = "SCENE_SELECTION"
    APPROVAL_REQUIREMENT = "APPROVAL_REQUIREMENT"


class DecisionSource(StrEnum):
    """决策来源，标识选择是由谁/什么做出的。

    RULE：系统规则自动决策。
    CATALOG：场景目录服务检索结果。
    LLM：AI 模型建议经校验后采纳。
    USER：用户手动选择。
    SYSTEM_DEFAULT：系统默认行为。
    """

    RULE = "RULE"
    CATALOG = "CATALOG"
    LLM = "LLM"
    USER = "USER"
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"


class DecisionStatus(StrEnum):
    """决策记录状态。

    DECIDED：已形成决策，记录了选择结论和理由。
    WAITING_USER：需要用户参与决策，任务暂停等待用户输入。
    SUPERSEDED：已被后续决策取代（如重新搜索后覆盖了旧选择）。
    FAILED：决策过程失败（如搜索无候选）。
    """

    DECIDED = "DECIDED"
    WAITING_USER = "WAITING_USER"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class DecisionOption(BaseModel):
    """决策候选项，记录当时有哪些可选方案供用户和审计人员查看。"""

    option_id: str = Field(description="候选项 ID，如 scene_code。")
    option_type: str = Field(description="候选项类型，如 scene、http_source。")
    label: str = Field(description="候选项展示名称，直接展示给用户。")
    score: float | None = Field(default=None, ge=0.0, le=1.0, description="候选项评分，没有评分时为空。")
    reasons: list[str] = Field(default_factory=list, description="候选项进入候选集的理由。")
    metadata: dict[str, Any] = Field(default_factory=dict, description="候选项补充元数据，默认只放非敏感摘要。")


class DecisionRejection(BaseModel):
    """未选候选项及其拒绝原因，让用户理解"为什么没选这个"。"""

    option_id: str = Field(description="未选候选项 ID。")
    reason: str = Field(description="未选择该候选项的原因说明。")


class DecisionRecord(BaseModel):
    """一次关键决策的结构化审计记录。

    业务目标：让用户和运维人员能回答"系统为什么选了这个场景""还有哪些候选"
    "为什么需要审批"等问题，实现造数过程的可解释性和可追溯性。
    注意：决策记录是审计解释账本，不驱动任务状态机流转。
    """

    decision_id: str = Field(description="决策记录唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId | None = Field(default=None, description="关联的业务步骤 ID，无法关联时为空。")
    requirement_id: str | None = Field(default=None, description="关联的资源缺口 ID，无法关联时为空。")
    proposal_id: str | None = Field(default=None, description="关联的候选集 ID，无法关联时为空。")
    action_id: ActionId | None = Field(default=None, description="关联的动作 ID，无法关联时为空。")
    scene_run_id: str | None = Field(default=None, description="关联的场景运行 ID，决策发生在执行前时为空。")
    decision_kind: DecisionKind = Field(description="决策类型：场景检索/场景选择/审批要求。")
    decision_source: DecisionSource = Field(description="决策来源：规则/目录/模型/用户/系统默认。")
    status: DecisionStatus = Field(description="决策记录状态，不等同于 TaskRunStatus。")
    target_type: str | None = Field(default=None, description="决策目标类型，如 scene。")
    target_id: str | None = Field(default=None, description="决策目标 ID，如被选中的 scene_code。")
    input_ref: StorageRef | None = Field(default=None, description="决策输入快照的存储引用，仅供审计权限读取。")
    options: list[DecisionOption] = Field(default_factory=list, description="本次决策的候选项列表，供审计查看当时有哪些可选方案。")
    selected_option: DecisionOption | None = Field(default=None, description="最终选中的候选项，未决定时为空。")
    selected_reasons: list[str] = Field(default_factory=list, description="选择该候选的理由列表。")
    rejected_reasons: list[DecisionRejection] = Field(default_factory=list, description="未选候选项及拒绝原因。")
    criteria: list[str] = Field(default_factory=list, description="本次决策采用的判断标准。")
    evidence_refs: list[str] = Field(default_factory=list, description="支撑本次决策的账本对象引用。")
    model_info: dict[str, Any] | None = Field(default=None, description="AI 模型参与信息摘要，不包含隐藏思维链。")
    summary: str = Field(description="面向审计展示的一句话中文解释，如'按目标造已支付订单检索到 3 个候选场景'。")
    created_at: datetime = Field(description="决策记录创建时间。")
