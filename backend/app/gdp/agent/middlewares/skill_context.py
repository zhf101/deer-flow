"""GDP Agent 阶段技能上下文中间件。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.skills.registry import get_gdp_skill_context
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_skill_context(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
) -> GDPNodeCallable:
    """给 GDP 节点出口注入当前阶段技能引用。"""

    async def skill_context_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        result = await node(state, config)
        if not isinstance(result, dict):
            return result

        phase = result.get("current_phase") or state.get("current_phase")
        skill_context = get_gdp_skill_context(phase)
        trace = {
            "nodeName": node_name,
            "phase": skill_context.get("phase"),
            "skillIds": skill_context.get("skillIds") or [],
            "reason": "按当前 GDP 阶段注入方法论技能引用。",
        }
        task_run_id = result.get("task_run_id") or state.get("task_run_id")
        if _should_record_skill_event(state, skill_context) and task_run_id:
            await task_service.record_event(
                task_run_id,
                event_type="AGENT_SKILLS_SELECTED",
                phase=_event_phase(skill_context.get("phase")),
                message=f"Agent 节点 {node_name} 已注入当前阶段技能引用。",
                payload={
                    "nodeName": node_name,
                    "phase": skill_context.get("phase"),
                    "skillIds": skill_context.get("skillIds") or [],
                    "skills": [
                        {
                            "skillId": item.get("skillId"),
                            "version": item.get("version"),
                            "title": item.get("title"),
                            "allowedActions": item.get("allowedActions") or [],
                        }
                        for item in skill_context.get("skills") or []
                    ],
                },
            )
        return {**result, "skill_context": skill_context, "skill_trace": [trace]}

    return skill_context_node


def _should_record_skill_event(state: GDPState, skill_context: dict[str, Any]) -> bool:
    """只有阶段技能集合变化时才写审计事件，避免 TaskEvent 噪声。"""

    skill_ids = skill_context.get("skillIds") or []
    if not skill_ids:
        return False
    existing = state.get("skill_context") or {}
    return existing.get("phase") != skill_context.get("phase") or existing.get("skillIds") != skill_ids


def _event_phase(value: Any) -> DatagenTaskPhase:
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return DatagenTaskPhase.INTAKE
