"""GDP Agent Runtime Verdict(裁决) 判定。

基于 Evidence 和 Action 状态判定。不读取 raw response，不调 LLM。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .models import (
    Action,
    ActionStatus,
    Evidence,
    PlanStep,
    StepStatus,
    TaskRun,
    TaskRunStatus,
    Verdict,
    VerdictType,
    reject_lm_proposal,
)
from .transitions import (
    transition_action,
    transition_step,
    transition_task_run,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def judge(evidence: Evidence, action: Action) -> Verdict:
    """基于 evidence 和 action 状态判定。"""
    reject_lm_proposal(evidence)
    reject_lm_proposal(action)

    verdict_id = _gen_id("vrd")

    if evidence.unknown_facts:
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.UNKNOWN_STATE,
            reason="执行结果未知: " + ", ".join(evidence.unknown_facts),
            created_at=_now(),
        )

    if evidence.missing_facts:
        has_any_passed = any(f.passed for f in evidence.facts)
        if has_any_passed:
            return Verdict(
                verdict_id=verdict_id,
                task_run_id=evidence.task_run_id,
                step_id=evidence.step_id,
                evidence_id=evidence.evidence_id,
                verdict_type=VerdictType.NEED_USER,
                reason="证据不足，缺失: " + ", ".join(evidence.missing_facts),
                created_at=_now(),
            )
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.FAILED,
            reason="证据缺失且无通过事实: " + ", ".join(evidence.missing_facts),
            created_at=_now(),
        )

    failed_facts = [f for f in evidence.facts if not f.passed]
    if failed_facts:
        reasons = [f"{f.subject}: expected={f.expected}, actual={f.actual}" for f in failed_facts]
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.FAILED,
            reason="事实未通过: " + "; ".join(reasons),
            created_at=_now(),
        )

    return Verdict(
        verdict_id=verdict_id,
        task_run_id=evidence.task_run_id,
        step_id=evidence.step_id,
        evidence_id=evidence.evidence_id,
        verdict_type=VerdictType.DONE,
        reason="所有事实通过",
        created_at=_now(),
    )


def apply_verdict(
    task_run: TaskRun,
    step: PlanStep,
    action: Action,
    verdict: Verdict,
) -> tuple[TaskRun, PlanStep, Action]:
    """根据 Verdict 联动更新 TaskRun、PlanStep 和 Action。"""
    reject_lm_proposal(verdict)

    if verdict.verdict_type == VerdictType.DONE:
        if action.status == ActionStatus.RUNNING:
            action = transition_action(action, ActionStatus.SUCCEEDED)
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.DONE)
        task_run.final_verdict_id = verdict.verdict_id
        task_run = transition_task_run(task_run, TaskRunStatus.COMPLETED)

    elif verdict.verdict_type == VerdictType.FAILED:
        if action.status == ActionStatus.RUNNING:
            action = transition_action(action, ActionStatus.FAILED)
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.FAILED)
        task_run.failure_reason = verdict.reason
        task_run = transition_task_run(task_run, TaskRunStatus.FAILED)

    elif verdict.verdict_type == VerdictType.UNKNOWN_STATE:
        if action.status == ActionStatus.RUNNING:
            action = transition_action(action, ActionStatus.UNKNOWN_STATE)
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.BLOCKED)
        task_run.pending_question = verdict.reason
        task_run = transition_task_run(task_run, TaskRunStatus.WAITING_USER)

    elif verdict.verdict_type == VerdictType.NEED_USER:
        step.verdict_id = verdict.verdict_id
        step = transition_step(step, StepStatus.BLOCKED)
        task_run.pending_question = verdict.reason
        task_run = transition_task_run(task_run, TaskRunStatus.WAITING_USER)

    return task_run, step, action
