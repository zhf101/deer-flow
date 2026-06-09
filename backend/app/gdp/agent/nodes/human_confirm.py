"""GDP Agent 人工确认节点。"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_human_confirm_node(task_service: DatagenTaskService):
    """构造人工确认节点。"""

    async def human_confirm(state: GDPState) -> GDPState:
        payload = state.get("pending_confirmation") or {}
        resume_value = interrupt(payload)
        task_run_id = state["task_run_id"]
        next_phase = _resolve_resume_phase(payload)
        user_inputs = _merge_user_inputs(state.get("user_inputs") or {}, resume_value, payload)
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
            "confirmation_result": resume_value,
            "user_inputs": user_inputs,
        }

    return human_confirm


def _resolve_resume_phase(payload: dict[str, Any]) -> DatagenTaskPhase:
    explicit = payload.get("resumePhase")
    if explicit:
        return DatagenTaskPhase(str(explicit))
    question_type = str(payload.get("questionType") or "")
    if question_type == "WRITE_SCENE_APPROVAL":
        return DatagenTaskPhase.SCENE_EXECUTING
    if question_type == "SCENE_INPUT_REQUIRED":
        return DatagenTaskPhase.SCENE_FULFILLMENT
    if question_type == "SOURCE_INPUT_REQUIRED":
        return DatagenTaskPhase.SCENE_DESIGN
    if question_type.startswith("SOURCE_CONFIG"):
        return DatagenTaskPhase.SOURCE_CONFIG
    if question_type.startswith("INFRA_CONFIG"):
        return DatagenTaskPhase.INFRA_CONFIG
    phase = payload.get("phase")
    if phase and phase != DatagenTaskPhase.WAITING_USER.value:
        return DatagenTaskPhase(str(phase))
    return DatagenTaskPhase.PROGRESS_REFLECTION


def _merge_user_inputs(
    current: dict[str, Any],
    resume_value: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current)
    if isinstance(resume_value, dict):
        if isinstance(resume_value.get("inputs"), dict):
            merged.update(resume_value["inputs"])
        for key in (
            "source",
            "sourceConfig",
            "sourceType",
            "config",
            "httpSource",
            "sqlSource",
            "infra",
            "infraConfig",
            "system",
            "environment",
            "serviceEndpoint",
            "datasource",
            "selectedSceneCode",
            "selectedSourceCode",
        ):
            if key in resume_value:
                merged[key] = resume_value[key]
        if "reply" in resume_value:
            _merge_scalar_reply(merged, resume_value["reply"], payload)
        return merged
    _merge_scalar_reply(merged, resume_value, payload)
    return merged


def _merge_scalar_reply(merged: dict[str, Any], value: Any, payload: dict[str, Any]) -> None:
    missing_inputs = ((payload.get("details") or {}).get("missingInputs") or [])
    if len(missing_inputs) == 1:
        merged[str(missing_inputs[0])] = value
