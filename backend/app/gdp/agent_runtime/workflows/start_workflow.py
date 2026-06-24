"""任务启动与场景选择工作流。

本模块负责用户点击 start 后的编排：
创建步骤和资源缺口、解析显式场景、搜索候选、规则选定、审批前置校验，
最后把已选定场景交给 execution_pipeline 执行。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..adapters.catalog import SceneCatalogPort
from ..bindings import resolve_step_inputs
from ..domain.config_writeback import ConfigWritebackStatus
from ..domain.factories import create_single_step
from ..domain.transitions import transition_requirement, transition_step, transition_task_run
from ..ledger.refs import pending_start_ref
from ..models import (
    Action,
    Evidence,
    Observation,
    PlanStep,
    Requirement,
    RequirementStatus,
    SelectionSource,
    StepStatus,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
    Verdict,
)
from ..planner import PlanStepSpec, build_plan, create_plan_steps, plan_step_spec_ref
from ..ports.config_writeback import ConfigWritebackPort
from ..ports.idempotency import IdempotencyGate
from ..store import EntityNotFoundError, Store
from ..support.errors import RuntimeConflictError, RuntimeServiceError
from ..support.log_text import (
    describe_bool,
    describe_code,
    describe_content,
    describe_name_list,
    describe_optional,
)
from ..variables import extract_scene_output_variables
from .decision_records import (
    build_scene_search_decision,
    build_scene_selection_decision,
    build_user_scene_selection_decision,
)
from .scene_catalog import create_scene_requirement, resolve_explicit_scene, search_scenes
from .selection_gate import select_and_maybe_execute, suspend_for_selection_decision, suspend_for_user
from .selection_policy import decide_selection
from .source_infra_discovery import discover_source_and_infra_after_scene_miss

logger = logging.getLogger(__name__)


class StartTaskRunRequestLike(Protocol):
    """启动请求的最小结构，避免 workflow 反向依赖 API 层。"""

    scene_code: str | None
    inputs: dict[str, Any]


async def run_start_workflow(
    task_run: TaskRun,
    request: StartTaskRunRequestLike,
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None = None,
    config_writeback: ConfigWritebackPort | None = None,
) -> TaskRun:
    """主循环入口：让用户的造数需求被完整处理。"""

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

    try:
        # 根据是否指定场景编码走不同路径：快速通道或智能搜索。
        if scene_code:
            step = create_single_step(task_run)
            requirement = create_scene_requirement(task_run, step)
            logger.info(
                "GDP Agent 运行时计划步骤已创建：任务ID=%s，步骤ID=%s，缺口ID=%s，任务目标=%s",
                task_run.task_run_id,
                step.step_id,
                requirement.requirement_id,
                step.goal,
            )
            return await _run_explicit_scene(
                task_run,
                step,
                requirement,
                scene_code,
                request.inputs,
                store,
                catalog,
                idempotency_gate,
            )

        specs = build_plan(task_run.user_goal, request.inputs)
        if len(specs) > 1:
            create_plan_steps(task_run, specs, store)
            return await _run_multistep(task_run, request.inputs, store, catalog, idempotency_gate, config_writeback)

        step = create_single_step(task_run)
        requirement = create_scene_requirement(task_run, step)
        logger.info(
            "GDP Agent 运行时计划步骤已创建：任务ID=%s，步骤ID=%s，缺口ID=%s，任务目标=%s",
            task_run.task_run_id,
            step.step_id,
            requirement.requirement_id,
            step.goal,
        )
        return await _run_search(
            task_run,
            step,
            requirement,
            request.inputs,
            store,
            catalog,
            idempotency_gate,
            config_writeback,
        )
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


async def _run_explicit_scene(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
    complete_task_run: bool = True,
) -> TaskRun:
    """用户已指定场景编码时的快速通道——解析契约确认入参齐全后直接执行。"""

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

    return await select_and_maybe_execute(
        task_run,
        step,
        requirement,
        proposal,
        scene_code,
        inputs,
        SelectionSource.EXPLICIT,
        _is_approved_request(inputs),
        store,
        idempotency_gate,
        complete_task_run=complete_task_run,
    )


async def _run_search(
    task_run: TaskRun,
    step: PlanStep,
    requirement: Requirement,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
    config_writeback: ConfigWritebackPort | None,
    complete_task_run: bool = True,
) -> TaskRun:
    """用户未指定场景时的智能搜索——调场景目录搜索、规则选择、必要时暂停等用户。"""

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
        # 搜索无结果：先保留原 Scene 缺口事实，再尝试只读向下发现 Source / Infra。
        store.save_requirement(requirement)  # 仍 PENDING，不转 RESOLVING
        discovery = await discover_source_and_infra_after_scene_miss(
            task_run,
            step,
            requirement,
            inputs,
            store,
            catalog,
            config_writeback,
        )
        if _writeback_succeeded(discovery):
            scene_code = discovery.writeback_result.target_code
            proposal = await resolve_explicit_scene(requirement, scene_code, inputs, catalog)
            store.save_proposal(proposal)
            requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
            store.save_requirement(requirement)
            return await select_and_maybe_execute(
                task_run,
                step,
                requirement,
                proposal,
                scene_code,
                inputs,
                SelectionSource.AUTO,
                _is_approved_request(inputs),
                store,
                idempotency_gate,
                complete_task_run=complete_task_run,
            )
        return suspend_for_user(
            task_run,
            step,
            discovery.question if discovery else outcome.question,
            SuspendReason.NEED_SCENE_SELECTION,
            store,
        )

    # 有候选时转入 RESOLVING，语义是"已有候选，正在选定中"。
    requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
    store.save_requirement(requirement)

    if outcome.kind == "AUTO_SELECTED":
        # 规则自动选定唯一候选，直接进入执行链路。
        return await select_and_maybe_execute(
            task_run,
            step,
            requirement,
            proposal,
            outcome.scene_code,
            inputs,
            SelectionSource.AUTO,
            _is_approved_request(inputs),
            store,
            idempotency_gate,
            complete_task_run=complete_task_run,
        )

    # NEED_USER：多候选、低分、缺参或需审批时，暂停等用户选择或批准后继续。
    return suspend_for_selection_decision(task_run, step, requirement, proposal, outcome.question, store)


async def _run_multistep(
    task_run: TaskRun,
    request_inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
    config_writeback: ConfigWritebackPort | None,
) -> TaskRun:
    """按 active_step_id 串行推进多步骤计划。"""

    return await continue_multistep(
        task_run,
        request_inputs,
        store,
        catalog,
        idempotency_gate,
        config_writeback,
        run_active_step=True,
    )


async def continue_multistep(
    task_run: TaskRun,
    request_inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
    config_writeback: ConfigWritebackPort | None = None,
    *,
    run_active_step: bool = False,
) -> TaskRun:
    """从当前 active_step_id 继续多步骤计划，可用于 start 和 reply 恢复。"""

    should_run_active_step = run_active_step
    while True:
        step = _get_active_step(task_run, store)
        spec = _get_step_spec(task_run, step, store)
        if should_run_active_step:
            task_run = await _run_plan_step(
                task_run,
                step,
                spec,
                request_inputs,
                store,
                catalog,
                idempotency_gate,
                config_writeback,
            )
            if task_run.status != TaskRunStatus.RUNNING:
                return task_run

            step = store.get_step(step.step_id)
        elif task_run.status != TaskRunStatus.RUNNING:
            return task_run

        if step.status != StepStatus.DONE:
            return task_run

        if spec.output_bindings:
            try:
                action, evidence, observation = _latest_success_context(step, store)
                extract_scene_output_variables(task_run, step, action, evidence, observation, spec.output_bindings, store)
            except ValueError as exc:
                # Verdict DONE 只证明场景执行成功；计划必需产出缺失时，业务步骤要修正为失败。
                step.status = StepStatus.FAILED
                store.save_step(step)
                task_run.failure_reason = str(exc)
                task_run = transition_task_run(task_run, TaskRunStatus.FAILED)
                store.save_task_run(task_run)
                return task_run

        next_step = _next_pending_step(task_run, store)
        if next_step is None:
            final_step = _final_assertion_step(task_run, store)
            task_run.final_verdict_id = final_step.verdict_id
            task_run = transition_task_run(task_run, TaskRunStatus.COMPLETED)
            store.save_task_run(task_run)
            return task_run

        task_run.active_step_id = next_step.step_id
        store.save_task_run(task_run)
        should_run_active_step = True


async def _run_plan_step(
    task_run: TaskRun,
    step: PlanStep,
    spec: PlanStepSpec,
    request_inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    idempotency_gate: IdempotencyGate | None,
    config_writeback: ConfigWritebackPort | None,
) -> TaskRun:
    """推进当前 PlanStep：绑定输入、搜索场景、选择并执行。"""

    resolution = resolve_step_inputs(task_run, step, spec.input_bindings, request_inputs, store)
    if resolution.missing_inputs:
        return suspend_for_user(
            task_run,
            step,
            "缺少必填信息：" + "，".join(f"inputs.{name}" for name in resolution.missing_inputs) + "。请补充后继续。",
            SuspendReason.MISSING_INPUT,
            store,
        )
    if resolution.missing_variables:
        step = transition_step(step, StepStatus.RUNNING)
        step = transition_step(step, StepStatus.FAILED)
        store.save_step(step)
        task_run.failure_reason = "计划变量缺失：" + "，".join(resolution.missing_variables)
        task_run = transition_task_run(task_run, TaskRunStatus.FAILED)
        store.save_task_run(task_run)
        return task_run

    requirement = create_scene_requirement(task_run, step)
    return await _run_search(
        task_run,
        step,
        requirement,
        resolution.inputs,
        store,
        catalog,
        idempotency_gate,
        config_writeback,
        complete_task_run=False,
    )


def _get_active_step(task_run: TaskRun, store: Store) -> PlanStep:
    if task_run.active_step_id is None:
        raise RuntimeConflictError("TaskRun 缺少 active_step_id")
    return store.get_step(task_run.active_step_id)


def _get_step_spec(task_run: TaskRun, step: PlanStep, store: Store) -> PlanStepSpec:
    payload = store.get_payload(task_run.task_run_id, plan_step_spec_ref(step.step_id))
    return PlanStepSpec.model_validate(payload)


def _next_pending_step(task_run: TaskRun, store: Store) -> PlanStep | None:
    steps = [store.get_step(step_id) for step_id in task_run.step_ids]
    for step in sorted(steps, key=lambda item: item.step_no):
        if step.status != StepStatus.PENDING:
            continue
        if all(store.get_step(depends_on).status == StepStatus.DONE for depends_on in step.depends_on):
            return step
    return None


def _final_assertion_step(task_run: TaskRun, store: Store) -> PlanStep:
    steps = [store.get_step(step_id) for step_id in task_run.step_ids]
    return max(steps, key=lambda item: item.step_no)


def _latest_success_context(step: PlanStep, store: Store) -> tuple[Action, Evidence, Observation]:
    if not step.action_ids or not step.verdict_id:
        raise ValueError("步骤缺少成功执行上下文。")
    action = store.get_action(step.action_ids[-1])
    verdict: Verdict = store.get_verdict(step.verdict_id)
    evidence = store.get_evidence(verdict.evidence_id)
    observation_id = _first_observation_id(evidence)
    observation = store.get_observation(observation_id)
    return action, evidence, observation


def _first_observation_id(evidence: Evidence) -> str:
    for fact in evidence.facts:
        return fact.source_observation_id
    raise ValueError("步骤缺少可追溯观察。")


def _writeback_succeeded(discovery: object | None) -> bool:
    """判断 Source/Infra 发现是否已经成功发布可执行 Scene。"""
    if discovery is None:
        return False
    result = getattr(discovery, "writeback_result", None)
    return result is not None and result.status == ConfigWritebackStatus.SUCCESS and bool(result.target_code)


def _is_approved_request(inputs: dict[str, Any]) -> bool:
    """检查启动请求是否已携带用户审批。"""

    return inputs.get("approved") is True


def _has_attempts(store: Store, task_run_id: str) -> bool:
    """检查任务是否已发起过场景调用，用于异常恢复时决定是否需要回滚账本。"""

    try:
        return bool(store.get_timeline(task_run_id)["attempts"])
    except (EntityNotFoundError, KeyError):
        return False
