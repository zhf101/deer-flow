"""GDP 造数 Agent 运行时的业务中枢。

封装用户造数任务的全部用例（创建、启动、回复、取消、查询），
API 层只负责 HTTP 映射，不包含业务编排细节。
每个用例的标准流程：加载/恢复任务账本 → 委托工作流或运行器 → 持久化或回滚。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..domain.transitions import IllegalTransition, transition_task_run
from ..ledger.memory import EntityNotFoundError
from ..ledger.memory import MemoryLedger as Store
from ..ledger.protocols import RuntimeLedgerRepository
from ..models import DecisionRecord, TaskRun, TaskRunStatus
from ..ports.idempotency import IdempotencyGate
from ..runner import run_task
from ..support.errors import (
    RuntimeConflictError,
    RuntimeForbiddenError,
    RuntimeNotFoundError,
    RuntimePersistenceError,
)
from ..workflows.reply_commands import RuntimeCommand
from ..workflows.reply_workflow import handle_reply

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
    API 层只做 HTTP 映射，复杂业务编排委托给 workflows 和 runner 完成。
    """

    def __init__(self, store: Store, repository: RuntimeLedgerRepository | None = None) -> None:
        self._store = store
        self._repository = repository

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

        from ..domain.factories import create_task_run as _create

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

        snapshot = store.snapshot()
        task_run = await handle_reply(task_run, command, store, self._idempotency_gate())
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
        return getattr(self._repository, "claim_idempotency_key", None)
