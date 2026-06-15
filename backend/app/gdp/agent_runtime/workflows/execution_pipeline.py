"""场景执行流水线。

本模块收拢"创建动作 → 调用场景 → 收集证据 → 判定结果 → 收口任务状态"这条执行链路。
runner.py 只负责选择和恢复流程，本模块负责真正进入写请求后的账本推进。
"""

from __future__ import annotations

import logging
from typing import Any

from ..domain.factories import create_input_variables, make_scene_action
from ..domain.transitions import transition_action, transition_step
from ..execution import run_action
from ..models import (
    Action,
    ActionAttempt,
    ActionStatus,
    AttemptStatus,
    Evidence,
    Observation,
    PlanStep,
    Requirement,
    SceneCandidate,
    StepStatus,
    TaskRun,
    Variable,
    Verdict,
    VerdictType,
)
from ..ports.idempotency import IdempotencyGate
from ..store import Store
from ..support.log_text import (
    describe_bool,
    describe_code,
    describe_content,
    describe_facts,
    describe_name_list,
    describe_optional,
    describe_variables,
)
from .selection_policy import blacklist_scene, ensure_requirement_matches_scene

logger = logging.getLogger(__name__)


async def execute_scene(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    candidate: SceneCandidate,
    store: Store,
    idempotency_gate: IdempotencyGate | None = None,
) -> TaskRun:
    """执行已选定场景并收口任务状态。"""

    action, step = _plan_scene_execution(task_run, step, requirement, scene_code, inputs, candidate, store)
    action, attempt, observation = await _run_and_record_attempt(task_run, action, store, idempotency_gate)
    evidence = _build_and_record_evidence(task_run, step, action, observation, attempt, store)
    verdict = _judge_and_record_verdict(task_run, evidence, action, store)
    task_run, step, action = _apply_and_record_verdict(task_run, step, action, verdict, store)
    _record_failed_scene_blacklist(requirement, scene_code, verdict, store)

    logger.info(
        "GDP Agent 运行时任务运行结束：任务ID=%s，任务状态=%s，步骤ID=%s，步骤状态=%s，动作ID=%s，动作状态=%s，步骤判定ID=%s，最终判定ID=%s，待用户确认=%s，失败原因=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        step.step_id,
        describe_code(step.status),
        action.action_id,
        describe_code(action.status),
        describe_optional(step.verdict_id),
        describe_optional(task_run.final_verdict_id),
        describe_optional(task_run.pending_question),
        describe_optional(task_run.failure_reason),
    )

    return task_run


def collect_preflight_missing(task_run: TaskRun, candidate: SceneCandidate) -> list[str]:
    """执行前检查缺失信息，避免在入参不全时盲目发起场景调用。"""

    missing_fields: list[str] = []
    if _is_blank(task_run.env_code):
        missing_fields.append("env_code")
    for name in candidate.missing_inputs:
        missing_fields.append(f"inputs.{name}")
    return missing_fields


def _plan_scene_execution(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    candidate: SceneCandidate,
    store: Store,
) -> tuple[Action, PlanStep]:
    """记录执行计划，准备输入变量。"""

    ensure_requirement_matches_scene(requirement, scene_code)
    action = make_scene_action(step, scene_code, inputs, approval_required=candidate.requires_confirmation)
    logger.info(
        "GDP Agent 运行时执行动作已计划：任务ID=%s，步骤ID=%s，动作ID=%s，动作类型=%s，场景编码=%s，输入摘要=%s，是否需要审批=%s",
        task_run.task_run_id,
        step.step_id,
        action.action_id,
        describe_code(action.action_type),
        action.scene_code,
        describe_content(action.input_preview),
        describe_bool(action.approval_required),
    )

    variables = create_input_variables(task_run, step, inputs)
    store.save_payload(task_run.task_run_id, action.input_ref, inputs)

    step = transition_step(step, StepStatus.RUNNING)
    action = transition_action(action, ActionStatus.RUNNING)

    store.save_task_run(task_run)
    store.save_step(step)
    store.save_action(action)
    _save_variables(store, variables)
    logger.info(
        "GDP Agent 运行时初始账本已写入存储：任务ID=%s，步骤ID=%s，动作ID=%s，变量=%s",
        task_run.task_run_id,
        step.step_id,
        action.action_id,
        describe_variables(variables),
    )
    return action, step


async def _run_and_record_attempt(
    task_run: TaskRun,
    action: Action,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> tuple[Action, ActionAttempt, Observation]:
    """执行场景并记录尝试和观察。"""

    attempt, observation = await run_action(action, store, idempotency_gate)
    action = _sync_action_status_with_attempt(action, attempt)
    store.save_attempt(attempt)
    store.save_observation(observation)
    store.save_action(action)
    logger.info(
        "GDP Agent 运行时动作执行完成：任务ID=%s，动作ID=%s，尝试ID=%s，尝试状态=%s，观察ID=%s，原始结果引用=%s，错误类型=%s，错误信息=%s",
        task_run.task_run_id,
        action.action_id,
        attempt.attempt_id,
        describe_code(attempt.status),
        observation.observation_id,
        observation.raw_ref,
        describe_optional(attempt.error_type),
        describe_optional(attempt.error_message),
    )
    return action, attempt, observation


def _build_and_record_evidence(
    task_run: TaskRun,
    step: PlanStep,
    action: Action,
    observation: Observation,
    attempt: ActionAttempt,
    store: Store,
) -> Evidence:
    """从观察中抽取可判定证据。"""

    from ..evidence import build_evidence

    evidence = build_evidence(step, action, observation, attempt)
    store.save_evidence(evidence)
    logger.info(
        "GDP Agent 运行时判定证据已生成：任务ID=%s，证据ID=%s，事实=%s，缺失事实=%s，未知事实=%s",
        task_run.task_run_id,
        evidence.evidence_id,
        describe_facts(evidence.facts),
        describe_name_list(evidence.missing_facts),
        describe_name_list(evidence.unknown_facts),
    )
    return evidence


def _judge_and_record_verdict(task_run: TaskRun, evidence: Evidence, action: Action, store: Store) -> Verdict:
    """基于证据做出结果判定。"""

    from ..verdict import judge

    verdict = judge(evidence, action)
    store.save_verdict(verdict)
    logger.info(
        "GDP Agent 运行时判定结果已生成：任务ID=%s，判定ID=%s，判定类型=%s，原因=%s",
        task_run.task_run_id,
        verdict.verdict_id,
        describe_code(verdict.verdict_type),
        verdict.reason,
    )
    return verdict


def _apply_and_record_verdict(
    task_run: TaskRun,
    step: PlanStep,
    action: Action,
    verdict: Verdict,
    store: Store,
) -> tuple[TaskRun, PlanStep, Action]:
    """根据判定更新任务和步骤状态。"""

    from ..verdict import apply_verdict

    task_run, step, action = apply_verdict(task_run, step, action, verdict)
    store.save_task_run(task_run)
    store.save_step(step)
    store.save_action(action)
    return task_run, step, action


def _record_failed_scene_blacklist(
    requirement: Requirement,
    scene_code: str,
    verdict: Verdict,
    store: Store,
) -> None:
    """失败场景加入黑名单，避免重搜时再次推荐。"""

    if verdict.verdict_type != VerdictType.FAILED:
        return
    requirement = blacklist_scene(requirement, scene_code)
    store.save_requirement(requirement)


def _save_variables(store: Store, variables: list[Variable]) -> None:
    """将本次造数消费的业务数据持久化到账本。"""

    for variable in variables:
        store.save_variable(variable)


def _sync_action_status_with_attempt(action: Action, attempt: ActionAttempt) -> Action:
    """将动作的技术执行状态与尝试结果同步。"""

    if action.status != ActionStatus.RUNNING:
        return action
    if attempt.status == AttemptStatus.SUCCEEDED:
        return transition_action(action, ActionStatus.SUCCEEDED)
    if attempt.status == AttemptStatus.FAILED:
        return transition_action(action, ActionStatus.FAILED)
    if attempt.status == AttemptStatus.UNKNOWN_STATE:
        return transition_action(action, ActionStatus.UNKNOWN_STATE)
    return action


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""
