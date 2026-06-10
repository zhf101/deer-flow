"""GDP Agent TaskRun 同步中间件工具。

重要契约（节点必须遵守）：本中间件在节点出口会用 DB 中 TaskRun 的
``phase`` / ``user_intent`` 覆盖节点返回值（TaskRun 是权威状态源）。
因此**节点必须先通过 ``move_to_phase`` / ``mark_waiting_user`` 等服务方法把
新阶段持久化，再在返回值里携带 ``current_phase``**；只改内存返回值而不落库
的阶段变更会被本中间件静默覆盖，导致路由决策丢失。出口检测到这种不一致时
会记录 warning 日志，便于及时发现违反契约的节点。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.runtime_context import runtime_binding
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskRunResponse
from app.gdp.datagen.config.task.service import DatagenTaskService

logger = logging.getLogger(__name__)

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_task_run_sync(
    *,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
) -> GDPNodeCallable:
    """在节点前后刷新 TaskRun 权威上下文，并把运行绑定同步回业务表。"""

    async def task_run_sync_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        prepared_state = await _refresh_state_from_task_run(task_service, state)
        result = await node(prepared_state, config)
        if not isinstance(result, dict):
            return result

        task_run_id = _resolve_task_run_id(result, prepared_state)
        if not task_run_id:
            return result

        await sync_task_run_binding(task_service, task_run_id, config)
        return await _refresh_result_from_task_run(task_service, result, prepared_state, task_run_id)

    return task_run_sync_node


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


def build_gdp_task_context(task_run: DatagenTaskRunResponse | Any) -> dict[str, Any]:
    """从 TaskRun 响应生成 checkpoint 中的轻量任务上下文。"""

    return {
        "task_run_id": task_run.taskRunId,
        "status": _enum_value(task_run.status),
        "phase": _enum_value(task_run.phase),
        "env_code": task_run.envCode,
        "deerflow_thread_id": task_run.deerflowThreadId,
        "deerflow_run_id": task_run.deerflowRunId,
        "last_checkpoint_id": task_run.lastCheckpointId,
    }


async def _refresh_state_from_task_run(task_service: DatagenTaskService, state: GDPState) -> GDPState:
    task_run_id = _resolve_task_run_id(state)
    if not task_run_id:
        return state
    task_run = await _safe_get_task_run(task_service, task_run_id)
    if task_run is None:
        return state
    return _merge_task_run_state(state, task_run)


async def _refresh_result_from_task_run(
    task_service: DatagenTaskService,
    result: GDPState,
    state: GDPState,
    task_run_id: str,
) -> GDPState:
    task_run = await _safe_get_task_run(task_service, task_run_id)
    if task_run is None:
        return result
    _warn_on_unpersisted_phase(result, task_run, task_run_id)
    return _merge_task_run_state(result, task_run, fallback=state)


def _warn_on_unpersisted_phase(result: GDPState, task_run: DatagenTaskRunResponse | Any, task_run_id: str) -> None:
    """检测节点违反“先持久化 phase 再返回”契约的情况并告警。

    节点返回的 ``current_phase`` 与 DB 权威 phase 不一致，说明节点只在内存里
    改了阶段、没有先落库——该路由决策即将被权威状态覆盖（见模块级契约说明）。
    """

    result_phase = result.get("current_phase")
    db_phase = _enum_value(getattr(task_run, "phase", None))
    if result_phase and db_phase and str(result_phase) != str(db_phase):
        logger.warning(
            "GDP 节点返回的 current_phase=%s 与 TaskRun(%s) 持久化 phase=%s 不一致，节点内存阶段将被权威状态覆盖。请检查节点是否漏调 move_to_phase/mark_waiting_user 先落库。",
            result_phase,
            task_run_id,
            db_phase,
        )


async def _safe_get_task_run(
    task_service: DatagenTaskService,
    task_run_id: str,
) -> DatagenTaskRunResponse | Any | None:
    try:
        return await task_service.get_task_run(task_run_id)
    except Exception:
        return None


def _merge_task_run_state(
    state: GDPState,
    task_run: DatagenTaskRunResponse | Any,
    *,
    fallback: GDPState | None = None,
) -> GDPState:
    context = build_gdp_task_context(task_run)
    existing_context = dict((fallback or {}).get("task_context") or {})
    existing_context.update(dict(state.get("task_context") or {}))
    user_intent = getattr(task_run, "userIntent", None)
    return {
        **state,
        "task_run_id": context["task_run_id"],
        "user_intent": str(user_intent) if user_intent is not None else state.get("user_intent"),
        "env_code": context["env_code"],
        "current_phase": context["phase"],
        "task_context": {**existing_context, **context},
    }


def _resolve_task_run_id(*states: GDPState) -> str | None:
    for state in states:
        task_run_id = state.get("task_run_id")
        if task_run_id:
            return str(task_run_id)
        task_context = state.get("task_context") or {}
        if isinstance(task_context, dict):
            context_task_run_id = task_context.get("task_run_id") or task_context.get("taskRunId")
            if context_task_run_id:
                return str(context_task_run_id)
    return None


def _enum_value(value: Any) -> Any:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    return enum_value if enum_value is not None else str(value)
