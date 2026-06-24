"""用户回复恢复工作流。

本模块收拢 WAITING_USER 任务的恢复编排：
补输入、选场景、补场景编码、审批和确认未知结果都在这里处理。
RuntimeService 只负责加载账本、权限校验和持久化边界。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ..bindings import resolve_step_inputs
from ..domain.transitions import transition_requirement, transition_task_run
from ..ledger.refs import pending_start_ref
from ..models import (
    PlanStep,
    ProposalStatus,
    Requirement,
    RequirementLayer,
    RequirementProposal,
    RequirementStatus,
    SceneCandidate,
    SelectionSource,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
)
from ..planner import PlanStepSpec, plan_step_spec_ref
from ..ports.idempotency import IdempotencyGate
from ..store import EntityNotFoundError, Store
from ..support.errors import RuntimeConflictError, RuntimeValidationError
from .decision_records import build_approval_requirement_decision, build_user_scene_selection_decision
from .execution_pipeline import collect_preflight_missing, execute_scene
from .reply_commands import (
    AcceptContractDriftCommand,
    ApproveCommand,
    ConfirmUnknownStateCommand,
    RuntimeCommand,
    SelectSceneCommand,
    SupplyInputCommand,
    SupplySceneCodeCommand,
)
from .scene_catalog import resolve_explicit_scene
from .selection_policy import apply_selection, ensure_selection_consistency
from .start_workflow import continue_multistep

ReplyHandler = Callable[[TaskRun, RuntimeCommand, Store, IdempotencyGate | None], Awaitable[TaskRun]]


async def handle_reply(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None = None,
) -> TaskRun:
    """按用户回复类型恢复暂停任务。"""

    handler = _REPLY_HANDLERS[type(command)]
    return await handler(task_run, command, store, idempotency_gate)


async def _handle_confirm_unknown_state(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户确认 UNKNOWN_STATE 实际结果后的双路径对账。

    - actual_outcome=FAILED（或缺省）：维持失败收口，避免重放写请求。
    - actual_outcome=SUCCEEDED：用户须指定只读核查场景 verify_scene_code，
      系统执行该 QUERY 场景取证据 judge——证据证明成功才推进，绝不靠用户断言写 DONE。
    - actual_outcome=UNCERTAIN：维持 WAITING_USER 等更多信息。
    """

    latest_verdict_type = _latest_verdict_type(task_run.task_run_id, store)
    if latest_verdict_type != "UNKNOWN_STATE":
        raise RuntimeConflictError("当前 TaskRun 不是执行结果未知状态，不能确认 UNKNOWN_STATE")

    actual_outcome = _unknown_state_outcome(command.payload)

    if actual_outcome == "SUCCEEDED":
        return await _reconcile_unknown_state_success(task_run, command, store, idempotency_gate)

    if actual_outcome == "UNCERTAIN":
        # 用户仍无法确认，保持挂起等待更多信息，不改终态。
        store.save_task_run(task_run)
        return task_run

    # FAILED（含缺省）：维持现有失败收口。
    task_run.pending_question = None
    task_run.suspend_reason = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    task_run.failure_reason = _format_unknown_state_confirmation(command.payload)
    task_run = transition_task_run(task_run, TaskRunStatus.FAILED)
    store.save_task_run(task_run)
    return task_run


async def _reconcile_unknown_state_success(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户确认实际成功：执行用户指定的只读核查场景，用证据判定是否真的完成。"""

    verify_scene_code = _strip_optional(command.payload.get("verify_scene_code"))
    if verify_scene_code is None:
        raise RuntimeValidationError(
            "确认实际成功必须提供 verify_scene_code（只读核查场景），系统据其取证判定，不接受无证据的成功断言"
        )

    requirement = _get_waiting_requirement(task_run, store)
    step = store.get_step(requirement.step_id)
    verify_inputs = _merge_reply_inputs(task_run, command.payload, store)

    # 解析核查场景契约并写入账本（独立于原写场景缺口的已选定场景）。
    verify_proposal = await resolve_explicit_scene(requirement, verify_scene_code, verify_inputs, _get_scene_catalog())
    verify_candidate = next(
        (item for item in verify_proposal.candidates if item.scene_code == verify_scene_code),
        None,
    )
    if verify_candidate is None:
        raise RuntimeValidationError("核查场景契约解析失败")

    task_run.pending_question = None
    task_run.suspend_reason = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)

    # 跳过"执行目标=缺口已选定场景"校验：核查场景与原写场景不同，但证据仍判定原步骤。
    task_run = await execute_scene(
        task_run,
        step,
        requirement,
        verify_scene_code,
        verify_inputs,
        verify_candidate,
        store,
        idempotency_gate,
        complete_task_run=not _is_multistep_task(task_run),
        skip_requirement_match=True,
    )
    if not _is_multistep_task(task_run):
        return task_run
    # 多步任务：核查步骤判定 DONE 后继续推进后续 step（单步任务已在 execute_scene 内收口）。
    return await continue_multistep(
        task_run,
        verify_inputs,
        store,
        _get_scene_catalog(),
        idempotency_gate,
    )


async def _handle_supply_input(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户补充缺失的输入后继续任务，核心保护是已有写请求时不允许重放。"""

    if _has_write_attempts_for_reply(task_run, store):
        raise RuntimeConflictError("当前 TaskRun 已发起写请求，不能通过 SUPPLY_INPUT 重放")

    pending_start = _get_pending_start(task_run, store)
    scene_code = _strip_optional(pending_start.get("scene_code"))

    _merge_env_code(task_run, command.payload)
    inputs = _merge_supplied_inputs(pending_start.get("inputs"), command.payload)
    store.save_payload(
        task_run.task_run_id,
        pending_start_ref(task_run.task_run_id),
        {"scene_code": scene_code, "inputs": inputs},
    )

    requirement = _get_waiting_scene_requirement(task_run, store)
    proposal = store.get_latest_proposal(
        task_run.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
    )
    if proposal is None:
        raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Proposal")

    extra_input_names = set(_supplied_input_names(command.payload))
    if proposal.status == ProposalStatus.SELECTED:
        selected_scene_code = proposal.selected_scene_code or scene_code
        if selected_scene_code is None:
            raise RuntimeConflictError("当前已选定 Proposal 缺少 scene_code")
        ensure_selection_consistency(requirement, proposal, selected_scene_code)
        extra_input_names.update(_proposal_missing_inputs(proposal, selected_scene_code))
        contract_inputs = _execution_inputs_for_contract_refresh(
            task_run,
            requirement,
            inputs,
            extra_input_names,
            store,
        )
        if isinstance(contract_inputs, TaskRun):
            return contract_inputs
        candidate = await _refresh_candidate_contract(proposal, selected_scene_code, contract_inputs, store)
    elif proposal.status == ProposalStatus.PENDING and len(proposal.candidates) == 1:
        selected_scene_code = proposal.candidates[0].scene_code
        extra_input_names.update(_proposal_missing_inputs(proposal, selected_scene_code))
        contract_inputs = _execution_inputs_for_contract_refresh(
            task_run,
            requirement,
            inputs,
            extra_input_names,
            store,
        )
        if isinstance(contract_inputs, TaskRun):
            return contract_inputs
        candidate = await _refresh_candidate_contract(proposal, selected_scene_code, contract_inputs, store)
        if requirement.status == RequirementStatus.PENDING:
            requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
        requirement, proposal = apply_selection(requirement, proposal, candidate.scene_code, SelectionSource.AUTO)
        requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
        store.save_requirement(requirement)
        store.save_proposal(proposal)
    else:
        raise RuntimeConflictError("当前 TaskRun 仍需先选择可恢复的场景")

    scene_code = candidate.scene_code
    store.save_payload(
        task_run.task_run_id,
        pending_start_ref(task_run.task_run_id),
        {"scene_code": scene_code, "inputs": inputs},
    )

    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        task_run.suspend_reason = SuspendReason.MISSING_INPUT
        store.save_task_run(task_run)
        return task_run

    if candidate.requires_confirmation and not store.has_approval_record(task_run.task_run_id, candidate.scene_code):
        task_run.pending_question = (
            f"场景 {candidate.scene_name}（{candidate.scene_code}）已具备必填输入，但执行有写副作用。请批准后继续。"
        )
        task_run.suspend_reason = SuspendReason.NEED_APPROVAL
        store.save_task_run(task_run)
        return task_run

    return await _execute_selected_scene(
        task_run,
        requirement,
        candidate.scene_code,
        inputs,
        candidate,
        store,
        idempotency_gate,
        extra_input_names=extra_input_names,
    )


async def _handle_select_scene(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户在候选列表中选定场景后继续执行。"""

    requirement = _get_waiting_requirement(task_run, store)
    proposal = _get_waiting_proposal(task_run, store, requirement.requirement_id)
    scene_code = _require_scene_code(command.payload)
    inputs = _merge_reply_inputs(task_run, command.payload, store)

    candidate = next((item for item in proposal.candidates if item.scene_code == scene_code), None)
    if candidate is None:
        raise RuntimeValidationError("payload.scene_code 不在最近候选内")

    if requirement.status == RequirementStatus.PENDING:
        requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)

    requirement, proposal = apply_selection(requirement, proposal, scene_code, SelectionSource.USER)
    requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
    store.save_requirement(requirement)
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

    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        task_run.suspend_reason = SuspendReason.MISSING_INPUT
        store.save_task_run(task_run)
        return task_run

    approved = command.payload.get("approved") is True
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
        task_run.pending_question = f"场景 {candidate.scene_name}（{candidate.scene_code}）已选定，但执行有写副作用。请批准后继续。"
        task_run.suspend_reason = SuspendReason.NEED_APPROVAL
        store.save_task_run(task_run)
        return task_run

    if candidate.requires_confirmation:
        _save_approval_record(store, task_run.task_run_id, requirement.requirement_id, proposal.proposal_id, candidate.scene_code)
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                candidate,
                approved=True,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )

    return await _execute_selected_scene(
        task_run,
        requirement,
        scene_code,
        inputs,
        candidate,
        store,
        idempotency_gate,
        extra_input_names=_supplied_input_names(command.payload),
        verify_drift=True,
    )


async def _handle_supply_scene_code(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """零候选时用户手动指定场景编码，系统解析并继续执行。"""

    requirement = _get_waiting_requirement(task_run, store)
    proposal = _get_waiting_proposal(task_run, store, requirement.requirement_id)
    if proposal.candidates:
        raise RuntimeConflictError("当前不是零候选等待状态，不能 SUPPLY_SCENE_CODE")

    scene_code = _require_scene_code(command.payload)
    inputs = _merge_reply_inputs(task_run, command.payload, store)

    proposal = await resolve_explicit_scene(requirement, scene_code, inputs, _get_scene_catalog())
    resolved = proposal.candidates[0]
    store.save_proposal(proposal)
    if requirement.status == RequirementStatus.PENDING:
        requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
    requirement, proposal = apply_selection(requirement, proposal, scene_code, SelectionSource.USER)
    requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
    store.save_requirement(requirement)
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

    missing_fields = collect_preflight_missing(task_run, resolved)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        task_run.suspend_reason = SuspendReason.MISSING_INPUT
        store.save_task_run(task_run)
        return task_run

    approved = command.payload.get("approved") is True
    if resolved.requires_confirmation and not approved:
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                resolved,
                approved=False,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )
        task_run.pending_question = f"场景 {resolved.scene_name}（{resolved.scene_code}）已补录，但执行有写副作用。请批准后继续。"
        task_run.suspend_reason = SuspendReason.NEED_APPROVAL
        store.save_task_run(task_run)
        return task_run

    if resolved.requires_confirmation:
        _save_approval_record(store, task_run.task_run_id, requirement.requirement_id, proposal.proposal_id, resolved.scene_code)
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                resolved,
                approved=True,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )

    return await _execute_selected_scene(
        task_run,
        requirement,
        scene_code,
        inputs,
        resolved,
        store,
        idempotency_gate,
        extra_input_names=_supplied_input_names(command.payload),
    )


async def _handle_approve_scene(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户批准有写副作用的场景后继续执行。"""

    requirement = _get_waiting_requirement(task_run, store)
    proposal = _get_latest_selected_proposal(task_run, store, requirement.requirement_id)
    if proposal.selected_scene_code is None:
        raise RuntimeConflictError("当前没有待审批的已选定场景")

    candidate = next((item for item in proposal.candidates if item.scene_code == proposal.selected_scene_code), None)
    if candidate is None or not candidate.requires_confirmation:
        raise RuntimeConflictError("当前 TaskRun 没有等待审批的候选")
    ensure_selection_consistency(requirement, proposal, proposal.selected_scene_code)
    if store.has_approval_record(task_run.task_run_id, proposal.selected_scene_code):
        raise RuntimeConflictError("该场景已经审批，无需重复 APPROVE")

    inputs = _merge_reply_inputs(task_run, command.payload, store)
    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        task_run.suspend_reason = SuspendReason.MISSING_INPUT
        store.save_task_run(task_run)
        return task_run

    _save_approval_record(
        store,
        task_run.task_run_id,
        requirement.requirement_id,
        proposal.proposal_id,
        proposal.selected_scene_code,
    )
    store.save_decision(
        build_approval_requirement_decision(
            task_run,
            requirement,
            proposal,
            candidate,
            approved=True,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )
    return await _execute_selected_scene(
        task_run,
        requirement,
        proposal.selected_scene_code,
        inputs,
        candidate,
        store,
        idempotency_gate,
        extra_input_names=_supplied_input_names(command.payload),
        verify_drift=True,
    )


async def _handle_accept_contract_drift(
    task_run: TaskRun,
    command: RuntimeCommand,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
) -> TaskRun:
    """用户接受执行前重验发现的新契约后，按新契约继续执行。

    刷新候选契约（写回新哈希）后直接执行，不再重验漂移——用户已确认接受新契约。
    """

    if task_run.suspend_reason != SuspendReason.CONTRACT_DRIFT:
        raise RuntimeConflictError("当前任务不在契约漂移待确认状态")

    requirement = _get_waiting_requirement(task_run, store)
    proposal = _get_latest_selected_proposal(task_run, store, requirement.requirement_id)
    scene_code = proposal.selected_scene_code
    if scene_code is None:
        raise RuntimeConflictError("当前没有已选定的漂移场景")

    inputs = _merge_reply_inputs(task_run, command.payload, store)
    candidate = await _refresh_candidate_contract(proposal, scene_code, inputs, store)

    return await _execute_selected_scene(
        task_run,
        requirement,
        scene_code,
        inputs,
        candidate,
        store,
        idempotency_gate,
        extra_input_names=_supplied_input_names(command.payload),
        verify_drift=False,
    )


def _get_pending_start(task_run: TaskRun, store: Store) -> dict[str, Any]:
    """取出用户上次暂停时保存的启动请求快照，用于恢复执行上下文。"""

    try:
        pending_start = store.get_payload(task_run.task_run_id, pending_start_ref(task_run.task_run_id))
    except EntityNotFoundError as exc:
        raise RuntimeConflictError("找不到可恢复的启动请求") from exc
    if not isinstance(pending_start, dict):
        raise RuntimeConflictError("待恢复启动请求格式无效")
    return pending_start


def _merge_supplied_inputs(pending_inputs: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """将用户新补充的输入与历史输入合并，新值覆盖同名旧值。"""

    base_inputs = pending_inputs if isinstance(pending_inputs, dict) else {}
    supplied_inputs = payload.get("inputs")
    if supplied_inputs is None:
        supplied_inputs = {
            key: value
            for key, value in payload.items()
            if key not in {"env_code", "message", "scene_code", "approved"}
        }
    if not isinstance(supplied_inputs, dict):
        raise RuntimeValidationError("payload.inputs 必须是对象")
    return {**base_inputs, **supplied_inputs}


def _latest_verdict_type(task_run_id: str, store: Store) -> str | None:
    """获取任务最近一次执行结果判定类型，用于确认当前是否处于 UNKNOWN_STATE。"""

    verdicts = store.get_timeline(task_run_id)["verdicts"]
    if not verdicts:
        return None
    verdict_type = verdicts[-1].get("verdict_type")
    return verdict_type if isinstance(verdict_type, str) else None


def _has_write_attempts(task_run_id: str, store: Store) -> bool:
    """检查任务是否已发起过执行尝试，用于决定是否允许重放写请求。"""

    return bool(store.get_timeline(task_run_id)["attempts"])


def _has_write_attempts_for_reply(task_run: TaskRun, store: Store) -> bool:
    """补参重放保护：多步骤只检查当前 active step，单步骤保持任务级保护。"""

    if not _is_multistep_task(task_run):
        return _has_write_attempts(task_run.task_run_id, store)
    if task_run.active_step_id is None:
        return _has_write_attempts(task_run.task_run_id, store)
    step = store.get_step(task_run.active_step_id)
    if not step.action_ids:
        return False
    actions = {
        action["action_id"]: action
        for action in store.get_timeline(task_run.task_run_id)["actions"]
        if action.get("action_id") in step.action_ids
    }
    return any(action.get("attempt_ids") for action in actions.values())


async def _execute_selected_scene(
    task_run: TaskRun,
    requirement: Requirement,
    scene_code: str,
    request_inputs: dict[str, Any],
    candidate: SceneCandidate,
    store: Store,
    idempotency_gate: IdempotencyGate | None,
    *,
    extra_input_names: set[str] | list[str] | tuple[str, ...] = (),
    verify_drift: bool = False,
) -> TaskRun:
    """执行当前选定场景；多步骤完成当前步骤后继续推进后续步骤。

    verify_drift=True 时（select_scene / approve 恢复路径，候选快照来自更早的请求），
    执行前重新解析契约并比对哈希，检测漂移则阻断等用户确认。
    supply_scene_code / supply_input 路径在同一请求内刚解析过契约，无需重验。
    """

    step = store.get_step(requirement.step_id)
    execution_inputs = request_inputs
    complete_task_run = True
    if _is_multistep_task(task_run):
        prepared = _prepare_multistep_execution_inputs(task_run, requirement, request_inputs, extra_input_names, store)
        if isinstance(prepared, TaskRun):
            return prepared
        step, execution_inputs = prepared
        complete_task_run = False

    task_run.pending_question = None
    task_run.suspend_reason = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    task_run = await execute_scene(
        task_run,
        step,
        requirement,
        scene_code,
        execution_inputs,
        candidate,
        store,
        idempotency_gate,
        complete_task_run=complete_task_run,
        catalog=_get_scene_catalog() if verify_drift else None,
    )
    if not _is_multistep_task(task_run):
        return task_run
    return await continue_multistep(
        task_run,
        request_inputs,
        store,
        _get_scene_catalog(),
        idempotency_gate,
    )


def _execution_inputs_for_contract_refresh(
    task_run: TaskRun,
    requirement: Requirement,
    request_inputs: dict[str, Any],
    extra_input_names: set[str],
    store: Store,
) -> dict[str, Any] | TaskRun:
    """刷新候选契约前，按当前步骤快照组装真实步骤入参。"""

    if not _is_multistep_task(task_run):
        return request_inputs
    prepared = _prepare_multistep_execution_inputs(task_run, requirement, request_inputs, extra_input_names, store)
    if isinstance(prepared, TaskRun):
        return prepared
    _, execution_inputs = prepared
    return execution_inputs


def _prepare_multistep_execution_inputs(
    task_run: TaskRun,
    requirement: Requirement,
    request_inputs: dict[str, Any],
    extra_input_names: set[str] | list[str] | tuple[str, ...],
    store: Store,
) -> tuple[PlanStep, dict[str, Any]] | TaskRun:
    """从 PlanStepSpec 快照重新解析当前步骤入参，避免 reply 依赖旧内存计划。"""

    step = store.get_step(requirement.step_id)
    spec = _get_step_spec_or_fail(task_run, step, store)
    if isinstance(spec, TaskRun):
        return spec

    resolution = resolve_step_inputs(task_run, step, spec.input_bindings, request_inputs, store)
    if resolution.missing_inputs:
        return _keep_waiting_for_missing_inputs(task_run, step, resolution.missing_inputs, store)
    if resolution.missing_variables:
        return _fail_waiting_task_run(task_run, "计划变量缺失：" + "，".join(resolution.missing_variables), store)

    execution_inputs = dict(resolution.inputs)
    for name in extra_input_names:
        if name in request_inputs and not _is_blank(request_inputs[name]):
            execution_inputs[name] = request_inputs[name]
    return step, execution_inputs


def _get_step_spec_or_fail(task_run: TaskRun, step: PlanStep, store: Store) -> PlanStepSpec | TaskRun:
    """读取当前步骤规格快照；缺失时失败收口，不重新 build_plan 猜测。"""

    try:
        payload = store.get_payload(task_run.task_run_id, plan_step_spec_ref(step.step_id))
        return PlanStepSpec.model_validate(payload)
    except (EntityNotFoundError, ValidationError):
        return _fail_waiting_task_run(task_run, "计划步骤快照缺失，无法恢复当前步骤。", store)


def _keep_waiting_for_missing_inputs(
    task_run: TaskRun,
    step: PlanStep,
    missing_inputs: list[str],
    store: Store,
) -> TaskRun:
    """当前步骤绑定仍缺用户输入时保持 WAITING_USER。"""

    task_run.pending_question = "缺少必填信息：" + "，".join(f"inputs.{name}" for name in missing_inputs) + "。请补充后继续。"
    task_run.suspend_reason = SuspendReason.MISSING_INPUT
    store.save_step(step)
    store.save_task_run(task_run)
    return task_run


def _fail_waiting_task_run(
    task_run: TaskRun,
    reason: str,
    store: Store,
) -> TaskRun:
    """WAITING_USER 恢复遇到不可恢复账本问题时，按状态机先恢复运行再失败收口。"""

    task_run.pending_question = None
    task_run.suspend_reason = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    task_run.failure_reason = reason
    task_run = transition_task_run(task_run, TaskRunStatus.FAILED)
    store.save_task_run(task_run)
    return task_run


def _is_multistep_task(task_run: TaskRun) -> bool:
    return len(task_run.step_ids) > 1


def _supplied_input_names(payload: dict[str, Any]) -> set[str]:
    supplied_inputs = payload.get("inputs")
    if isinstance(supplied_inputs, dict):
        return {str(key) for key in supplied_inputs}
    return {
        str(key)
        for key in payload
        if key not in {"env_code", "message", "scene_code", "approved"}
    }


def _proposal_missing_inputs(proposal: RequirementProposal, scene_code: str) -> set[str]:
    for candidate in proposal.candidates:
        if candidate.scene_code == scene_code:
            return {_strip_input_prefix(name) for name in candidate.missing_inputs}
    return set()


def _strip_input_prefix(name: str) -> str:
    return name.removeprefix("inputs.")


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _unknown_state_outcome(payload: dict[str, Any]) -> str:
    """解析用户对 UNKNOWN_STATE 的实际结果判断。

    缺省为 FAILED：保持历史"确认即失败收口"语义，向后兼容旧客户端。
    取值：SUCCEEDED / FAILED / UNCERTAIN。
    """

    raw = payload.get("actual_outcome")
    if not isinstance(raw, str):
        return "FAILED"
    normalized = raw.strip().upper()
    if normalized in {"SUCCEEDED", "FAILED", "UNCERTAIN"}:
        return normalized
    raise RuntimeValidationError("payload.actual_outcome 取值必须是 SUCCEEDED / FAILED / UNCERTAIN 之一")


def _format_unknown_state_confirmation(payload: dict[str, Any]) -> str:
    """格式化用户确认执行结果未知时的失败原因说明。"""

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return "用户确认执行结果未知，任务已停止以避免重复写请求。用户说明：" + message.strip()
    return "用户确认执行结果未知，任务已停止以避免重复写请求。"


def _format_missing_required_question(missing_fields: list[str]) -> str:
    """将缺失的必填字段列表格式化为面向用户的提示语。"""

    return "缺少必填信息：" + "，".join(missing_fields) + "。请补充后继续。"


def _require_scene_code(payload: dict[str, Any]) -> str:
    """从用户回复中提取并校验场景编码，必须是非空字符串。"""

    scene_code = payload.get("scene_code")
    if not isinstance(scene_code, str) or not scene_code.strip():
        raise RuntimeValidationError("payload.scene_code 必须是非空字符串")
    return scene_code.strip()


def _strip_optional(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _get_waiting_requirement(task_run: TaskRun, store: Store) -> Requirement:
    requirement = store.get_active_requirement(task_run.task_run_id, step_id=task_run.active_step_id)
    if requirement is None:
        raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Requirement")
    return requirement


def _get_waiting_scene_requirement(task_run: TaskRun, store: Store) -> Requirement:
    requirements = [
        item
        for item in store.list_requirements(task_run.task_run_id)
        if item.step_id == task_run.active_step_id and item.layer == RequirementLayer.SCENE
    ]
    if not requirements:
        raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Scene Requirement")
    return max(requirements, key=lambda item: item.created_at)


def _get_waiting_proposal(task_run: TaskRun, store: Store, requirement_id: str) -> RequirementProposal:
    proposal = store.get_latest_proposal(
        task_run.task_run_id,
        step_id=task_run.active_step_id,
        requirement_id=requirement_id,
    )
    if proposal is None or proposal.requirement_id != requirement_id:
        raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Proposal")
    if proposal.status != ProposalStatus.PENDING:
        raise RuntimeConflictError("最近候选集已不是待选择状态")
    return proposal


def _get_latest_selected_proposal(task_run: TaskRun, store: Store, requirement_id: str) -> RequirementProposal:
    proposal = store.get_latest_proposal(
        task_run.task_run_id,
        step_id=task_run.active_step_id,
        requirement_id=requirement_id,
    )
    if proposal is None or proposal.requirement_id != requirement_id:
        raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Proposal")
    if proposal.status != ProposalStatus.SELECTED:
        raise RuntimeConflictError("当前没有已选定且待审批的 Proposal")
    return proposal


def _merge_reply_inputs(task_run: TaskRun, payload: dict[str, Any], store: Store) -> dict[str, Any]:
    pending_start = _get_pending_start(task_run, store)
    _merge_env_code(task_run, payload)
    inputs = _merge_supplied_inputs(pending_start.get("inputs"), payload)
    store.save_payload(
        task_run.task_run_id,
        pending_start_ref(task_run.task_run_id),
        {"scene_code": payload.get("scene_code", pending_start.get("scene_code")), "inputs": inputs},
    )
    return inputs


def _merge_env_code(task_run: TaskRun, payload: dict[str, Any]) -> None:
    supplied_env_code = payload.get("env_code")
    if supplied_env_code is None:
        return
    if not isinstance(supplied_env_code, str) or not supplied_env_code.strip():
        raise RuntimeValidationError("payload.env_code 必须是非空字符串")
    task_run.env_code = supplied_env_code.strip()


async def _refresh_candidate_contract(
    proposal: RequirementProposal,
    scene_code: str,
    inputs: dict[str, Any],
    store: Store,
) -> SceneCandidate:
    """按最新输入刷新候选契约，并写回当前 Proposal。"""

    candidate = await _get_scene_catalog().get_contract(scene_code=scene_code, user_inputs=inputs)
    proposal.candidates = [
        candidate if item.scene_code == scene_code else item
        for item in proposal.candidates
    ]
    if all(item.scene_code != scene_code for item in proposal.candidates):
        proposal.candidates.append(candidate)
    store.save_proposal(proposal)
    return candidate


def _save_approval_record(
    store: Store,
    task_run_id: str,
    requirement_id: str,
    proposal_id: str,
    scene_code: str,
) -> None:
    store.save_approval_record(
        {
            "task_run_id": task_run_id,
            "requirement_id": requirement_id,
            "proposal_id": proposal_id,
            "scene_code": scene_code,
            "approved_by": "USER",
            "approved_at": datetime.now(UTC).isoformat(),
        }
    )


def _get_scene_catalog():
    from .. import runner as runtime_runner

    return runtime_runner.get_catalog()


_REPLY_HANDLERS: dict[type[RuntimeCommand], ReplyHandler] = {
    ConfirmUnknownStateCommand: _handle_confirm_unknown_state,
    SupplyInputCommand: _handle_supply_input,
    SelectSceneCommand: _handle_select_scene,
    SupplySceneCodeCommand: _handle_supply_scene_code,
    ApproveCommand: _handle_approve_scene,
    AcceptContractDriftCommand: _handle_accept_contract_drift,
}
