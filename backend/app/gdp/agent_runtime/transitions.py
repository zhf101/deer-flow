"""造数任务状态机的安全守卫。

用户发起造数任务后，任务会经历"创建→执行→等待用户→完成/失败"等多个阶段。
所有改变任务走向的状态转移都必须经过本模块的 guard 函数校验，防止系统进入
不一致的状态导致用户任务卡死或数据丢失。

本模块守护四类状态机：
- TaskRun：用户造数任务的整体生命周期
- PlanStep：任务拆解后的单个执行步骤
- Action：步骤内的具体写操作（如调接口造数据）
- Requirement：资源缺口的识别与填补流程

Attempt、Proposal、Decision 属于执行或审计账本，由各自写入函数约束，
不纳入主状态机 guard。
"""

from __future__ import annotations

from datetime import UTC, datetime

from .models import (
    Action,
    ActionStatus,
    PlanStep,
    Requirement,
    RequirementStatus,
    StepStatus,
    TaskRun,
    TaskRunStatus,
    reject_lm_proposal,
)


class IllegalTransition(Exception):
    """非法状态转移异常。

    当系统试图将任务推入不合法的状态时抛出，保护用户任务不会因为非法状态跳转
    而丢失进度或进入不可恢复的中间态。
    """

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"非法状态转移: {from_status} -> {to_status}")


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- TaskRun 状态机 ----------
# 用户造数任务的生命周期：
# CREATED → RUNNING：用户提交造数目标，系统开始执行
# RUNNING → WAITING_USER：系统遇到无法自动决策的环节，暂停并询问用户
# RUNNING → COMPLETED：造数成功，用户可查看证据和结果
# RUNNING → FAILED：造数过程中出现不可恢复错误，用户收到失败报告
# RUNNING → CANCELLED：用户主动取消任务
# WAITING_USER → RUNNING：用户回复后任务继续执行
# WAITING_USER → CANCELLED：用户在等待期间取消任务
# COMPLETED / FAILED / CANCELLED：终态，不可再转移

TASK_RUN_LEGAL_TRANSITIONS: dict[TaskRunStatus, set[TaskRunStatus]] = {
    TaskRunStatus.CREATED: {TaskRunStatus.RUNNING, TaskRunStatus.CANCELLED},
    TaskRunStatus.RUNNING: {
        TaskRunStatus.WAITING_USER,
        TaskRunStatus.COMPLETED,
        TaskRunStatus.FAILED,
        TaskRunStatus.CANCELLED,
    },
    TaskRunStatus.WAITING_USER: {TaskRunStatus.RUNNING, TaskRunStatus.CANCELLED},
    TaskRunStatus.COMPLETED: set(),
    TaskRunStatus.FAILED: set(),
    TaskRunStatus.CANCELLED: set(),
}


def transition_task_run(run: TaskRun, target: TaskRunStatus) -> TaskRun:
    """TaskRun 状态转移守卫。

    业务目标：确保用户造数任务的每次状态变化都合法，防止任务进入死胡同。
    当前动作：校验目标状态是否允许，并处理进入 WAITING_USER 时的前置条件。
    预期结果：任务状态安全更新；进入终态时自动记录完成时间，用户可在前端看到准确耗时。
    """
    reject_lm_proposal(target)
    if target not in TASK_RUN_LEGAL_TRANSITIONS[run.status]:
        raise IllegalTransition(run.status, target)
    if target == TaskRunStatus.WAITING_USER:
        if not run.pending_question:
            raise ValueError("WAITING_USER 必须先写入 pending_question。")
        if run.suspend_reason is None:
            raise ValueError("WAITING_USER 必须先写入 suspend_reason。")
    else:
        run.pending_question = None
        run.suspend_reason = None
    run.status = target
    run.updated_at = _now()
    if target in {TaskRunStatus.COMPLETED, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}:
        run.finished_at = _now()
    return run


# ---------- PlanStep 状态机 ----------
# 单个执行步骤的生命周期：
# PENDING → RUNNING：该步骤开始执行，用户在时间线可看到进度
# RUNNING → DONE：步骤成功完成，用户可以继续下一步
# RUNNING → FAILED：步骤执行失败，用户收到失败原因
# RUNNING → BLOCKED：步骤被阻塞（如等待前置条件），用户可看到阻塞原因
# BLOCKED → RUNNING：阻塞解除后步骤继续执行
# DONE / FAILED：终态，不可再转移

STEP_LEGAL_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.RUNNING},
    StepStatus.RUNNING: {StepStatus.DONE, StepStatus.FAILED, StepStatus.BLOCKED},
    StepStatus.BLOCKED: {StepStatus.RUNNING},
    StepStatus.DONE: set(),
    StepStatus.FAILED: set(),
}


def transition_step(step: PlanStep, target: StepStatus) -> PlanStep:
    """PlanStep 状态转移守卫。

    业务目标：确保用户的每个执行步骤不会跳入非法状态，避免步骤卡死。
    当前动作：校验目标状态是否在当前步骤的合法转移范围内。
    预期结果：步骤状态安全更新，前端时间线可正确展示步骤进度。
    """
    reject_lm_proposal(target)
    if target not in STEP_LEGAL_TRANSITIONS[step.status]:
        raise IllegalTransition(step.status, target)
    step.status = target
    return step


# ---------- Action 状态机 ----------
# 步骤内具体写操作（如调接口造数据）的生命周期：
# PLANNED → RUNNING：动作开始执行，用户可看到当前正在执行的操作
# RUNNING → SUCCEEDED：动作成功，用户可看到返回的证据
# RUNNING → FAILED：动作失败，用户可看到失败原因并决定是否重试
# RUNNING → UNKNOWN_STATE：动作已发出但结果未知，用户需确认是否继续
# SUCCEEDED / FAILED / UNKNOWN_STATE：终态，不可再转移

ACTION_LEGAL_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PLANNED: {ActionStatus.RUNNING},
    ActionStatus.RUNNING: {ActionStatus.SUCCEEDED, ActionStatus.FAILED, ActionStatus.UNKNOWN_STATE},
    ActionStatus.SUCCEEDED: set(),
    ActionStatus.FAILED: set(),
    ActionStatus.UNKNOWN_STATE: set(),
}


def transition_action(action: Action, target: ActionStatus) -> Action:
    """Action 状态转移守卫。

    业务目标：确保用户的每个写操作（如调用接口造数据）不会进入非法状态，
    避免数据被重复写入或操作结果无法追溯。
    当前动作：校验目标状态是否在当前动作的合法转移范围内。
    预期结果：动作状态安全更新，用户可准确看到每个操作的成功/失败/未知结果。
    """
    reject_lm_proposal(target)
    if target not in ACTION_LEGAL_TRANSITIONS[action.status]:
        raise IllegalTransition(action.status, target)
    action.status = target
    return action


# ---------- Requirement 状态机（资源缺口识别与填补） ----------
# 当系统发现造数步骤缺少必要资源时，会创建一个 Requirement 来跟踪缺口填补：
# PENDING → RESOLVING：系统开始搜索可用场景来填补缺口，用户可看到搜索进度
# PENDING → FAILED：缺口无法填补，用户收到缺失资源说明
# RESOLVING → SATISFIED：找到合适场景并确认可用，用户任务可以继续
# RESOLVING → FAILED：搜索后仍无法找到合适场景，用户需要手动介入
# SATISFIED / FAILED：终态，不可再转移

REQUIREMENT_LEGAL_TRANSITIONS: dict[RequirementStatus, set[RequirementStatus]] = {
    RequirementStatus.PENDING: {RequirementStatus.RESOLVING, RequirementStatus.FAILED},
    RequirementStatus.RESOLVING: {RequirementStatus.SATISFIED, RequirementStatus.FAILED},
    RequirementStatus.SATISFIED: set(),
    RequirementStatus.FAILED: set(),
}


def transition_requirement(requirement: Requirement, target: RequirementStatus) -> Requirement:
    """Requirement 状态转移守卫。

    业务目标：确保资源缺口的识别与填补流程不会跳入非法状态，避免用户任务因
    资源搜索异常而卡死。
    当前动作：校验目标状态是否合法，并更新缺口的最后修改时间。
    预期结果：缺口状态安全更新，用户可在时间线看到资源搜索的实时进展。
    """
    reject_lm_proposal(target)
    if target not in REQUIREMENT_LEGAL_TRANSITIONS[requirement.status]:
        raise IllegalTransition(requirement.status, target)
    requirement.status = target
    requirement.updated_at = _now()
    return requirement
