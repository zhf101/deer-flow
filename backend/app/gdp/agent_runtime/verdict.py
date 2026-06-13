"""GDP Agent Runtime Verdict(裁决) 判定。

基于 Evidence 和 Action 状态判定。不读取 raw response，不调 LLM。
Action 技术状态只由执行尝试同步，Verdict 只收口 TaskRun 和 PlanStep。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .log_text import describe_fact_name, describe_fact_value
from .models import (
    Action,
    Evidence,
    PlanStep,
    StepStatus,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
    Verdict,
    VerdictType,
    reject_lm_proposal,
)
from .transitions import transition_step, transition_task_run


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
            reason="执行结果未知：" + "，".join(describe_fact_name(item) for item in evidence.unknown_facts),
            created_at=_now(),
        )

    if evidence.missing_facts:
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.NEED_USER,
            reason="证据不足，缺失：" + "，".join(describe_fact_name(item) for item in evidence.missing_facts),
            created_at=_now(),
        )

    failed_facts = [f for f in evidence.facts if not f.passed]
    if failed_facts:
        # 失败原因以“人话”为主：有 detail（业务规则原因 / 步骤级友好提示，
        # 如“无法连接到目标服务器，请检查服务器地址、端口是否正确”）就直接展示，
        # 不再用“XX未通过：期望=…实际=…”这种机器话包裹——那是给用户看的，不是给排查日志看的。
        # 只有在拿不到 detail 时，才退回“期望/实际”的技术描述兜底。
        reasons = [
            (
                f.detail
                if f.detail
                else f"{describe_fact_name(f.subject)}未达预期：期望={describe_fact_value(f.expected)}，实际={describe_fact_value(f.actual)}"
            )
            for f in failed_facts
        ]
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.FAILED,
            reason="；".join(reasons),
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
    """根据 Verdict 联动更新 TaskRun 和 PlanStep，Action 保留技术执行状态。"""
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
