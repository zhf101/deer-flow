"""GDP Agent 进度振荡检测中间件。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_progress_loop_detection(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
    enabled: bool,
    warn_threshold: int = 3,
    window_size: int = 8,
) -> GDPNodeCallable:
    """给 GDP 节点出口增加阶段振荡检测。"""

    async def progress_loop_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        result = await node(state, config)
        if not enabled or not isinstance(result, dict):
            return result

        phase = str(result.get("current_phase") or state.get("current_phase") or "")
        if not phase:
            return result
        history = list(state.get("phase_history") or [])
        entry = {
            "nodeName": node_name,
            "phase": phase,
            "visitNo": len(history) + 1,
        }
        recent = [*history, entry][-window_size:]
        warning = _build_loop_warning(state, phase, recent, warn_threshold)
        if warning is None:
            return {**result, "phase_history": [entry]}

        task_run_id = result.get("task_run_id") or state.get("task_run_id")
        if task_run_id:
            await task_service.record_event(
                task_run_id,
                event_type="AGENT_PROGRESS_LOOP_DETECTED",
                phase=_event_phase(phase),
                message=f"检测到 Agent 近期多次回到阶段 {phase}，需要关注是否出现进度振荡。",
                payload=warning,
            )
        return {
            **result,
            "phase_history": [entry],
            # errors 写入约定：wrapper 只追加自身错误，必须保留内层 wrapper /
            # 节点已写入 result["errors"] 的诊断（reducer 在整个节点函数返回后才介入）。
            "errors": [*list(result.get("errors") or []), warning],
        }

    return progress_loop_node


def _build_loop_warning(
    state: GDPState,
    phase: str,
    recent: list[dict[str, Any]],
    warn_threshold: int,
) -> dict[str, Any] | None:
    phase_count = sum(1 for item in recent if item.get("phase") == phase)
    if phase_count < warn_threshold:
        return None
    for error in state.get("errors") or []:
        if error.get("errorType") == "PROGRESS_LOOP_DETECTED" and error.get("phase") == phase:
            return None
    return {
        "errorType": "PROGRESS_LOOP_DETECTED",
        "phase": phase,
        "phaseCount": phase_count,
        "recentPhases": [item.get("phase") for item in recent],
        "recentNodes": [item.get("nodeName") for item in recent],
        "message": "近期阶段重复次数较高，可能出现阶段振荡或资源补齐循环。",
    }


def _event_phase(value: str) -> DatagenTaskPhase:
    try:
        return DatagenTaskPhase(value)
    except ValueError:
        return DatagenTaskPhase.INTAKE
