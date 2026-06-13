"""造数结果判定模块——回答"用户的造数目标达成了吗"。

业务目标：基于证据链（Evidence）给出明确的判定结论，驱动任务进入终态或等待状态。
当前动作：judge() 从证据中得出结论（DONE/FAILED/UNKNOWN_STATE/NEED_USER），
apply_verdict() 根据结论联动更新 TaskRun 和 PlanStep 的状态。
预期结果：
  DONE → 任务完成，用户看到造数结果
  FAILED → 任务失败，用户看到友好失败原因
  UNKNOWN_STATE → 暂停等用户确认执行结果，禁止盲目重试写操作
  NEED_USER → 暂停等用户补充缺失信息

安全边界：所有判定只读取 Evidence，不读取原始响应，不接受 LMProposal，
杜绝 LLM 凭感觉宣布造数成功或失败。
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
    """回答用户最关心的问题："我的造数目标达成了吗？"

    业务目标：基于已收集的证据事实，给出结构化的判定结论，
    让用户在前端看到明确的造数结果或下一步操作指引。
    当前动作：按优先级检查证据链——
    1. 存在未知事实 → UNKNOWN_STATE（执行结果不确定，需用户确认）
    2. 存在缺失事实 → NEED_USER（证据不足，需用户补充信息）
    3. 存在未通过事实 → FAILED（造数未达预期，附业务失败原因）
    4. 全部事实通过 → DONE（造数目标达成）
    预期结果：返回 Verdict 对象，由 apply_verdict 驱动任务进入对应终态。
    安全边界：拒绝 LMProposal 输入，防止 AI 模型直接操控判定结论。
    """
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
    """将判定结论转化为用户可感知的任务状态变化。

    业务目标：根据 judge() 给出的判定结论，联动更新 TaskRun 和 PlanStep 的状态，
    使前端展示正确的任务结果（完成/失败/暂停等待用户操作）。
    当前动作：
    - DONE → 步骤标记完成，任务进入 COMPLETED，用户看到造数结果
    - FAILED → 步骤标记失败，任务进入 FAILED，用户看到失败原因
    - UNKNOWN_STATE → 步骤阻塞，任务进入 WAITING_USER，系统询问用户实际执行结果
    - NEED_USER → 步骤阻塞，任务进入 WAITING_USER，系统请用户补充缺失证据
    预期结果：返回更新后的 (TaskRun, PlanStep, Action) 三元组，
    状态机完整性由 transition 模块的 guard 函数保证。
    """
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
