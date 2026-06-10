"""GDP Agent 节点审计中间件。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from app.gdp.agent.middlewares.runtime_context import metadata_payload
from app.gdp.agent.middlewares.task_run_sync import sync_task_run_binding
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_node_audit(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
    metadata: Any | None = None,
) -> GDPNodeCallable:
    """为 GDP 图节点增加开始、结束、中断和失败审计。"""

    runtime_payload = metadata_payload(metadata)

    async def audited_node(state: GDPState, config: RunnableConfig) -> GDPState:
        task_run_id = state.get("task_run_id")
        attempt_no = _next_attempt_no(state, node_name)
        if task_run_id:
            await sync_task_run_binding(task_service, task_run_id, config)
            await _record_node_event(
                task_service,
                task_run_id,
                event_type="AGENT_NODE_STARTED",
                phase=_phase_from_state(state),
                message=f"Agent 节点 {node_name} 开始执行。",
                payload={"nodeName": node_name, "attemptNo": attempt_no, **runtime_payload},
            )
        try:
            result = await node(state, config)
        except GraphInterrupt:
            if task_run_id:
                await _record_node_event(
                    task_service,
                    task_run_id,
                    event_type="AGENT_NODE_INTERRUPTED",
                    phase=_phase_from_state(state),
                    message=f"Agent 节点 {node_name} 触发 LangGraph 中断。",
                    payload={"nodeName": node_name, "attemptNo": attempt_no, **runtime_payload},
                )
            raise

        result_task_run_id = result.get("task_run_id") or task_run_id
        if result_task_run_id:
            await sync_task_run_binding(task_service, result_task_run_id, config)
            await _record_node_event(
                task_service,
                result_task_run_id,
                event_type="AGENT_NODE_FINISHED",
                phase=_phase_from_state(result, fallback=state),
                message=f"Agent 节点 {node_name} 执行完成。",
                payload={
                    "nodeName": node_name,
                    "attemptNo": attempt_no,
                    "currentPhase": result.get("current_phase") or state.get("current_phase"),
                    "lastResultRef": result.get("last_result_ref"),
                    **runtime_payload,
                },
            )
        return {
            **result,
            "node_attempts": _merge_attempt_delta(result.get("node_attempts"), node_name),
        }

    return audited_node


async def _record_node_event(
    task_service: DatagenTaskService,
    task_run_id: str,
    *,
    event_type: str,
    phase: DatagenTaskPhase,
    message: str,
    payload: dict[str, Any],
) -> None:
    """记录节点审计事件，失败时交给调用方处理。"""

    await task_service.record_event(
        task_run_id,
        event_type=event_type,
        phase=phase,
        message=message,
        payload=payload,
    )


def _phase_from_state(state: GDPState, *, fallback: GDPState | None = None) -> DatagenTaskPhase:
    value = state.get("current_phase") or (fallback or {}).get("current_phase")
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return DatagenTaskPhase.INTAKE


def _next_attempt_no(state: GDPState, node_name: str) -> int:
    attempts = state.get("node_attempts") or {}
    try:
        return int(attempts.get(node_name, 0)) + 1
    except (TypeError, ValueError):
        return 1


def _merge_attempt_delta(existing: Any, node_name: str) -> dict[str, int]:
    result = dict(existing or {})
    try:
        current = int(result.get(node_name, 0))
    except (TypeError, ValueError):
        current = 0
    result[node_name] = current + 1
    return result
