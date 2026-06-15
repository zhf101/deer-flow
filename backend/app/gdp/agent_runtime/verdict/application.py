"""判定结论应用。"""

from __future__ import annotations

from ..domain.transitions import transition_step, transition_task_run
from ..models import (
    Action,
    PlanStep,
    StepStatus,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
    Verdict,
    VerdictType,
    reject_lm_proposal,
)


def apply_verdict(
    task_run: TaskRun,
    step: PlanStep,
    action: Action,
    verdict: Verdict,
) -> tuple[TaskRun, PlanStep, Action]:
    """将判定结论转化为用户可感知的任务状态变化。"""

    reject_lm_proposal(verdict)

    if verdict.verdict_type == VerdictType.DONE:
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.DONE)
        task_run.final_verdict_id = verdict.verdict_id
        task_run = transition_task_run(task_run, TaskRunStatus.COMPLETED)

    elif verdict.verdict_type == VerdictType.FAILED:
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.FAILED)
        task_run.failure_reason = verdict.reason
        task_run = transition_task_run(task_run, TaskRunStatus.FAILED)

    elif verdict.verdict_type == VerdictType.UNKNOWN_STATE:
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.BLOCKED)
        task_run.pending_question = verdict.reason
        task_run.suspend_reason = SuspendReason.UNKNOWN_STATE_CONFIRMATION
        task_run = transition_task_run(task_run, TaskRunStatus.WAITING_USER)

    elif verdict.verdict_type == VerdictType.NEED_USER:
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.BLOCKED)
        task_run.pending_question = verdict.reason
        task_run.suspend_reason = SuspendReason.NEED_EVIDENCE
        task_run = transition_task_run(task_run, TaskRunStatus.WAITING_USER)

    return task_run, step, action
