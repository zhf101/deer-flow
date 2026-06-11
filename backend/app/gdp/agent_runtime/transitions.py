"""GDP Agent Runtime 状态转移 guard 函数。

所有状态变更必须经过本模块的 guard 函数，直接赋值 status 是 bug。
"""

from __future__ import annotations

from datetime import UTC, datetime

from .models import (
    Action,
    ActionStatus,
    PlanStep,
    StepStatus,
    TaskRun,
    TaskRunStatus,
    reject_lm_proposal,
)


class IllegalTransition(Exception):
    """非法状态转移。"""

    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"非法状态转移: {from_status} -> {to_status}")


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- TaskRun 状态机 ----------

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
    """TaskRun 状态转移 guard。拒绝 LMProposal 和非法转移。"""
    reject_lm_proposal(target)
    if target not in TASK_RUN_LEGAL_TRANSITIONS[run.status]:
        raise IllegalTransition(run.status, target)
    run.status = target
    run.updated_at = _now()
    if target in {TaskRunStatus.COMPLETED, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}:
        run.finished_at = _now()
    return run


# ---------- PlanStep 状态机 ----------

STEP_LEGAL_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.RUNNING},
    StepStatus.RUNNING: {StepStatus.DONE, StepStatus.FAILED, StepStatus.BLOCKED},
    StepStatus.BLOCKED: {StepStatus.RUNNING},
    StepStatus.DONE: set(),
    StepStatus.FAILED: set(),
}


def transition_step(step: PlanStep, target: StepStatus) -> PlanStep:
    """PlanStep 状态转移 guard。"""
    reject_lm_proposal(target)
    if target not in STEP_LEGAL_TRANSITIONS[step.status]:
        raise IllegalTransition(step.status, target)
    step.status = target
    return step


# ---------- Action 状态机 ----------

ACTION_LEGAL_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PLANNED: {ActionStatus.WAITING_APPROVAL, ActionStatus.RUNNING},
    ActionStatus.WAITING_APPROVAL: {ActionStatus.RUNNING, ActionStatus.CANCELLED},
    ActionStatus.RUNNING: {ActionStatus.SUCCEEDED, ActionStatus.FAILED, ActionStatus.UNKNOWN_STATE},
    ActionStatus.SUCCEEDED: set(),
    ActionStatus.FAILED: set(),
    ActionStatus.UNKNOWN_STATE: set(),
    ActionStatus.CANCELLED: set(),
}


def transition_action(action: Action, target: ActionStatus) -> Action:
    """Action 状态转移 guard。"""
    reject_lm_proposal(target)
    if target not in ACTION_LEGAL_TRANSITIONS[action.status]:
        raise IllegalTransition(action.status, target)
    action.status = target
    return action
