"""场景选择后的前置门禁。

本模块负责候选场景被选中之后的共用门禁：
写入选定事实、检查必填输入、检查副作用审批，全部通过后交给执行流水线。
"""

from __future__ import annotations

import logging
from typing import Any

from ..domain.transitions import transition_requirement, transition_task_run
from ..ledger.refs import pending_start_ref
from ..models import (
    PlanStep,
    Requirement,
    RequirementProposal,
    RequirementStatus,
    SceneCandidate,
    SelectionSource,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
)
from ..ports.idempotency import IdempotencyGate
from ..store import Store
from ..support.log_text import describe_code, describe_name_list, describe_optional
from .decision_records import build_approval_requirement_decision
from .execution_pipeline import collect_preflight_missing, execute_scene
from .selection_policy import apply_selection, ensure_selection_consistency

logger = logging.getLogger(__name__)


async def select_and_maybe_execute(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    proposal: RequirementProposal,
    scene_code: str,
    inputs: dict[str, Any],
    source: SelectionSource,
    approved: bool,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """选定场景后的三重门——校验入参齐全 → 审批有副作用的场景 → 执行。"""

    candidate = _candidate_of(proposal, scene_code)
    if candidate is None:
        # 候选已失效（理论上不应发生，调用方已校验），保守暂停等用户重新选择。
        return suspend_for_user(task_run, step, f"候选已失效：{scene_code}", SuspendReason.NEED_SCENE_SELECTION, store)

    # 记录选定事实到账本，保证后续审批流程能基于账本恢复上下文。
    if requirement.status != RequirementStatus.SATISFIED:
        requirement, proposal = apply_selection(requirement, proposal, scene_code, source)
        requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
        store.save_requirement(requirement)
        store.save_proposal(proposal)
        logger.info(
            "GDP Agent 运行时场景已选定：任务ID=%s，场景编码=%s，选定来源=%s，缺口状态=%s",
            task_run.task_run_id,
            scene_code,
            source.value,
            describe_code(requirement.status),
        )
    else:
        # 已选定过（如用户补参后重放），校验一致性。
        ensure_selection_consistency(requirement, proposal, scene_code)

    # 执行前校验：检查环境编码和候选契约缺失的入参，缺参绝不发起场景写请求。
    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        logger.info(
            "GDP Agent 运行时选定前置校验未通过，等待用户补充：任务ID=%s，场景编码=%s，缺失=%s",
            task_run.task_run_id,
            scene_code,
            describe_name_list(missing_fields),
        )
        return suspend_for_user(
            task_run,
            step,
            _format_missing_required_question(missing_fields),
            SuspendReason.MISSING_INPUT,
            store,
        )

    # 审批关卡：场景有写副作用且用户尚未批准时，暂停等用户确认后执行。
    if candidate.requires_confirmation and not approved:
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                candidate,
                approved=False,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )
        logger.info(
            "GDP Agent 运行时选定场景需审批，等待用户批准：任务ID=%s，场景编码=%s",
            task_run.task_run_id,
            scene_code,
        )
        return suspend_for_user(task_run, step, _approval_question(candidate), SuspendReason.NEED_APPROVAL, store)

    # 三重门全部通过，清除暂停提示后进入执行链路。
    task_run.pending_question = None
    task_run.suspend_reason = None
    return await execute_scene(task_run, step, requirement, scene_code, inputs, candidate, store, idempotency_gate)


def suspend_for_selection_decision(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    proposal: RequirementProposal,
    question: str | None,
    store: Store,
) -> TaskRun:
    """因需要用户选择或审批而挂起任务。"""

    if len(proposal.candidates) == 1 and proposal.candidates[0].requires_confirmation:
        # 唯一候选但有写副作用，需要用户审批后才能执行。
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                proposal.candidates[0],
                approved=False,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )
    return suspend_for_user(task_run, step, question, selection_suspend_reason(proposal), store)


def suspend_for_user(
    task_run: TaskRun,
    step: PlanStep,
    question: str | None,
    reason: SuspendReason,
    store: Store,
) -> TaskRun:
    """暂停造数任务并向用户展示待处理事项。"""

    task_run.pending_question = question or "需要用户补充信息后继续。"
    task_run.suspend_reason = reason
    task_run = transition_task_run(task_run, TaskRunStatus.WAITING_USER)
    store.save_step(step)
    store.save_task_run(task_run)
    logger.info(
        "GDP Agent 运行时任务挂起等待用户：任务ID=%s，状态=%s，待用户确认=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        describe_optional(task_run.pending_question),
    )
    return task_run


def selection_suspend_reason(proposal: RequirementProposal) -> SuspendReason:
    """判断任务暂停时用户主要需要做什么操作。"""

    if len(proposal.candidates) == 1:
        candidate = proposal.candidates[0]
        if candidate.missing_inputs:
            return SuspendReason.MISSING_INPUT
        if candidate.requires_confirmation:
            return SuspendReason.NEED_APPROVAL
    return SuspendReason.NEED_SCENE_SELECTION


def _candidate_of(proposal: RequirementProposal, scene_code: str) -> SceneCandidate | None:
    for candidate in proposal.candidates:
        if candidate.scene_code == scene_code:
            return candidate
    return None


def _approval_question(candidate: SceneCandidate) -> str:
    return (
        f"场景 {candidate.scene_name}（{candidate.scene_code}）执行有写副作用，需要批准后执行。"
        "请回复 SELECT_SCENE 并携带 approved=true，或回复 APPROVE 批准。"
    )


def _format_missing_required_question(missing_fields: list[str]) -> str:
    return "缺少必填信息：" + "，".join(missing_fields) + "。请补充后继续。"
