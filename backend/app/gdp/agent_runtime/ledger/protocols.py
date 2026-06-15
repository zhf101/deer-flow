"""运行时账本持久化端口。"""

from __future__ import annotations

from typing import Any, Protocol

from ..models import TaskRun, TaskRunStatus
from .memory import MemoryLedger


class RuntimeLedgerRepository(Protocol):
    """RuntimeService 依赖的账本持久化最小接口。"""

    async def persist_store(self, store: MemoryLedger, task_run_id: str) -> None:
        """持久化指定任务的完整内存账本。"""

    async def hydrate_store(self, task_run_id: str) -> MemoryLedger:
        """从外部持久化存储恢复指定任务账本。"""

    async def list_task_runs(
        self,
        *,
        status: TaskRunStatus | None = None,
        env_code: str | None = None,
        user_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskRun]:
        """分页查询任务列表。"""

    async def get_payload(self, task_run_id: str, ref: str) -> Any:
        """读取完整审计载荷。"""

    async def claim_idempotency_key(self, task_run_id: str, action_id: str, idempotency_key: str) -> bool:
        """检查同一任务中是否已有其他动作发起过同幂等键写请求。"""
