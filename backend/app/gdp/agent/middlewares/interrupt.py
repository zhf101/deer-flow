"""GDP Agent 中断恢复中间件工具。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.task_run_sync import build_gdp_task_context
from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.redaction import redact_sensitive_payload

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_interrupt(
    *,
    node_name: str,
    node: GDPNodeCallable,
    task_service: DatagenTaskService,
) -> GDPNodeCallable:
    """规范节点返回的等待用户状态，确保 checkpoint 与 TaskRun 中断语义一致。"""

    async def interrupt_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        result = await node(state, config)
        if not isinstance(result, dict) or not _is_waiting_user_result(result):
            return result

        task_run_id = _resolve_task_run_id(result, state)
        task_run = await _safe_get_task_run(task_service, task_run_id) if task_run_id else None
        pending_source = result.get("pending_confirmation") or getattr(task_run, "pendingInterrupts", None) or {}
        pending, repairs = _normalize_pending_confirmation(
            pending_source,
            task_run_id=task_run_id,
            previous_phase=state.get("current_phase"),
        )
        normalized = _with_waiting_context(result, pending, task_run)
        if repairs and task_run_id:
            await _record_interrupt_repaired(task_service, task_run_id, node_name, pending, repairs)
        return normalized

    return interrupt_node


def resolve_resume_phase(payload: dict[str, Any]) -> DatagenTaskPhase:
    """根据等待用户 payload 推断恢复后的业务阶段。"""

    explicit = payload.get("resumePhase")
    if explicit:
        return DatagenTaskPhase(str(explicit))
    question_type = str(payload.get("questionType") or "")
    if question_type == "WRITE_SCENE_APPROVAL":
        return DatagenTaskPhase.SCENE_EXECUTING
    if question_type == "SCENE_PUBLISH_APPROVAL":
        return DatagenTaskPhase.SCENE_DESIGN
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


def merge_user_inputs_from_resume(
    current: dict[str, Any],
    resume_value: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """把用户恢复回复归并成后续节点统一读取的 user_inputs。"""

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


def build_confirmation_decision(payload: dict[str, Any], resume_value: Any) -> dict[str, Any]:
    """构造恢复回复对应的轻量决策上下文。"""

    question_type = str(payload.get("questionType") or "")
    decision: dict[str, Any] = {
        "lastConfirmation": {
            "questionType": question_type,
            "phase": payload.get("phase"),
            "resumePhase": payload.get("resumePhase"),
            "reply": resume_value,
        }
    }
    if isinstance(resume_value, dict):
        if "selectedSceneCode" in resume_value:
            decision["selectedSceneCode"] = str(resume_value["selectedSceneCode"])
        if "selectedSourceCode" in resume_value:
            decision["selectedSourceCode"] = str(resume_value["selectedSourceCode"])
        if question_type == "WRITE_SCENE_APPROVAL":
            decision["writeSceneApproval"] = resume_value
        if question_type == "SCENE_PUBLISH_APPROVAL":
            decision["scenePublishApproval"] = _approval_decision(payload, resume_value)
    elif question_type == "WRITE_SCENE_APPROVAL":
        decision["writeSceneApproval"] = resume_value
    elif question_type == "SCENE_PUBLISH_APPROVAL":
        decision["scenePublishApproval"] = _approval_decision(payload, resume_value)
    return decision


def _merge_scalar_reply(merged: dict[str, Any], value: Any, payload: dict[str, Any]) -> None:
    missing_inputs = ((payload.get("details") or {}).get("missingInputs") or [])
    if len(missing_inputs) == 1:
        merged[str(missing_inputs[0])] = value


def _approval_decision(payload: dict[str, Any], resume_value: Any) -> dict[str, Any]:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    return {
        "approved": _is_approved_reply(resume_value),
        "reply": resume_value,
        "approvalKey": details.get("approvalKey"),
        "toolName": details.get("toolName"),
        "sourceCode": details.get("sourceCode"),
        "sceneCode": details.get("sceneCode"),
    }


def _is_approved_reply(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        for key in ("approved", "confirm", "confirmed", "yes"):
            if value.get(key) is True:
                return True
        text = str(value.get("reply") or value.get("answer") or "")
        return _is_positive_text(text)
    if isinstance(value, str):
        return _is_positive_text(value)
    return False


def _is_positive_text(value: str) -> bool:
    return value.strip().lower() in {"y", "yes", "ok", "true", "确认", "同意", "继续", "执行", "发布"}


def _is_waiting_user_result(result: GDPState) -> bool:
    if result.get("current_phase") == DatagenTaskPhase.WAITING_USER.value:
        return True
    if result.get("pending_confirmation"):
        return True
    task_context = result.get("task_context") or {}
    if isinstance(task_context, dict):
        return task_context.get("status") == DatagenTaskStatus.WAITING_USER.value
    return False


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


async def _safe_get_task_run(task_service: DatagenTaskService, task_run_id: str):
    try:
        return await task_service.get_task_run(task_run_id)
    except Exception:
        return None


def _normalize_pending_confirmation(
    pending: Any,
    *,
    task_run_id: str | None,
    previous_phase: Any,
) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(pending) if isinstance(pending, dict) else {}
    repairs: list[str] = []
    if task_run_id and normalized.get("taskRunId") != task_run_id:
        normalized["taskRunId"] = task_run_id
        repairs.append("taskRunId")
    if previous_phase and not normalized.get("phase"):
        normalized["phase"] = str(previous_phase)
        repairs.append("phase")
    if "details" not in normalized:
        normalized["details"] = {}
        repairs.append("details")
    return redact_sensitive_payload(normalized), repairs


def _with_waiting_context(
    result: GDPState,
    pending: dict[str, Any],
    task_run: Any | None,
) -> GDPState:
    existing_task_context = dict(result.get("task_context") or {})
    if task_run is not None:
        existing_task_context.update(build_gdp_task_context(task_run))
    existing_task_context.update(
        {
            "status": DatagenTaskStatus.WAITING_USER.value,
            "phase": DatagenTaskPhase.WAITING_USER.value,
        }
    )
    return {
        **result,
        "current_phase": DatagenTaskPhase.WAITING_USER.value,
        "pending_confirmation": pending,
        "task_context": existing_task_context,
    }


async def _record_interrupt_repaired(
    task_service: DatagenTaskService,
    task_run_id: str,
    node_name: str,
    pending: dict[str, Any],
    repairs: list[str],
) -> None:
    try:
        await task_service.record_event(
            task_run_id,
            event_type="AGENT_INTERRUPT_NORMALIZED",
            phase=DatagenTaskPhase.WAITING_USER,
            message="已规范化 Agent 节点返回的等待用户 checkpoint 状态。",
            payload={
                "nodeName": node_name,
                "questionType": pending.get("questionType"),
                "questionPhase": pending.get("phase"),
                "repairedFields": repairs,
            },
        )
    except Exception:
        return
