"""GDP 造数运行时引擎主循环。

本模块是造数运行时的心脏——驱动用户造数目标从"创建"走到"完成"或"等待用户"的完整生命周期。

用户提交造数目标后，引擎按以下流程推进：
1. 创建执行计划和需求缺口；
2. 根据是否携带场景编码走不同路径：
   - 携带场景编码（快速通道）：解析契约 → 确认入参齐全 → 直接执行；
   - 未携带场景编码（智能搜索）：调用场景目录搜索 → 规则自动选择 / 暂停等用户选定；
3. 选定场景后依次通过入参校验、审批关卡，最终调用场景并收集证据、判定结果、收口任务状态。

任何阶段遇到信息缺失或需要审批，任务会暂停并向前端展示 pending_question 提示，
等待用户通过 /reply 补充后继续。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from .adapters.catalog import SceneCatalogPort
from .catalog import create_scene_requirement, resolve_explicit_scene, search_scenes
from .decision import (
    build_approval_requirement_decision,
    build_scene_search_decision,
    build_scene_selection_decision,
    build_user_scene_selection_decision,
)
from .errors import RuntimeServiceError
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
IdempotencyGate = Callable[[str, str, str], Awaitable[bool]]


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
    idempotency_gate: IdempotencyGate | None = None,
) -> TaskRun:
    """主循环入口：让用户的造数需求被完整处理。

    业务目标：用户提交造数目标后，系统创建执行计划和需求缺口，然后根据是否指定场景编码走不同路径——
    指定了场景编码则直接执行，未指定则智能搜索后选定执行。最终任务是完成、失败或暂停等用户。

    预期结果：任务状态被正确推进，所有中间状态（步骤、动作、尝试、证据、判定）被完整记录到账本。
    """
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

    # 保存启动请求快照，供用户后续补参时重放使用（第一阶段兼容）。
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
        # 根据是否指定场景编码走不同路径：快速通道或智能搜索。
        if scene_code:
            return await _run_explicit_scene(
                task_run, step, requirement, scene_code, request.inputs, store, catalog, idempotency_gate
            )

        return await _run_search(task_run, step, requirement, request.inputs, store, catalog, idempotency_gate)
    except RuntimeServiceError:
        # Catalog 服务失败且尚未发起任何写请求时，恢复账本快照避免任务卡在 RUNNING 状态。
        if not _has_attempts(store, task_run.task_run_id):
            store.restore(original_store_snapshot)
        raise
    except Exception:
        # 其他异常时，如果还没有发起过场景调用（无尝试记录），恢复账本快照避免用户任务卡在不一致状态。
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


# ---------- 分支 1：用户已指定场景编码时的快速通道 ----------


async def _run_explicit_scene(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户已指定场景编码时的快速通道——解析契约确认入参齐全后直接执行。

    业务目标：用户明确知道要用哪个场景，跳过搜索直接走执行链路，节省交互轮次。
    当前动作：解析场景契约、合成单候选，然后进入与搜索路径共用的选择/审批关卡。
    预期结果：契约解析成功则进入执行，场景不存在则由 API 层返回 404。
    """
    # 场景不存在或未发布时，catalog.get_contract 会抛 HTTPException(404)，由 API 层统一处理。
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
        idempotency_gate,
    )


# ---------- 分支 2：用户未指定场景时的智能搜索 ----------


async def _run_search(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户未指定场景时的智能搜索——调场景目录搜索、规则选择、必要时暂停等用户。

    业务目标：用户不知道具体场景编码时，系统根据造数目标自动检索并选定最合适的场景。
    当前动作：调用场景目录搜索，按规则自动选定或暂停等用户确认。
    预期结果：自动选定则直接执行，零候选或多候选则暂停等用户补充信息或选择。
    """
    # 调用场景目录检索候选场景，结果记入账本供后续选择和审计。
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

    # 根据候选集规则自动选定：唯一高分候选则自动选定，否则暂停等用户决策。
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
        # 搜索无结果：暂停等用户补充场景编码或调整造数目标，缺口保持 PENDING 表示"还没有候选"。
        store.save_requirement(requirement)  # 仍 PENDING，不转 RESOLVING
        return _suspend_for_user(task_run, step, outcome.question, SuspendReason.NEED_SCENE_SELECTION, store)

    # 有候选时转入 RESOLVING，语义是"已有候选，正在选定中"。
    requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
    store.save_requirement(requirement)

    if outcome.kind == "AUTO_SELECTED":
        # 规则自动选定唯一候选，直接进入执行链路。
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
            idempotency_gate,
        )

    # NEED_USER：多候选、低分、缺参或需审批时，暂停等用户选择或批准后继续。
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
    return _suspend_for_user(task_run, step, outcome.question, _selection_suspend_reason(proposal), store)


# ---------- 选定场景后的三重门：校验入参 → 审批副作用 → 执行 ----------


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
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """选定场景后的三重门——校验入参齐全 → 审批有副作用的场景 → 执行。

    业务目标：确保场景调用前入参完整、副作用已被用户批准，避免盲目发起写请求。
    当前动作：记录选定事实，依次检查入参缺口和审批关卡，全部通过则进入执行链路。
    预期结果：任一关卡未通过则暂停等用户，全部通过则直接执行场景。
    """
    candidate = _candidate_of(proposal, scene_code)
    if candidate is None:
        # 候选已失效（理论上不应发生，调用方已校验），保守暂停等用户重新选择。
        return _suspend_for_user(task_run, step, f"候选已失效：{scene_code}", SuspendReason.NEED_SCENE_SELECTION, store)

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
        return _suspend_for_user(task_run, step, _format_missing_required_question(missing_fields), SuspendReason.MISSING_INPUT, store)

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
        return _suspend_for_user(task_run, step, _approval_question(candidate), SuspendReason.NEED_APPROVAL, store)

    # 三重门全部通过，清除暂停提示后进入执行链路。
    task_run.pending_question = None
    task_run.suspend_reason = None
    return await execute_scene(task_run, step, requirement, scene_code, inputs, candidate, store, idempotency_gate)


# ---------- 执行链路：创建动作 → 调用场景 → 收集证据 → 判定结果 → 收口任务状态 ----------


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
    """第一阶段执行链路——创建动作 → 调用场景 → 收集证据 → 判定结果 → 收口任务状态。

    业务目标：实际调用造数场景，收集执行证据并做出结果判定，最终收口任务和步骤的状态。
    当前动作：依次执行计划、尝试、证据、判定、收口五步，失败时将场景加入黑名单。
    预期结果：任务状态变为完成、失败或需要用户确认，所有中间产物记入账本。

    入参校验已由调用方按候选契约完成，这里直接执行。
    执行失败后将 scene_code 加入 requirement.blacklist，便于重搜时排除失败场景。
    """
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


def _plan_scene_execution(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    candidate: SceneCandidate,
    store: Store,
) -> tuple[Action, PlanStep]:
    """记录执行计划，准备输入变量。

    业务目标：在发起场景调用前，将执行意图（动作、输入变量、入参快照）完整记录到账本。
    当前动作：创建动作实体、保存输入变量和入参引用，将步骤和动作推进到 RUNNING 状态。
    预期结果：账本中有完整的执行计划和输入快照，可供审计和断点恢复。
    """
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
    """执行场景并记录尝试和观察。

    业务目标：实际调用场景服务获取造数结果，同时完整记录尝试状态和原始观察。
    当前动作：调用 run_action 执行场景，同步动作技术状态，保存尝试和观察到账本。
    预期结果：得到执行尝试（含成功/失败状态）和原始观察结果，全部记入账本。
    """
    from .execution import run_action

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
    """从观察中抽取可判定证据。

    业务目标：从原始观察结果中提取结构化事实，为后续结果判定提供依据。
    当前动作：调用 build_evidence 从观察和尝试中抽取已确认事实、缺失事实和未知事实。
    预期结果：得到一份结构化的证据记录，记入账本供判定使用。
    """
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
    """基于证据做出结果判定。

    业务目标：根据已收集的证据判定造数是否成功，给出明确的结果和原因。
    当前动作：调用 judge 根据证据和动作信息生成判定结论（成功/失败/需确认）。
    预期结果：得到一份结构化的判定记录，记入账本供后续收口使用。
    """
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
    """根据判定更新任务和步骤状态。

    业务目标：将判定结果落实到任务和步骤的最终状态上，让前端能正确展示任务结果。
    当前动作：调用 apply_verdict 根据判定类型更新任务、步骤和动作的业务状态。
    预期结果：任务状态被更新为完成、失败或需确认，步骤和动作状态同步收口。
    """
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
    """失败场景加入黑名单，避免重搜时再次推荐。

    业务目标：执行失败的场景不应在后续重搜中被重复推荐给用户，减少无效交互。
    当前动作：判定为失败时将场景编码加入需求缺口的黑名单。
    预期结果：后续搜索选定流程会排除黑名单中的场景。
    """
    if verdict.verdict_type != VerdictType.FAILED:
        return
    requirement = blacklist_scene(requirement, scene_code)
    store.save_requirement(requirement)


def _save_variables(store: Store, variables: list[Variable]) -> None:
    """将本次造数消费的业务数据持久化到账本，确保每个参数都有据可查。"""
    for variable in variables:
        store.save_variable(variable)


# ---------- Helpers ----------


def _candidate_of(proposal: RequirementProposal, scene_code: str) -> SceneCandidate | None:
    for candidate in proposal.candidates:
        if candidate.scene_code == scene_code:
            return candidate
    return None


def collect_preflight_missing(task_run: TaskRun, candidate: SceneCandidate) -> list[str]:
    """执行前检查缺失信息，避免在入参不全时盲目发起场景调用。

    业务目标：在调用场景前确认所有必填信息已齐全，缺失时直接暂停等用户补充，
    避免发起无效的远程调用。
    当前动作：检查环境编码（执行必需）和候选契约声明的缺失入参字段。
    预期结果：返回缺失字段列表，为空表示可以安全发起场景调用。
    """
    missing_fields: list[str] = []
    if _is_blank(task_run.env_code):
        missing_fields.append("env_code")
    for name in candidate.missing_inputs:
        missing_fields.append(f"inputs.{name}")
    return missing_fields


def _is_approved_request(inputs: dict[str, Any]) -> bool:
    """检查启动请求是否已携带用户审批。

    业务目标：尊重调用方在 start 阶段就携带审批结果的快捷路径，
    减少有副作用场景的交互轮次。
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
    """暂停造数任务并向用户展示待处理事项。

    业务目标：当系统遇到无法自动决策的环节（缺输入、需审批、选场景等）时，
    安全地暂停任务并向前端展示明确的提示信息，引导用户操作来恢复任务。
    当前动作：写入 pending_question 和 suspend_reason，将任务状态转为 WAITING_USER。
    预期结果：前端展示用户引导问题，用户可据此做出回复来恢复造数任务。
    """
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
    """判断任务暂停时用户主要需要做什么操作。

    业务目标：根据候选集的具体情况，给出最精确的挂起原因，
    让前端展示最贴合当前情况的引导提示（补参数/审批/选场景）。
    """
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
    """将动作的技术执行状态与尝试结果同步，确保用户看到的动作状态与实际执行一致。"""
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
    """检查任务是否已发起过场景调用，用于异常恢复时决定是否需要回滚账本。"""
    try:
        return bool(store.get_timeline(task_run_id)["attempts"])
    except (EntityNotFoundError, KeyError):
        return False
