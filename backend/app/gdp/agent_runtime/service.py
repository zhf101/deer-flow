"""GDP Agent Runtime 应用服务。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .commands import (
    ApproveCommand,
    ConfirmUnknownStateCommand,
    RuntimeCommand,
    SelectSceneCommand,
    SupplyInputCommand,
    SupplySceneCodeCommand,
)
from .decision import build_approval_requirement_decision, build_user_scene_selection_decision
from .errors import (
    RuntimeConflictError,
    RuntimeForbiddenError,
    RuntimeNotFoundError,
    RuntimePersistenceError,
    RuntimeValidationError,
)
from .models import (
    DecisionRecord,
    ProposalStatus,
    RequirementStatus,
    SelectionSource,
    SuspendReason,
    TaskRun,
    TaskRunStatus,
)
from .runner import IdempotencyGate, collect_preflight_missing, execute_scene, pending_start_ref, run_task
from .selection import apply_selection, ensure_selection_consistency
from .store import EntityNotFoundError, Store
from .transitions import IllegalTransition, transition_requirement, transition_task_run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimePrincipal:
    """当前请求用户。未认证测试入口使用 user_id=None。"""

    user_id: str | None
    is_admin: bool = False

    @property
    def has_audit_access(self) -> bool:
        """是否允许读取完整审计 payload。"""

        return self.is_admin


class RuntimeService:
    """封装 Agent Runtime 用例，API 层只负责 HTTP 映射。"""

    def __init__(self, store: Store, repository: Any | None = None) -> None:
        self._store = store
        self._repository = repository
        self._reply_handlers: dict[type[RuntimeCommand], Callable[[TaskRun, RuntimeCommand, Store], Awaitable[TaskRun]]] = {
            ConfirmUnknownStateCommand: self._handle_confirm_unknown_state,
            SupplyInputCommand: self._handle_supply_input,
            SelectSceneCommand: self._handle_select_scene,
            SupplySceneCodeCommand: self._handle_supply_scene_code,
            ApproveCommand: self._handle_approve_scene,
        }

    async def list_task_runs(
        self,
        *,
        status: TaskRunStatus | None,
        env_code: str | None,
        user_id: str | None,
        limit: int,
        offset: int,
        principal: RuntimePrincipal,
    ) -> list[TaskRun]:
        """分页查询当前用户可见的 TaskRun。"""

        effective_user_id = self._effective_query_user_id(user_id, principal)
        if self._repository is not None:
            return await self._repository.list_task_runs(
                status=status,
                env_code=env_code,
                user_id=effective_user_id,
                limit=limit,
                offset=offset,
            )

        task_runs = self._store.list_task_runs()
        if status is not None:
            task_runs = [item for item in task_runs if item.status == status]
        if env_code:
            task_runs = [item for item in task_runs if item.env_code == env_code]
        if effective_user_id:
            task_runs = [item for item in task_runs if item.user_id == effective_user_id]
        return task_runs[offset : offset + limit]

    async def create_task_run(self, *, user_goal: str, env_code: str | None, principal: RuntimePrincipal) -> TaskRun:
        """创建 TaskRun。"""

        from .flow import create_task_run as _create

        task_run = _create(
            user_goal=user_goal,
            env_code=env_code,
            user_id=principal.user_id or "anonymous",
        )
        snapshot = self._store.snapshot()
        self._store.save_task_run(task_run)
        await self._persist_task_run_or_rollback(task_run.task_run_id, snapshot)
        return task_run

    async def start_task_run(self, task_run_id: str, request: Any, principal: RuntimePrincipal) -> TaskRun:
        """启动 TaskRun。"""

        store = await self._load_store_for_task_run(task_run_id)
        task_run = self._get_visible_task_run(store, task_run_id, principal)
        if task_run.status != TaskRunStatus.CREATED:
            raise RuntimeConflictError(f"TaskRun 状态为 {task_run.status}，不能 start")

        snapshot = store.snapshot()
        task_run = await run_task(task_run, request, store, idempotency_gate=self._idempotency_gate())
        await self._persist_task_run_or_rollback(task_run.task_run_id, snapshot)
        return task_run

    async def cancel_task_run(self, task_run_id: str, principal: RuntimePrincipal) -> TaskRun:
        """取消 TaskRun。"""

        store = await self._load_store_for_task_run(task_run_id)
        task_run = self._get_visible_task_run(store, task_run_id, principal)
        snapshot = store.snapshot()
        try:
            task_run = transition_task_run(task_run, TaskRunStatus.CANCELLED)
        except IllegalTransition as exc:
            raise RuntimeConflictError(f"TaskRun 状态为 {task_run.status}，不能取消") from exc

        store.save_task_run(task_run)
        await self._persist_task_run_or_rollback(task_run.task_run_id, snapshot)
        return task_run

    async def reply_task_run(self, task_run_id: str, command: RuntimeCommand, principal: RuntimePrincipal) -> TaskRun:
        """执行 WAITING_USER 恢复命令。"""

        store = await self._load_store_for_task_run(task_run_id)
        task_run = self._get_visible_task_run(store, task_run_id, principal)
        if task_run.status != TaskRunStatus.WAITING_USER:
            raise RuntimeConflictError(f"TaskRun 状态为 {task_run.status}，不能 reply")

        handler = self._reply_handlers[type(command)]
        snapshot = store.snapshot()
        task_run = await handler(task_run, command, store)
        await self._persist_task_run_or_rollback(task_run.task_run_id, snapshot)
        return task_run

    async def get_task_run(self, task_run_id: str, principal: RuntimePrincipal) -> TaskRun:
        """查询 TaskRun 当前状态。"""

        store = await self._load_store_for_task_run(task_run_id)
        return self._get_visible_task_run(store, task_run_id, principal)

    async def get_timeline(self, task_run_id: str, principal: RuntimePrincipal) -> dict[str, Any]:
        """查询 TaskRun 时间线。"""

        store = await self._load_store_for_task_run(task_run_id)
        self._get_visible_task_run(store, task_run_id, principal)
        return store.get_timeline(task_run_id)

    async def list_decisions(self, task_run_id: str, principal: RuntimePrincipal) -> list[DecisionRecord]:
        """查询 TaskRun 决策审计记录。"""

        store = await self._load_store_for_task_run(task_run_id)
        self._get_visible_task_run(store, task_run_id, principal)
        return store.list_decisions(task_run_id)

    async def get_payload(self, task_run_id: str, ref: str, principal: RuntimePrincipal) -> Any:
        """读取完整 payload。认证请求必须具备审计权限。"""

        store = await self._load_store_for_task_run(task_run_id)
        task_run = self._get_visible_task_run(store, task_run_id, principal)
        self._ensure_payload_access(task_run, principal)
        try:
            return store.get_payload(task_run_id, ref)
        except EntityNotFoundError as memory_exc:
            if self._repository is None:
                raise RuntimeNotFoundError(f"Payload {ref} not found in memory store") from memory_exc
            try:
                return await self._repository.get_payload(task_run_id, ref)
            except EntityNotFoundError as repository_exc:
                raise RuntimeNotFoundError(f"Payload {ref} not found in memory store or database") from repository_exc

    async def _handle_confirm_unknown_state(
        self,
        task_run: TaskRun,
        command: RuntimeCommand,
        store: Store,
    ) -> TaskRun:
        latest_verdict_type = _latest_verdict_type(task_run.task_run_id, store)
        if latest_verdict_type != "UNKNOWN_STATE":
            raise RuntimeConflictError("当前 TaskRun 不是执行结果未知状态，不能确认 UNKNOWN_STATE")

        task_run.pending_question = None
        task_run.suspend_reason = None
        task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
        task_run.failure_reason = _format_unknown_state_confirmation(command.payload)
        task_run = transition_task_run(task_run, TaskRunStatus.FAILED)
        store.save_task_run(task_run)
        return task_run

    async def _handle_supply_input(
        self,
        task_run: TaskRun,
        command: RuntimeCommand,
        store: Store,
    ) -> TaskRun:
        if _has_write_attempts(task_run.task_run_id, store):
            raise RuntimeConflictError("当前 TaskRun 已发起写请求，不能通过 SUPPLY_INPUT 重放")

        pending_start = _get_pending_start(task_run, store)
        scene_code = _strip_optional(pending_start.get("scene_code"))

        _merge_env_code(task_run, command.payload)
        inputs = _merge_supplied_inputs(pending_start.get("inputs"), command.payload)
        store.save_payload(task_run.task_run_id, pending_start_ref(task_run.task_run_id), {"scene_code": scene_code, "inputs": inputs})

        requirement = _get_waiting_requirement(task_run, store)
        proposal = store.get_latest_proposal(
            task_run.task_run_id,
            step_id=requirement.step_id,
            requirement_id=requirement.requirement_id,
        )
        if proposal is None:
            raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Proposal")

        if proposal.status == ProposalStatus.SELECTED:
            selected_scene_code = proposal.selected_scene_code or scene_code
            if selected_scene_code is None:
                raise RuntimeConflictError("当前已选定 Proposal 缺少 scene_code")
            ensure_selection_consistency(requirement, proposal, selected_scene_code)
            candidate = await _refresh_candidate_contract(proposal, selected_scene_code, inputs, store)
        elif proposal.status == ProposalStatus.PENDING and len(proposal.candidates) == 1:
            candidate = await _refresh_candidate_contract(proposal, proposal.candidates[0].scene_code, inputs, store)
            if requirement.status == RequirementStatus.PENDING:
                requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
            requirement, proposal = apply_selection(requirement, proposal, candidate.scene_code, SelectionSource.AUTO)
            requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
            store.save_requirement(requirement)
            store.save_proposal(proposal)
        else:
            raise RuntimeConflictError("当前 TaskRun 仍需先选择可恢复的场景")

        scene_code = candidate.scene_code
        store.save_payload(task_run.task_run_id, pending_start_ref(task_run.task_run_id), {"scene_code": scene_code, "inputs": inputs})

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

        task_run.pending_question = None
        task_run.suspend_reason = None
        task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
        return await execute_scene(
            task_run,
            store.get_step(requirement.step_id),
            requirement,
            candidate.scene_code,
            inputs,
            candidate,
            store,
            self._idempotency_gate(),
        )

    async def _handle_select_scene(
        self,
        task_run: TaskRun,
        command: RuntimeCommand,
        store: Store,
    ) -> TaskRun:
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
            task_run.pending_question = (
                f"场景 {candidate.scene_name}（{candidate.scene_code}）已选定，但执行有写副作用。"
                "请批准后继续。"
            )
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

        task_run.pending_question = None
        task_run.suspend_reason = None
        task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
        return await execute_scene(
            task_run,
            store.get_step(requirement.step_id),
            requirement,
            scene_code,
            inputs,
            candidate,
            store,
            self._idempotency_gate(),
        )

    async def _handle_supply_scene_code(
        self,
        task_run: TaskRun,
        command: RuntimeCommand,
        store: Store,
    ) -> TaskRun:
        requirement = _get_waiting_requirement(task_run, store)
        proposal = _get_waiting_proposal(task_run, store, requirement.requirement_id)
        if proposal.candidates:
            raise RuntimeConflictError("当前不是零候选等待状态，不能 SUPPLY_SCENE_CODE")

        scene_code = _require_scene_code(command.payload)
        inputs = _merge_reply_inputs(task_run, command.payload, store)

        from .catalog import resolve_explicit_scene

        proposal = await resolve_explicit_scene(requirement, scene_code, inputs, _get_scene_catalog())
        resolved = proposal.candidates[0]
        store.save_proposal(proposal)
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

        task_run.pending_question = None
        task_run.suspend_reason = None
        task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
        return await execute_scene(
            task_run,
            store.get_step(requirement.step_id),
            requirement,
            scene_code,
            inputs,
            resolved,
            store,
            self._idempotency_gate(),
        )

    async def _handle_approve_scene(
        self,
        task_run: TaskRun,
        command: RuntimeCommand,
        store: Store,
    ) -> TaskRun:
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

        _save_approval_record(store, task_run.task_run_id, requirement.requirement_id, proposal.proposal_id, proposal.selected_scene_code)
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
        task_run.pending_question = None
        task_run.suspend_reason = None
        task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
        return await execute_scene(
            task_run,
            store.get_step(requirement.step_id),
            requirement,
            proposal.selected_scene_code,
            inputs,
            candidate,
            store,
            self._idempotency_gate(),
        )

    async def _load_store_for_task_run(self, task_run_id: str) -> Store:
        try:
            self._store.get_task_run(task_run_id)
            return self._store
        except EntityNotFoundError:
            if self._repository is None:
                raise RuntimeNotFoundError(f"TaskRun {task_run_id} not found")
            try:
                restored = await self._repository.hydrate_store(task_run_id)
            except EntityNotFoundError as exc:
                raise RuntimeNotFoundError(f"TaskRun {task_run_id} not found") from exc
            self._store.restore(restored.snapshot())
            return self._store

    async def _persist_task_run_or_rollback(self, task_run_id: str, snapshot: dict[str, Any]) -> None:
        try:
            await self._persist_task_run(task_run_id)
        except Exception as exc:
            self._store.restore(snapshot)
            logger.exception("GDP Agent 运行时账本持久化失败，已回滚内存状态：任务ID=%s", task_run_id)
            raise RuntimePersistenceError() from exc

    async def _persist_task_run(self, task_run_id: str) -> None:
        if self._repository is None:
            return
        await self._repository.persist_store(self._store, task_run_id)

    def _get_visible_task_run(self, store: Store, task_run_id: str, principal: RuntimePrincipal) -> TaskRun:
        try:
            task_run = store.get_task_run(task_run_id)
        except EntityNotFoundError as exc:
            raise RuntimeNotFoundError(f"TaskRun {task_run_id} not found") from exc
        self._ensure_task_access(task_run, principal)
        return task_run

    def _ensure_task_access(self, task_run: TaskRun, principal: RuntimePrincipal) -> None:
        if principal.user_id is None or principal.is_admin:
            return
        if task_run.user_id != principal.user_id:
            raise RuntimeNotFoundError(f"TaskRun {task_run.task_run_id} not found")

    def _ensure_payload_access(self, task_run: TaskRun, principal: RuntimePrincipal) -> None:
        if principal.user_id is None or principal.has_audit_access:
            return
        raise RuntimeForbiddenError(f"TaskRun {task_run.task_run_id} payload 需要审计权限")

    def _effective_query_user_id(self, requested_user_id: str | None, principal: RuntimePrincipal) -> str | None:
        if principal.user_id is None:
            return requested_user_id
        if principal.is_admin:
            return requested_user_id
        return principal.user_id

    def _idempotency_gate(self) -> IdempotencyGate | None:
        if self._repository is None:
            return None
        return self._repository.claim_idempotency_key


def _get_pending_start(task_run: TaskRun, store: Store) -> dict[str, Any]:
    try:
        pending_start = store.get_payload(task_run.task_run_id, pending_start_ref(task_run.task_run_id))
    except EntityNotFoundError as exc:
        raise RuntimeConflictError("找不到可恢复的启动请求") from exc
    if not isinstance(pending_start, dict):
        raise RuntimeConflictError("待恢复启动请求格式无效")
    return pending_start


def _merge_supplied_inputs(pending_inputs: Any, payload: dict[str, Any]) -> dict[str, Any]:
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
    verdicts = store.get_timeline(task_run_id)["verdicts"]
    if not verdicts:
        return None
    verdict_type = verdicts[-1].get("verdict_type")
    return verdict_type if isinstance(verdict_type, str) else None


def _has_write_attempts(task_run_id: str, store: Store) -> bool:
    return bool(store.get_timeline(task_run_id)["attempts"])


def _format_unknown_state_confirmation(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return "用户确认执行结果未知，任务已停止以避免重复写请求。用户说明：" + message.strip()
    return "用户确认执行结果未知，任务已停止以避免重复写请求。"


def _format_missing_required_question(missing_fields: list[str]) -> str:
    return "缺少必填信息：" + "，".join(missing_fields) + "。请补充后继续。"


def _require_scene_code(payload: dict[str, Any]) -> str:
    scene_code = payload.get("scene_code")
    if not isinstance(scene_code, str) or not scene_code.strip():
        raise RuntimeValidationError("payload.scene_code 必须是非空字符串")
    return scene_code.strip()


def _strip_optional(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _get_waiting_requirement(task_run: TaskRun, store: Store):
    requirement = store.get_active_requirement(task_run.task_run_id, step_id=task_run.active_step_id)
    if requirement is None:
        raise RuntimeConflictError("当前 TaskRun 没有可恢复的 Requirement")
    return requirement


def _get_waiting_proposal(task_run: TaskRun, store: Store, requirement_id: str):
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


def _get_latest_selected_proposal(task_run: TaskRun, store: Store, requirement_id: str):
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
    proposal,
    scene_code: str,
    inputs: dict[str, Any],
    store: Store,
):
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
    from datetime import UTC, datetime

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
    from . import runner as runtime_runner

    return runtime_runner.get_catalog()
