"""GDP Agent 错误处理中间件工具。"""

from __future__ import annotations

from app.gdp.datagen.config.task.service import DatagenTaskService


async def mark_node_failed(
    task_service: DatagenTaskService,
    task_run_id: str,
    node_name: str,
    exc: Exception,
) -> None:
    """把普通节点异常落到 TaskRun 失败事件，失败时不覆盖原始异常。"""

    try:
        await task_service.fail_task(
            task_run_id,
            failure_type=f"AGENT_NODE_ERROR:{node_name}",
            failure_message=f"Agent 节点 {node_name} 执行失败：{exc}",
        )
    except Exception:
        return
