"""GDP Agent Runtime 主循环。

第二阶段：先解析/搜索 Scene（Catalog 驱动），选定后复用第一阶段执行链路
（make_scene_action → run_action → build_evidence → judge → apply_verdict）。

兼容性：
- 显式 scene_code：跳过搜索，但仍走契约解析（resolve_explicit_scene），按契约 missing_inputs
  校验，缺参逻辑与搜索路径同源；删除了第一阶段的 _REQUIRED_INPUTS_BY_SCENE 硬编码。
- 无 scene_code：进入搜索 → 选择 → 执行链路。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import HTTPException

from .adapters.catalog import SceneCatalogPort
from .catalog import create_scene_requirement, resolve_explicit_scene, search_scenes
from .decision import (
    build_approval_requirement_decision,
    build_scene_search_decision,
    build_scene_selection_decision,
    build_user_scene_selection_decision,
)
from .flow import create_input_variables, create_single_step, make_scene_action
from .log_text import (
    describe_bool,
    describe_code,
    describe_content,
    describe_facts,
    describe_name_list,
    describe_optional,
    describe_variables,
)
from .models import (
    Action,
    ActionAttempt,
    ActionStatus,
    AttemptStatus,
    Evidence,
    Observation,
    PlanStep,
    Requirement,
    RequirementProposal,
    RequirementStatus,
    SceneCandidate,
    SelectionSource,
    StepStatus,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
    Variable,
    Verdict,
    VerdictType,
)
from .selection import (
    apply_selection,
    blacklist_scene,
    decide_selection,
    ensure_requirement_matches_scene,
    ensure_selection_consistency,
)
from .store import EntityNotFoundError, Store
from .transitions import transition_action, transition_requirement, transition_step, transition_task_run

logger = logging.getLogger(__name__)

_PENDING_START_REF_PREFIX = "ref:agent-runtime/pending-start"


class StartTaskRunRequestLike(Protocol):
    """启动请求的最小结构，避免 runner 反向依赖 API 层。"""

    scene_code: str | None
    inputs: dict[str, Any]


def pending_start_ref(task_run_id: str) -> str:
    """返回待补充启动请求的固定存储引用。"""
    return f"{_PENDING_START_REF_PREFIX}/{task_run_id}"


def get_catalog() -> SceneCatalogPort:
    """返回默认 Catalog 适配器。测试可注入 fake 或 monkeypatch 本函数。"""
    from .adapters.catalog import AgentCatalogAdapter

    return AgentCatalogAdapter()


async def run_task(
    task_run: TaskRun,
    request: StartTaskRunRequestLike,
    store: Store,
    catalog: SceneCatalogPort | None = None,
) -> TaskRun:
    """主循环：解析/搜索 Scene → 选定 → 执行 → 判定。"""
    catalog = catalog or get_catalog()
    scene_code = getattr(request, "scene_code", None)
    original_store_snapshot = store.snapshot()

    logger.info(
        "GDP Agent 运行时任务开始运行：任务ID=%s，原状态=%s，场景编码=%s，输入内容=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        describe_optional(scene_code),
        describe_content(request.inputs),
    )

    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)

    # 保存待恢复启动请求，供 SUPPLY_INPUT 补参后重放（第一阶段兼容）。
    store.save_payload(
        task_run.task_run_id,
        pending_start_ref(task_run.task_run_id),
        {"scene_code": scene_code, "inputs": request.inputs},
    )

    step = create_single_step(task_run)
    requirement = create_scene_requirement(task_run, step)
    logger.info(
        "GDP Agent 运行时计划步骤已创建：任务ID=%s，步骤ID=%s，缺口ID=%s，任务目标=%s",
        task_run.task_run_id,
        step.step_id,
        requirement.requirement_id,
        step.goal,
    )

    try:
        if scene_code:
            return await _run_explicit_scene(
                task_run, step, requirement, scene_code, request.inputs, store, catalog
            )

        return await _run_search(task_run, step, requirement, request.inputs, store, catalog)
    except HTTPException:
        # Catalog 失败发生在写请求前；恢复启动前账本，避免任务卡在 RUNNING。
        if not _has_attempts(store, task_run.task_run_id):
            store.restore(original_store_snapshot)
        raise
    except Exception:
        has_attempts = _has_attempts(store, task_run.task_run_id)
        if not has_attempts:
            store.restore(original_store_snapshot)
        logger.exception(
            "GDP Agent 运行时任务异常中断：任务ID=%s，场景编码=%s，是否已有执行尝试=%s",
            task_run.task_run_id,
            describe_optional(scene_code),
            describe_bool(has_attempts),
        )
        raise


# ---------- 分支 1：显式 scene_code ----------


async def _run_explicit_scene(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
) -> TaskRun:
    """显式 scene_code 路径：契约解析 → 合成单候选 → 同搜索路径的选择/审批 gate。"""
    # scene_code 不存在 / 未发布 -> catalog.get_contract 抛 HTTPException(404)，由 API 层处理。
    proposal = await resolve_explicit_scene(requirement, scene_code, inputs, catalog)
    store.save_requirement(requirement)  # 仍 PENDING
    store.save_proposal(proposal)
    store.save_decision(
        build_user_scene_selection_decision(
            task_run,
            requirement,
            proposal,
            scene_code,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )

    requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
    store.save_requirement(requirement)
    logger.info(
        "GDP Agent 运行时显式场景已解析契约：任务ID=%s，场景编码=%s，候选数=%s",
        task_run.task_run_id,
        scene_code,
        len(proposal.candidates),
    )

    return await _select_and_maybe_execute(
        task_run,
        step,
        requirement,
        proposal,
        scene_code,
        inputs,
        SelectionSource.EXPLICIT,
        _is_approved_request(inputs),
        store,
        catalog,
    )


# ---------- 分支 2：搜索选择 ----------


async def _run_search(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
) -> TaskRun:
    """搜索路径：调 Catalog → decide_selection → 自动执行 / 等用户 / 零候选收口。"""
    proposal = await search_scenes(requirement, inputs, task_run.env_code, catalog)
    store.save_proposal(proposal)
    store.save_decision(
        build_scene_search_decision(
            task_run,
            requirement,
            proposal,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )
    logger.info(
        "GDP Agent 运行时搜索完成：任务ID=%s，候选数=%s，检索词=%s",
        task_run.task_run_id,
        len(proposal.candidates),
        describe_name_list(proposal.query_terms),
    )

    outcome = decide_selection(proposal)
    store.save_decision(
        build_scene_selection_decision(
            task_run,
            requirement,
            proposal,
            outcome,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )
    logger.info(
        "GDP Agent 运行时选择决策：任务ID=%s，决策=%s，场景编码=%s，原因=%s",
        task_run.task_run_id,
        outcome.kind,
        describe_optional(outcome.scene_code),
        outcome.reason,
    )

    if outcome.kind == "NO_CANDIDATE":
        # 零候选：Requirement 停在 PENDING（语义是"还没出候选"），挂起等用户补 scene_code 或改目标。
        store.save_requirement(requirement)  # 仍 PENDING，不转 RESOLVING
        return _suspend_for_user(task_run, step, outcome.question, SuspendReason.NEED_SCENE_SELECTION, store)

    # 有候选才转 RESOLVING（RESOLVING 的语义就是"已出候选，待选定"）。
    requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
    store.save_requirement(requirement)

    if outcome.kind == "AUTO_SELECTED":
        return await _select_and_maybe_execute(
            task_run,
            step,
            requirement,
            proposal,
            outcome.scene_code,
            inputs,
            SelectionSource.AUTO,
            _is_approved_request(inputs),
            store,
            catalog,
        )

    # NEED_USER：多候选 / 低分 / 缺参 / 需审批，挂起等用户选择或审批。
    if len(proposal.candidates) == 1 and proposal.candidates[0].requires_confirmation:
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
    return _suspend_for_user(task_run, step, outcome.question, _selection_suspend_reason(proposal), store)


# ---------- 选择 + 审批 gate + 执行 ----------


async def _select_and_maybe_execute(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    proposal: RequirementProposal,
    scene_code: str,
    inputs: dict[str, Any],
    source: SelectionSource,
    approved: bool,
    store: Store,
    catalog: SceneCatalogPort,
) -> TaskRun:
    """对选定 scene_code 先写选定事实，再执行 preflight 和审批 gate。"""
    candidate = _candidate_of(proposal, scene_code)
    if candidate is None:
        # 理论上不会发生（调用方已校验），保守收口。
        return _suspend_for_user(task_run, step, f"候选已失效：{scene_code}", SuspendReason.NEED_SCENE_SELECTION, store)

    # 先写选定事实，保证后续 APPROVE 能基于账本恢复。
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
        ensure_selection_consistency(requirement, proposal, scene_code)

    # preflight：env_code + 候选契约缺参（缺参绝不发起 Scene 写请求）。
    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        logger.info(
            "GDP Agent 运行时选定前置校验未通过，等待用户补充：任务ID=%s，场景编码=%s，缺失=%s",
            task_run.task_run_id,
            scene_code,
            describe_name_list(missing_fields),
        )
        return _suspend_for_user(task_run, step, _format_missing_required_question(missing_fields), SuspendReason.MISSING_INPUT, store)

    # 审批 gate：有写副作用且未批准 -> 挂起等审批（与选择正交）。
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
        return _suspend_for_user(task_run, step, _approval_question(candidate), SuspendReason.NEED_APPROVAL, store)

    task_run.pending_question = None
    task_run.suspend_reason = None
    return await execute_scene(task_run, step, requirement, scene_code, inputs, candidate, store)


# ---------- 第一阶段执行链路（抽出，可复用） ----------


async def execute_scene(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    candidate: SceneCandidate,
    store: Store,
) -> TaskRun:
    """第一阶段执行链路：make_scene_action → run_action → evidence → judge → apply_verdict。

    缺参校验已由调用方按候选契约 candidate.missing_inputs 完成，这里直接执行。
    执行失败（Verdict=FAILED）后把 scene_code 加入 requirement.blacklist，便于重搜排除。
    """
    action, step = _plan_scene_execution(task_run, step, requirement, scene_code, inputs, candidate, store)
    action, attempt, observation = await _run_and_record_attempt(task_run, action, store)
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


def _plan_scene_execution(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    candidate: SceneCandidate,
    store: Store,
) -> tuple[Action, PlanStep]:
    """记录计划动作、输入变量和执行输入快照。"""
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
) -> tuple[Action, ActionAttempt, Observation]:
    """记录执行尝试、原始观察和 Action 技术状态。"""
    from .execution import run_action

    attempt, observation = await run_action(action, store)
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
    """记录从观察结果抽取出的可判定证据。"""
    from .evidence import build_evidence

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
    """记录基于证据得到的结果判定。"""
    from .verdict import judge

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
    """记录 Verdict 对 TaskRun、PlanStep 和 Action 的业务收口。"""
    from .verdict import apply_verdict

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
    """执行失败后把场景加入黑名单，供后续重搜排除。"""
    if verdict.verdict_type != VerdictType.FAILED:
        return
    requirement = blacklist_scene(requirement, scene_code)
    store.save_requirement(requirement)


def _save_variables(store: Store, variables: list[Variable]) -> None:
    """保存本次执行消费的输入变量。"""
    for variable in variables:
        store.save_variable(variable)


# ---------- Helpers ----------


def _candidate_of(proposal: RequirementProposal, scene_code: str) -> SceneCandidate | None:
    for candidate in proposal.candidates:
        if candidate.scene_code == scene_code:
            return candidate
    return None


def collect_preflight_missing(task_run: TaskRun, candidate: SceneCandidate) -> list[str]:
    """选定执行前的缺口：env_code（执行必需）+ 候选契约 missing_inputs（契约驱动）。"""
    missing_fields: list[str] = []
    if _is_blank(task_run.env_code):
        missing_fields.append("env_code")
    for name in candidate.missing_inputs:
        missing_fields.append(f"inputs.{name}")
    return missing_fields


def _is_approved_request(inputs: dict[str, Any]) -> bool:
    """start 请求是否已携带审批（inputs.approved 为 true）。

    start 一般不会带 approved；审批通常在 WAITING_USER 后经 /reply 提交。但显式 scene_code
    的副作用场景若调用方在 start 就带了 approved，也予以尊重。
    """
    return inputs.get("approved") is True


def _approval_question(candidate: SceneCandidate) -> str:
    return (
        f"场景 {candidate.scene_name}（{candidate.scene_code}）执行有写副作用，需要批准后执行。"
        "请回复 SELECT_SCENE 并携带 approved=true，或回复 APPROVE 批准。"
    )


def _suspend_for_user(
    task_run: TaskRun,
    step: PlanStep,
    question: str | None,
    reason: SuspendReason,
    store: Store,
) -> TaskRun:
    """挂起等用户：TaskRun -> WAITING_USER，保存 step。"""
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


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _selection_suspend_reason(proposal: RequirementProposal) -> SuspendReason:
    """根据候选集判断这次等待用户主要卡在哪类选择缺口。"""
    if len(proposal.candidates) == 1:
        candidate = proposal.candidates[0]
        if candidate.missing_inputs:
            return SuspendReason.MISSING_INPUT
        if candidate.requires_confirmation:
            return SuspendReason.NEED_APPROVAL
    return SuspendReason.NEED_SCENE_SELECTION


def _format_missing_required_question(missing_fields: list[str]) -> str:
    return "缺少必填信息：" + "，".join(missing_fields) + "。请补充后继续。"


def _sync_action_status_with_attempt(action: Action, attempt: ActionAttempt) -> Action:
    if action.status != ActionStatus.RUNNING:
        return action
    if attempt.status == AttemptStatus.SUCCEEDED:
        return transition_action(action, ActionStatus.SUCCEEDED)
    if attempt.status == AttemptStatus.FAILED:
        return transition_action(action, ActionStatus.FAILED)
    if attempt.status == AttemptStatus.UNKNOWN_STATE:
        return transition_action(action, ActionStatus.UNKNOWN_STATE)
    return action


def _has_attempts(store: Store, task_run_id: str) -> bool:
    try:
        return bool(store.get_timeline(task_run_id)["attempts"])
    except (EntityNotFoundError, KeyError):
        return False
