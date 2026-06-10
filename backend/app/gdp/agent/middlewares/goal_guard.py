"""GDP Agent 目标锚点保护中间件。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import signature
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.context_compression import load_gdp_context_summary
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_goal_guard(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
    subtask_service: DatagenTaskSubtaskService | None = None,
    enabled: bool,
) -> GDPNodeCallable:
    """在节点出口刷新任务目标锚点，并阻止 checkpoint 中的原始目标漂移。"""

    accepts_config = len(signature(node).parameters) >= 2

    async def guarded_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        result = await node(state, config) if accepts_config else await node(state)
        if not enabled or not isinstance(result, dict):
            return result

        task_run_id = result.get("task_run_id") or state.get("task_run_id")
        if not task_run_id:
            return result

        try:
            context_summary = await load_gdp_context_summary(task_service, subtask_service, str(task_run_id))
        except Exception:
            return result

        goal_anchor = context_summary.get("goalAnchor") or {}
        protected_user_intent = goal_anchor.get("userIntent") or state.get("user_intent")
        guard_payload = _guard_payload(node_name, task_run_id, context_summary)
        warning = _build_goal_drift_warning(
            node_name=node_name,
            expected=protected_user_intent,
            actual=result.get("user_intent"),
        )

        guarded_result: GDPState = {
            **result,
            "context_summary": context_summary,
            "decision_context": {**dict(result.get("decision_context") or {}), "goalGuard": guard_payload},
        }
        if protected_user_intent:
            guarded_result["user_intent"] = str(protected_user_intent)
        if warning is None:
            return guarded_result

        await _record_goal_drift(task_service, str(task_run_id), context_summary, warning)
        return {
            **guarded_result,
            "errors": [*list(result.get("errors") or []), warning],
        }

    return guarded_node


def _guard_payload(node_name: str, task_run_id: str, context_summary: dict[str, Any]) -> dict[str, Any]:
    goal_anchor = context_summary.get("goalAnchor") or {}
    return {
        "nodeName": node_name,
        "taskRunId": task_run_id,
        "userIntent": goal_anchor.get("userIntent"),
        "envCode": goal_anchor.get("envCode"),
        "phase": goal_anchor.get("phase"),
        "goalStackDepth": len(goal_anchor.get("goalStack") or []),
        "unfinishedGoalCount": len(context_summary.get("unfinishedGoals") or []),
    }


def _build_goal_drift_warning(
    *,
    node_name: str,
    expected: Any,
    actual: Any,
) -> dict[str, Any] | None:
    if actual is None or expected is None or str(actual) == str(expected):
        return None
    return {
        "errorType": "GOAL_DRIFT_DETECTED",
        "nodeName": node_name,
        "field": "user_intent",
        "expected": str(expected),
        "actual": str(actual),
        "message": "节点输出尝试改写原始造数目标，已按 TaskRun 权威目标回写。",
    }


async def _record_goal_drift(
    task_service: DatagenTaskService,
    task_run_id: str,
    context_summary: dict[str, Any],
    warning: dict[str, Any],
) -> None:
    try:
        await task_service.record_event(
            task_run_id,
            event_type="AGENT_GOAL_DRIFT_DETECTED",
            phase=_event_phase((context_summary.get("goalAnchor") or {}).get("phase")),
            message="检测到 Agent 节点输出与 TaskRun 原始目标不一致，已保护目标锚点。",
            payload=warning,
        )
    except Exception:
        return


def _event_phase(value: str | None) -> DatagenTaskPhase:
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return DatagenTaskPhase.INTAKE
