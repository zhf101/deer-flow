"""GDP Agent TaskRun 同步中间件工具。"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.runtime_context import runtime_binding
from app.gdp.datagen.config.task.service import DatagenTaskService


async def sync_task_run_binding(
    task_service: DatagenTaskService,
    task_run_id: str,
    config: RunnableConfig | None,
) -> None:
    """把 DeerFlow runtime 标识同步到 TaskRun，失败不打断节点主流程。"""

    binding = runtime_binding(config)
    if not any(binding.values()):
        return
    try:
        await task_service.bind_deerflow_run(
            task_run_id,
            deerflow_thread_id=binding.get("thread_id"),
            deerflow_run_id=binding.get("run_id"),
            last_checkpoint_id=binding.get("checkpoint_id"),
        )
    except Exception:
        return
