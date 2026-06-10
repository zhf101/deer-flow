"""GDP Agent 人工确认节点。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.gdp.agent.middlewares.interrupt import (
    build_confirmation_decision,
    merge_user_inputs_from_resume,
    resolve_resume_phase,
)
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_human_confirm_node(task_service: DatagenTaskService):
    """构造人工确认节点。"""

    async def human_confirm(state: GDPState) -> GDPState:
        payload = state.get("pending_confirmation") or {}
        resume_value = interrupt(payload)
        task_run_id = state["task_run_id"]
        next_phase = resolve_resume_phase(payload)
        user_inputs = merge_user_inputs_from_resume(state.get("user_inputs") or {}, resume_value, payload)
        await task_service.record_event(
            task_run_id,
            event_type="USER_CONFIRMATION_RESUMED",
            phase=DatagenTaskPhase.WAITING_USER,
            message="已从 LangGraph 中断点收到用户回复。",
            payload={"reply": resume_value},
        )
        await task_service.move_to_phase(
            task_run_id,
            status=DatagenTaskStatus.RUNNING,
            phase=next_phase,
            event_type="PHASE_CHANGED",
            message=f"用户已回复，任务进入 {next_phase.value} 阶段。",
            payload={"from": DatagenTaskPhase.WAITING_USER.value, "to": next_phase.value},
        )
        return {
            "current_phase": next_phase.value,
            "task_context": {
                "task_run_id": task_run_id,
                "status": DatagenTaskStatus.RUNNING.value,
                "phase": next_phase.value,
            },
            "pending_confirmation": None,
            "confirmation_result": resume_value,
            "user_inputs": user_inputs,
            "decision_context": build_confirmation_decision(payload, resume_value),
        }

    return human_confirm
