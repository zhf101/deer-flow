"""GDP Agent 错误处理中间件工具。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp, GraphInterrupt

from app.gdp.agent.middlewares.runtime_context import metadata_payload
from app.gdp.agent.middlewares.task_run_sync import sync_task_run_binding
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_error_handling(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
    metadata: Any | None = None,
) -> GDPNodeCallable:
    """为 GDP 节点增加普通异常失败落库边界，LangGraph 控制流异常继续透传。"""

    runtime_payload = metadata_payload(metadata)

    async def error_handling_node(state: GDPState, config: RunnableConfig) -> GDPState:
        try:
            return await node(state, config)
        except (GraphInterrupt, GraphBubbleUp):
            raise
        except Exception as exc:
            task_run_id = _resolve_task_run_id(state)
            if task_run_id:
                await sync_task_run_binding(task_service, task_run_id, config)
                payload = build_node_error_payload(node_name, exc, state, runtime_payload)
                await record_node_failed_event(task_service, task_run_id, payload)
                await mark_node_failed(task_service, task_run_id, node_name, exc)
            raise

    return error_handling_node


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


def build_node_error_payload(
    node_name: str,
    exc: Exception,
    state: GDPState | None = None,
    runtime_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造节点失败审计 payload，避免不同 wrapper 各自拼装错误结构。"""

    return {
        "nodeName": node_name,
        "errorType": f"AGENT_NODE_ERROR:{node_name}",
        "errorClass": exc.__class__.__name__,
        "errorMessage": str(exc),
        "currentPhase": (state or {}).get("current_phase"),
        **(runtime_payload or {}),
    }


async def record_node_failed_event(
    task_service: DatagenTaskService,
    task_run_id: str,
    payload: dict[str, Any],
) -> None:
    """记录节点失败审计事件，记录失败不覆盖原始节点异常。"""

    try:
        await task_service.record_event(
            task_run_id,
            event_type="AGENT_NODE_FAILED",
            phase=_event_phase(payload.get("currentPhase")),
            message=f"Agent 节点 {payload.get('nodeName')} 执行失败。",
            payload=payload,
        )
    except Exception:
        return


def _resolve_task_run_id(state: GDPState) -> str | None:
    task_run_id = state.get("task_run_id")
    if task_run_id:
        return str(task_run_id)
    task_context = state.get("task_context") or {}
    if isinstance(task_context, dict):
        context_task_run_id = task_context.get("task_run_id") or task_context.get("taskRunId")
        if context_task_run_id:
            return str(context_task_run_id)
    return None


def _event_phase(value: Any) -> DatagenTaskPhase:
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return DatagenTaskPhase.FAILED
