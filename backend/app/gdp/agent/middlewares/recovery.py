"""GDP Agent 任务恢复中间件。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.runtime_context import runtime_binding
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService

GDPNodeCallable = Callable[..., Awaitable[GDPState]]

RECOVERY_REASON = "GDP Agent 图运行入口恢复上一次运行遗留的非终态步骤。"


def wrap_gdp_task_recovery(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
    enabled: bool,
) -> GDPNodeCallable:
    """在每次图运行中至多恢复一次遗留的 PENDING/RUNNING 任务步骤。"""

    async def task_recovery_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        if not enabled:
            return await node(state, config)

        recovery_summary = await recover_task_steps_once(
            task_service,
            state,
            config,
            node_name=node_name,
        )
        prepared_state = _merge_recovery_summary(state, recovery_summary)
        result = await node(prepared_state, config)
        if not isinstance(result, dict) or recovery_summary is None:
            return result
        return _merge_recovery_summary(result, recovery_summary)

    return task_recovery_node


async def recover_task_steps_once(
    task_service: DatagenTaskService,
    state: GDPState,
    config: RunnableConfig | None,
    *,
    node_name: str,
) -> dict[str, Any] | None:
    """按运行标识对非终态步骤做一次恢复，避免同一图运行重复改写步骤。"""

    task_run_id = _resolve_task_run_id(state)
    if not task_run_id:
        return None
    run_key = _recovery_run_key(config)
    if _already_recovered(state, run_key):
        return None

    task_run = await _safe_get_task_run(task_service, task_run_id)
    if task_run is None or _is_recovery_skipped_status(task_run.status):
        return {
            "taskRunId": task_run_id,
            "runKey": run_key,
            "nodeName": node_name,
            "recoveredStepCount": 0,
            "recoveredSteps": [],
            "skipped": True,
            "reason": RECOVERY_REASON,
        }

    try:
        recovered_steps = await task_service.recover_non_terminal_steps(task_run_id, reason=RECOVERY_REASON)
    except Exception:
        return None

    return {
        "taskRunId": task_run_id,
        "runKey": run_key,
        "nodeName": node_name,
        "recoveredStepCount": len(recovered_steps),
        "recoveredSteps": [_step_summary(step) for step in recovered_steps],
        "skipped": False,
        "reason": RECOVERY_REASON,
    }


def _merge_recovery_summary(state: GDPState, recovery_summary: dict[str, Any] | None) -> GDPState:
    if recovery_summary is None:
        return state
    return {
        **state,
        "decision_context": {
            **dict(state.get("decision_context") or {}),
            "taskStepRecovery": recovery_summary,
        },
    }


async def _safe_get_task_run(task_service: DatagenTaskService, task_run_id: str):
    try:
        return await task_service.get_task_run(task_run_id)
    except Exception:
        return None


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


def _recovery_run_key(config: RunnableConfig | None) -> str:
    binding = runtime_binding(config)
    return binding.get("run_id") or binding.get("thread_id") or "local"


def _already_recovered(state: GDPState, run_key: str) -> bool:
    decision_context = state.get("decision_context") or {}
    recovery = decision_context.get("taskStepRecovery") if isinstance(decision_context, dict) else None
    return isinstance(recovery, dict) and recovery.get("runKey") == run_key


def _is_recovery_skipped_status(status: Any) -> bool:
    value = getattr(status, "value", status)
    return value in {
        DatagenTaskStatus.WAITING_USER.value,
        DatagenTaskStatus.COMPLETED.value,
        DatagenTaskStatus.FAILED.value,
        DatagenTaskStatus.CANCELLED.value,
    }


def _step_summary(step: Any) -> dict[str, Any]:
    return {
        "taskStepId": step.taskStepId,
        "stepNo": step.stepNo,
        "phase": _enum_value(step.phase),
        "stepType": _enum_value(step.stepType),
        "status": _enum_value(step.status),
    }


def _enum_value(value: Any) -> Any:
    enum_value = getattr(value, "value", None)
    return enum_value if enum_value is not None else value
