"""GDP Agent Runtime 核心数据结构。

所有领域模型定义。LLM 输出隔离通过 LMProposal 类型实现，
事实写入接口拒绝该类型。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

TaskRunId = str
StepId = str
ActionId = str
AttemptId = str
VariableId = str
EvidenceId = str
VerdictId = str
StorageRef = str
HashValue = str

T = TypeVar("T")


class LMProposal(BaseModel, Generic[T]):  # noqa: UP046
    """LLM 输出的候选建议，只能被校验、采纳或丢弃，不能直接写事实。"""

    proposal_id: str = Field(description="建议 ID。")
    payload: T = Field(description="结构化建议内容。")
    prompt_hash: HashValue = Field(description="生成该建议的 Prompt 哈希。")
    model_name: str = Field(description="生成该建议的模型名称。")
    confidence: float = Field(ge=0.0, le=1.0, description="模型自评置信度，只能用于排序，不能作为事实。")


def reject_lm_proposal(value: object) -> None:
    """拒绝 LMProposal 写入事实接口。"""
    if isinstance(value, LMProposal):
        raise TypeError("LMProposal 不能作为事实写入。")


# ---------- TaskRun ----------


class TaskRunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepEdge(BaseModel):
    """PlanStep 依赖边。MVP 只有一个 step，但保留拓扑结构。"""

    from_step_id: StepId = Field(description="前置步骤 ID。")
    to_step_id: StepId = Field(description="后置步骤 ID。")
    variable_ids: list[VariableId] = Field(default_factory=list, description="沿依赖边传递的变量。")


class TaskRun(BaseModel):
    """一次 GDP Agent 造数任务的账本根。"""

    task_run_id: TaskRunId = Field(description="任务运行 ID。")
    thread_id: str = Field(description="所属对话线程 ID。")
    user_id: str = Field(description="用户 ID。")
    user_goal: str = Field(min_length=1, description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")
    status: TaskRunStatus = Field(description="任务状态。")
    step_ids: list[StepId] = Field(default_factory=list, description="任务内步骤 ID 列表。")
    step_edges: list[StepEdge] = Field(default_factory=list, description="步骤依赖图边。")
    active_step_id: StepId | None = Field(default=None, description="当前正在推进的步骤。")
    pending_question: str | None = Field(default=None, description="等待用户输入时展示的问题。")
    final_verdict_id: VerdictId | None = Field(default=None, description="终态 Verdict。")
    failure_reason: str | None = Field(default=None, description="终态失败时的可读原因。")
    created_at: datetime = Field(description="创建时间。")
    updated_at: datetime = Field(description="更新时间。")
    finished_at: datetime | None = Field(default=None, description="结束时间。")

    @model_validator(mode="after")
    def check_terminal_fields(self) -> TaskRun:
        if self.status in {TaskRunStatus.COMPLETED, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}:
            if self.finished_at is None:
                raise ValueError("终态 TaskRun 必须有 finished_at。")
        if self.status == TaskRunStatus.WAITING_USER and not self.pending_question:
            raise ValueError("WAITING_USER 必须有 pending_question。")
        if self.status == TaskRunStatus.COMPLETED and not self.final_verdict_id:
            raise ValueError("COMPLETED TaskRun 必须有 final_verdict_id。")
        return self


# ---------- PlanStep ----------


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class PlanStep(BaseModel):
    """用户目标拆出的业务步骤。MVP 只有一个步骤。"""

    step_id: StepId = Field(description="步骤 ID。")
    task_run_id: TaskRunId = Field(description="所属 TaskRun。")
    step_no: int = Field(ge=1, description="步骤序号。")
    goal: str = Field(min_length=1, description="该步骤要达成的业务目标。")
    status: StepStatus = Field(description="步骤状态。")
    depends_on: list[StepId] = Field(default_factory=list, description="前置步骤。")
    action_ids: list[ActionId] = Field(default_factory=list, description="该步骤产生的动作。")
    consumes: list[VariableId] = Field(default_factory=list, description="该步骤消费的变量。")
    produces: list[VariableId] = Field(default_factory=list, description="该步骤产出的变量。")
    verdict_id: VerdictId | None = Field(default=None, description="步骤最终判定。")


# ---------- Action / ActionAttempt ----------


class ActionType(StrEnum):
    EXECUTE_SCENE = "EXECUTE_SCENE"


class ActionStatus(StrEnum):
    PLANNED = "PLANNED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN_STATE = "UNKNOWN_STATE"
    CANCELLED = "CANCELLED"


class Action(BaseModel):
    """一次待执行动作。MVP 只支持执行已有 Scene。"""

    action_id: ActionId = Field(description="动作 ID。")
    task_run_id: TaskRunId = Field(description="所属 TaskRun。")
    step_id: StepId = Field(description="所属 PlanStep。")
    action_type: ActionType = Field(description="动作类型。")
    status: ActionStatus = Field(description="动作状态。")
    scene_code: str = Field(min_length=1, description="要执行的 Scene 编码。")
    input_ref: StorageRef = Field(description="完整输入参数的安全存储引用。")
    input_preview: dict[str, Any] = Field(default_factory=dict, description="可展示的输入摘要。")
    input_hash: HashValue = Field(description="输入哈希。")
    idempotency_key: str = Field(min_length=1, description="幂等键。")
    approval_required: bool = Field(description="是否需要审批。")
    attempt_ids: list[AttemptId] = Field(default_factory=list, description="执行尝试列表。")


class AttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN_STATE = "UNKNOWN_STATE"


class ActionAttempt(BaseModel):
    """Action 的一次执行尝试，append-only。"""

    attempt_id: AttemptId = Field(description="尝试 ID。")
    action_id: ActionId = Field(description="所属 Action。")
    attempt_no: int = Field(ge=1, description="尝试序号。")
    status: AttemptStatus = Field(description="尝试状态。")
    request_ref: StorageRef = Field(description="完整请求快照引用。")
    response_ref: StorageRef | None = Field(default=None, description="完整响应快照引用。")
    response_preview: dict[str, Any] = Field(default_factory=dict, description="可展示响应摘要。")
    error_type: str | None = Field(default=None, description="错误类型。")
    error_message: str | None = Field(default=None, description="错误摘要。")
    started_at: datetime = Field(description="开始时间。")
    finished_at: datetime | None = Field(default=None, description="结束时间。")


# ---------- Observation / Evidence / Verdict ----------


class Observation(BaseModel):
    """一次 Attempt 的原始观察。"""

    observation_id: str = Field(description="观察 ID。")
    task_run_id: TaskRunId = Field(description="所属 TaskRun。")
    action_id: ActionId = Field(description="所属 Action。")
    attempt_id: AttemptId = Field(description="所属 Attempt。")
    raw_ref: StorageRef = Field(description="完整原始响应或错误的安全存储引用。")
    preview: dict[str, Any] = Field(default_factory=dict, description="可展示摘要。")
    created_at: datetime = Field(description="创建时间。")


class FactPredicate(StrEnum):
    EXISTS = "EXISTS"
    EQUALS = "EQUALS"
    IN = "IN"
    NON_EMPTY = "NON_EMPTY"


class EvidenceFact(BaseModel):
    """可判定事实。"""

    subject: str = Field(description="事实主体，如 order.pay_status。")
    predicate: FactPredicate = Field(description="判定方式。")
    expected: Any = Field(description="期望值。")
    actual: Any = Field(description="实际值。")
    passed: bool = Field(description="是否通过。")
    # detail 承载场景自己算出的精确原因（如命中的失败规则描述）。
    # 业务失败时 Scene 把原因放在 businessResult 里，必须透传到这里，
    # 否则 Verdict 只能给出“执行失败”这种无信息量的结论。
    detail: str | None = Field(default=None, description="事实补充说明，如命中的业务规则描述。")
    source_observation_id: str = Field(description="事实来源 Observation。")


class Evidence(BaseModel):
    """Verdict 唯一允许读取的判定输入。"""

    evidence_id: EvidenceId = Field(description="证据 ID。")
    task_run_id: TaskRunId = Field(description="所属 TaskRun。")
    step_id: StepId = Field(description="所属 PlanStep。")
    action_id: ActionId = Field(description="所属 Action。")
    facts: list[EvidenceFact] = Field(default_factory=list, description="已知事实。")
    missing_facts: list[str] = Field(default_factory=list, description="缺失事实。")
    unknown_facts: list[str] = Field(default_factory=list, description="未知事实。")
    created_at: datetime = Field(description="创建时间。")


class VerdictType(StrEnum):
    DONE = "DONE"
    FAILED = "FAILED"
    UNKNOWN_STATE = "UNKNOWN_STATE"
    NEED_USER = "NEED_USER"


class Verdict(BaseModel):
    """基于 Evidence 得出的结构化判定。"""

    verdict_id: VerdictId = Field(description="判定 ID。")
    task_run_id: TaskRunId = Field(description="所属 TaskRun。")
    step_id: StepId = Field(description="所属 PlanStep。")
    evidence_id: EvidenceId = Field(description="引用的 Evidence。")
    verdict_type: VerdictType = Field(description="判定类型。")
    reason: str = Field(description="人类可读原因。")
    tainted_variable_ids: list[VariableId] = Field(default_factory=list, description="被污染变量。MVP 通常为空。")
    created_at: datetime = Field(description="创建时间。")


# ---------- Variable ----------


class VariableSource(StrEnum):
    USER_INPUT = "USER_INPUT"
    SCENE_OUTPUT = "SCENE_OUTPUT"
    CONTEXT = "CONTEXT"


class VariableProvenance(BaseModel):
    """变量来源。"""

    source_type: VariableSource = Field(description="变量来源类型。")
    source_id: str = Field(description="来源对象 ID。")
    action_id: ActionId | None = Field(default=None, description="来源 Action。")
    evidence_id: EvidenceId | None = Field(default=None, description="支撑该变量可信的 Evidence。")


class Variable(BaseModel):
    """TaskRun 内可绑定变量。"""

    variable_id: VariableId = Field(description="变量 ID。")
    task_run_id: TaskRunId = Field(description="所属 TaskRun。")
    name: str = Field(description="变量名。")
    semantic_type: str = Field(description="语义类型，如 ORDER_ID、CARD_NO。")
    value_ref: StorageRef = Field(description="完整值的安全存储引用。")
    value_preview: str = Field(description="可展示值，如尾号或摘要。")
    sensitive: bool = Field(description="是否敏感。")
    tainted: bool = Field(default=False, description="是否已污染。")
    provenance: VariableProvenance = Field(description="变量来源。")
    consumed_by: list[StepId] = Field(default_factory=list, description="消费该变量的步骤。")
    created_at: datetime = Field(description="创建时间。")
