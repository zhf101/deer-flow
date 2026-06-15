"""GDP 造数运行时启动入口兼容门面。

历史调用方仍从本模块导入 run_task / get_catalog。
真正的 start/search/selection 编排已下沉到 workflows.start_workflow。
"""

from __future__ import annotations

from .adapters.catalog import AgentCatalogAdapter, SceneCatalogPort
from .ledger.memory import MemoryLedger as Store
from .models import TaskRun
from .ports.idempotency import IdempotencyGate
from .workflows.start_workflow import StartTaskRunRequestLike, run_start_workflow


def get_catalog() -> SceneCatalogPort:
    """返回默认 Catalog 适配器。测试可 monkeypatch 本函数注入 fake。"""

    return AgentCatalogAdapter()


async def run_task(
    task_run: TaskRun,
    request: StartTaskRunRequestLike,
    store: Store,
    catalog: SceneCatalogPort | None = None,
    idempotency_gate: IdempotencyGate | None = None,
) -> TaskRun:
    """启动造数任务，委托 start workflow 完成场景解析、搜索、选择和执行。"""

    return await run_start_workflow(
        task_run=task_run,
        request=request,
        store=store,
        catalog=catalog or get_catalog(),
        idempotency_gate=idempotency_gate,
    )
