"""GDP Agent 中断恢复中间件工具。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.task.models import DatagenTaskPhase


def resolve_resume_phase(payload: dict[str, Any]) -> DatagenTaskPhase:
    """根据等待用户 payload 推断恢复后的业务阶段。"""

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
    elif question_type == "WRITE_SCENE_APPROVAL":
        decision["writeSceneApproval"] = resume_value
    return decision


def _merge_scalar_reply(merged: dict[str, Any], value: Any, payload: dict[str, Any]) -> None:
    missing_inputs = ((payload.get("details") or {}).get("missingInputs") or [])
    if len(missing_inputs) == 1:
        merged[str(missing_inputs[0])] = value
