"""GDP 造数 Agent 运行时的业务中枢。

封装用户造数任务的全部用例（创建、启动、回复、取消、查询），
API 层只负责 HTTP 映射，不包含任何业务逻辑。
每个用例的标准流程：加载/恢复任务账本 → 执行用例 → 持久化或回滚。
"""

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
    """当前操作用户身份。

    业务目标：限定用户只能查看和操作自己创建的造数任务，
    完整审计数据（payload）需要管理员权限才能访问。
    未认证的测试入口使用 user_id=None 跳过权限校验。
    """

    user_id: str | None
    is_admin: bool = False

    @property
    def has_audit_access(self) -> bool:
        """管理员才允许读取完整的审计 payload（含请求/响应原始数据）。"""

        return self.is_admin


class RuntimeService:
    """封装所有造数运行时用例。

    业务目标：为用户造数任务提供完整的生命周期管理——
    创建目标、启动执行、暂停回复、取消任务、查询历史。
    API 层只做 HTTP 映射，所有业务编排都在这里完成。
    """

    def __init__(self, store: Store, repository: Any | None = None) -> None:
        self._store = store
        self._repository = repository
        # 将每种回复命令路由到对应的处理用例
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
        """用户查看自己的造数任务历史。

        业务目标：让用户按状态、环境筛选自己创建过的造数任务，支持分页。
        普通用户只能看到自己的任务；管理员可查看所有任务。
        """

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
        """用户创建一个新的造数目标。

        业务目标：用户描述想要造什么数据，系统记录目标并生成任务。
        当前动作：初始化任务账本，快照内存状态后持久化到数据库。
        预期结果：返回新创建的任务，状态为 CREATED，等待用户启动。
        """

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
        """用户启动造数任务，系统开始自动搜索场景和执行。

        业务目标：用户已创建目标，现在触发系统自动执行造数流程。
        当前动作：恢复任务账本，校验只有 CREATED 状态可启动，驱动任务执行引擎。
        预期结果：任务进入执行流程，可能直接完成或因缺少输入/候选而暂停等待用户回复。
        """

        store = await self._load_store_for_task_run(task_run_id)
        task_run = self._get_visible_task_run(store, task_run_id, principal)
        if task_run.status != TaskRunStatus.CREATED:
            raise RuntimeConflictError(f"TaskRun 状态为 {task_run.status}，不能 start")

        snapshot = store.snapshot()
        task_run = await run_task(task_run, request, store, idempotency_gate=self._idempotency_gate())
        await self._persist_task_run_or_rollback(task_run.task_run_id, snapshot)
        return task_run

    async def cancel_task_run(self, task_run_id: str, principal: RuntimePrincipal) -> TaskRun:
        """用户取消正在运行或等待中的造数任务。

        业务目标：用户不再需要这批数据，终止任务避免无效执行。
        当前动作：恢复任务账本，校验状态合法性后转换为 CANCELLED。
        预期结果：任务状态变为 CANCELLED，后续不再执行任何场景。
        """

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
        """用户回复暂停的造数任务，补充信息后继续执行。

        业务目标：任务因缺少输入、候选场景、审批或结果未知而暂停，用户提供回复后恢复执行。
        当前动作：恢复任务账本，校验只有 WAITING_USER 状态可回复，根据命令类型分发到具体处理用例。
        预期结果：任务恢复执行，可能继续推进或因新的缺失再次暂停。
        """

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
        """用户查看某个造数任务的当前状态。

        业务目标：让用户了解任务进展——是正在执行、等待回复还是已完成/失败/取消。
        """

        store = await self._load_store_for_task_run(task_run_id)
        return self._get_visible_task_run(store, task_run_id, principal)

    async def get_timeline(self, task_run_id: str, principal: RuntimePrincipal) -> dict[str, Any]:
        """用户查看造数任务的执行时间线。

        业务目标：让用户看到任务执行过程中每一步的详细记录，
        包括需求解析、场景搜索、执行尝试、结果判定等完整过程。
        """

        store = await self._load_store_for_task_run(task_run_id)
        self._get_visible_task_run(store, task_run_id, principal)
        return store.get_timeline(task_run_id)

    async def list_decisions(self, task_run_id: str, principal: RuntimePrincipal) -> list[DecisionRecord]:
        """用户查看造数任务的关键决策记录。

        业务目标：让用户了解系统在执行过程中做了哪些关键决策——
        如场景选择、审批要求等，增强执行过程的透明度。
        """

        store = await self._load_store_for_task_run(task_run_id)
        self._get_visible_task_run(store, task_run_id, principal)
        return store.list_decisions(task_run_id)

    async def get_payload(self, task_run_id: str, ref: str, principal: RuntimePrincipal) -> Any:
        """管理员查看造数任务的完整审计 payload（原始请求/响应数据）。

        业务目标：审计场景下需要查看实际发送和接收的完整数据。
        权限要求：必须具备管理员审计权限，普通用户不可访问。
        查找策略：先查内存账本，找不到则回退到数据库。
        """

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
        """用户确认执行结果未知后停止任务，避免系统盲目重放写请求。

        业务目标：当系统无法确定上次写请求是否成功时，由用户确认结果并停止任务，
        防止重复执行写操作导致数据错乱。
        当前动作：校验当前确实是 UNKNOWN_STATE 状态，清除暂停标记，将任务标记为失败并附带用户说明。
        预期结果：任务状态变为 FAILED，不再继续执行。
        """
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
        """用户补充缺失的输入后继续任务，核心保护是已有写请求时不允许重放。

        业务目标：任务因缺少必填输入而暂停，用户补充后系统尝试继续执行。
        安全保护：如果已经发起过写请求，拒绝重放以避免数据重复。
        当前动作：合并新旧输入 → 刷新候选契约 → 检查是否仍需补输入或审批。
        预期结果：输入齐全则继续执行场景；仍缺输入或需审批则再次暂停。
        """
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
        """用户在候选列表中选定场景后继续执行。

        业务目标：系统搜索到多个候选场景，用户选定其中一个后继续造数。
        当前动作：校验选定场景在候选范围内 → 记录用户决策 → 检查是否需要补输入或审批。
        预期结果：选定场景输入齐全且已审批则执行；否则暂停等待用户进一步回复。
        """
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
        """零候选时用户手动指定场景编码，系统解析并继续执行。

        业务目标：系统未搜索到任何候选场景，用户凭借领域知识直接提供场景编码。
        当前动作：校验当前确实是零候选状态 → 从场景目录解析该编码 → 检查是否需要补输入或审批。
        预期结果：场景解析成功且条件满足则执行；否则暂停等待用户进一步回复。
        """
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
        """用户批准有写副作用的场景后继续执行。

        业务目标：选定场景的执行会产生写副作用（如修改线上数据），必须经用户明确批准才能执行。
        当前动作：校验存在待审批的已选定场景 → 检查输入是否齐全 → 记录审批决策 → 执行场景。
        预期结果：批准后执行该场景；若仍缺输入则再次暂停。
        """
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
        """从内存或数据库恢复任务账本，确保后续用例操作有完整数据。

        查找策略：先查内存账本，命中则直接返回；
        未命中则从数据库加载历史数据恢复到内存，支持用户查看已归档的任务。
        """
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
        """持久化任务账本，失败时回滚内存状态，保护用户任务数据一致性。

        业务目标：确保用户的任务数据不会因为持久化异常而损坏——
        如果写入数据库失败，内存账本恢复到操作前的快照，用户可重试。
        """
        try:
            await self._persist_task_run(task_run_id)
        except Exception as exc:
            self._store.restore(snapshot)
            logger.exception("GDP Agent 运行时账本持久化失败，已回滚内存状态：任务ID=%s", task_run_id)
            raise RuntimePersistenceError() from exc

    async def _persist_task_run(self, task_run_id: str) -> None:
        """将内存中的任务账本写入数据库。无数据库配置时跳过（纯内存模式）。"""
        if self._repository is None:
            return
        await self._repository.persist_store(self._store, task_run_id)

    def _get_visible_task_run(self, store: Store, task_run_id: str, principal: RuntimePrincipal) -> TaskRun:
        """获取当前用户有权查看的任务实例，越权访问时对调用方表现为"不存在"。"""
        try:
            task_run = store.get_task_run(task_run_id)
        except EntityNotFoundError as exc:
            raise RuntimeNotFoundError(f"TaskRun {task_run_id} not found") from exc
        self._ensure_task_access(task_run, principal)
        return task_run

    def _ensure_task_access(self, task_run: TaskRun, principal: RuntimePrincipal) -> None:
        """校验操作权限：用户只能访问自己创建的任务，管理员和未认证测试入口跳过校验。"""
        if principal.user_id is None or principal.is_admin:
            return
        if task_run.user_id != principal.user_id:
            raise RuntimeNotFoundError(f"TaskRun {task_run.task_run_id} not found")

    def _ensure_payload_access(self, task_run: TaskRun, principal: RuntimePrincipal) -> None:
        """校验审计数据访问权限：只有管理员或未认证测试入口可查看完整 payload。"""
        if principal.user_id is None or principal.has_audit_access:
            return
        raise RuntimeForbiddenError(f"TaskRun {task_run.task_run_id} payload 需要审计权限")

    def _effective_query_user_id(self, requested_user_id: str | None, principal: RuntimePrincipal) -> str | None:
        """计算列表查询的实际用户范围：普通用户强制限定为自己，管理员可查询任意用户。"""
        if principal.user_id is None:
            return requested_user_id
        if principal.is_admin:
            return requested_user_id
        return principal.user_id

    def _idempotency_gate(self) -> IdempotencyGate | None:
        """获取幂等性保护门控，防止同一请求被重复执行。纯内存模式无需幂等保护。"""
        if self._repository is None:
            return None
        return self._repository.claim_idempotency_key


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
