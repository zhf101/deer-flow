"""GDP Agent 已有场景满足节点。"""

from __future__ import annotations

from typing import Any

from app.gdp.agent.nodes.events import emit_waiting_user_event
from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.scene_tools import bind_scene_inputs, run_datagen_scene_for_task, search_scene_contracts
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService

AUTO_SELECT_MIN_SCORE = 0.25
CLOSE_SCORE_DELTA = 0.08


def build_scene_fulfillment_node(
    *,
    catalog_service: AgentCatalogService,
    task_service: DatagenTaskService,
    scene_service: SceneService,
):
    """构造已有场景满足节点。"""

    async def scene_fulfillment(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        visible_variable_summaries = [_visible_variable_summary(item) for item in task_run.visibleVariables]
        visible_variable_bindings = [_visible_variable_binding(item) for item in task_run.visibleVariables]
        result = await search_scene_contracts(
            catalog_service,
            goal=state.get("user_intent") or task_run.userIntent,
            env_code=state.get("env_code") or task_run.envCode,
            user_inputs=state.get("user_inputs") or {},
            visible_variables=visible_variable_summaries,
            limit=5,
        )
        executed_scene_codes = await _executed_scene_codes(task_service, task_run_id)
        result["candidates"] = [
            item
            for item in result["candidates"]
            if item["contract"]["sceneCode"] not in executed_scene_codes
        ]
        await task_service.record_event(
            task_run_id,
            event_type="SCENE_CANDIDATES_FOUND",
            phase=DatagenTaskPhase.SCENE_FULFILLMENT,
            message=f"已找到 {len(result['candidates'])} 个候选场景。",
            payload={"candidates": [_candidate_summary(item) for item in result["candidates"]]},
        )

        if not result["candidates"]:
            await task_service.move_to_phase(
                task_run_id,
                status=DatagenTaskStatus.RUNNING,
                phase=DatagenTaskPhase.SCENE_DESIGN,
                event_type="RESOURCE_MISSING",
                message="没有找到可复用的已发布造数场景，需要进入场景设计分支。",
                payload={"resourceType": "SCENE", "goal": task_run.userIntent},
            )
            return {
                "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
                "decision_context": {
                    "lastSceneResult": None,
                    "sceneSearch": {"resourceMissing": True, "resourceType": "SCENE", "candidateCount": 0}
                },
            }

        user_inputs = state.get("user_inputs") or {}
        selected_scene_code = user_inputs.get("selectedSceneCode")
        top = _select_candidate(result["candidates"], selected_scene_code)
        if top is None:
            details = _candidate_confirmation_details(
                result["candidates"],
                recommended=result["candidates"][0]["contract"]["sceneCode"],
                confirmation_reason="INVALID_SELECTION",
            )
            details["invalidSelectedSceneCode"] = str(selected_scene_code)
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                "resumePhase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                "questionType": "SCENE_CANDIDATE_CONFIRM",
                "question": "选择的造数场景不存在，请重新确认本次任务优先使用哪一个。",
                "details": details,
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="选择的候选场景不存在，等待用户重新确认。")
            emit_waiting_user_event(pending, message="选择的候选场景不存在，等待用户重新确认。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "sceneCandidates": [_candidate_summary(item) for item in result["candidates"]],
                    "invalidSelectedSceneCode": str(selected_scene_code),
                },
            }
        confirmation_reason = _candidate_confirmation_reason(
            result["candidates"],
            top,
            selected_code=selected_scene_code,
        )
        if confirmation_reason:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                "resumePhase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                "questionType": "SCENE_CANDIDATE_CONFIRM",
                "question": "找到多个可能可用的造数场景，请确认本次任务优先使用哪一个。",
                "details": _candidate_confirmation_details(
                    result["candidates"],
                    recommended=top["contract"]["sceneCode"],
                    confirmation_reason=confirmation_reason,
                ),
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="候选场景不够明确，等待用户确认。")
            emit_waiting_user_event(pending, message="候选场景不够明确，等待用户确认。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "sceneCandidates": [_candidate_summary(item) for item in result["candidates"]],
                    "recommendedSceneCode": top["contract"]["sceneCode"],
                    "sceneConfirmationReason": confirmation_reason,
                },
            }

        contract = top["contract"]
        if top["missingInputs"]:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                "questionType": "SCENE_INPUT_REQUIRED",
                "question": "候选场景仍缺少必填入参，请补充后继续。",
                "details": {
                    "sceneCode": contract["sceneCode"],
                    "missingInputs": top["missingInputs"],
                },
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="候选场景缺少必填入参，等待用户补充。")
            emit_waiting_user_event(pending, message="候选场景缺少必填入参，等待用户补充。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": _selected_scene_decision(top),
            }

        if top["requiresConfirmation"]:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_EXECUTING.value,
                "questionType": "WRITE_SCENE_APPROVAL",
                "question": "候选场景会写入或变更业务数据，是否确认执行？",
                "details": {
                    "sceneCode": contract["sceneCode"],
                    "envCode": task_run.envCode,
                    "sideEffects": contract["sideEffects"],
                },
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="写操作场景执行前需要用户确认。")
            emit_waiting_user_event(pending, message="写操作场景执行前需要用户确认。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": _selected_scene_decision(top),
            }

        bindings = await bind_scene_inputs(
            catalog_service,
            scene_code=contract["sceneCode"],
            user_inputs=state.get("user_inputs") or {},
            visible_variables=visible_variable_bindings,
        )
        scene_result = await run_datagen_scene_for_task(
            task_service,
            scene_service,
            task_run_id=task_run_id,
            scene_code=contract["sceneCode"],
            env_code=task_run.envCode,
            input_params=bindings["bindings"],
            goal=task_run.userIntent,
        )
        result_ref = _scene_result_ref(contract["sceneCode"], scene_result)
        return {
            "current_phase": DatagenTaskPhase.PROGRESS_REFLECTION.value,
            "decision_context": {
                **_selected_scene_decision(top),
                "inputBinding": bindings,
                "lastSceneResult": scene_result,
            },
            "last_result_ref": result_ref,
            "result_refs": [result_ref],
        }

    return scene_fulfillment


def _select_candidate(candidates: list[dict[str, Any]], selected_code: Any) -> dict[str, Any] | None:
    if selected_code:
        for candidate in candidates:
            if candidate["contract"]["sceneCode"] == str(selected_code):
                return candidate
        return None
    return candidates[0]


def _candidate_confirmation_reason(
    candidates: list[dict[str, Any]],
    top: dict[str, Any],
    *,
    selected_code: Any,
) -> str | None:
    if selected_code:
        return None
    if len(candidates) < 2:
        return "LOW_CONFIDENCE" if top["score"] < AUTO_SELECT_MIN_SCORE else None
    if candidates[1]["score"] >= top["score"]:
        return "SAME_SCORE"
    if top["score"] - candidates[1]["score"] <= CLOSE_SCORE_DELTA:
        return "CLOSE_SCORE"
    if top["score"] < AUTO_SELECT_MIN_SCORE:
        return "LOW_CONFIDENCE"
    return None


def _candidate_confirmation_details(
    candidates: list[dict[str, Any]],
    *,
    recommended: str,
    confirmation_reason: str,
) -> dict[str, Any]:
    return {
        "selectionKey": "selectedSceneCode",
        "selectionType": "single",
        "recommended": recommended,
        "confirmationReason": confirmation_reason,
        "autoSelectMinScore": AUTO_SELECT_MIN_SCORE,
        "closeScoreDelta": CLOSE_SCORE_DELTA,
        "candidates": [_candidate_summary(item) for item in candidates],
    }


async def _executed_scene_codes(task_service: DatagenTaskService, task_run_id: str) -> set[str]:
    steps = await task_service.list_steps(task_run_id)
    return {
        str(step.selectedResource.get("sceneCode"))
        for step in steps
        if step.selectedResource and step.selectedResource.get("sceneCode")
    }


def _visible_variable_summary(variable: Any) -> dict[str, Any]:
    return {
        "name": variable.name,
        "semanticType": variable.semanticType,
        "label": variable.label,
        "valueSchema": variable.valueSchema,
        "valuePreview": None if variable.sensitive else variable.valuePreview,
        "valueSize": variable.valueSize.model_dump(mode="json") if variable.valueSize else None,
        "sensitive": variable.sensitive,
        "confidence": variable.confidence,
    }


def _visible_variable_binding(variable: Any) -> dict[str, Any]:
    return {
        "name": variable.name,
        "semanticType": variable.semanticType,
        "label": variable.label,
        "value": variable.value,
        "valuePreview": None if variable.sensitive else variable.valuePreview,
        "valueSize": variable.valueSize.model_dump(mode="json") if variable.valueSize else None,
        "sensitive": variable.sensitive,
        "confidence": variable.confidence,
    }


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    contract = candidate["contract"]
    return {
        "sceneCode": contract["sceneCode"],
        "sceneName": contract["sceneName"],
        "capabilityType": contract["capabilityType"],
        "businessDomain": contract["businessDomain"],
        "hasSideEffects": contract["hasSideEffects"],
        "score": candidate["score"],
        "reasons": candidate["reasons"],
        "missingInputs": candidate["missingInputs"],
        "requiresConfirmation": candidate["requiresConfirmation"],
    }


def _selected_scene_decision(candidate: dict[str, Any]) -> dict[str, Any]:
    contract = candidate["contract"]
    return {
        "lastSceneResult": None,
        "selectedSceneCode": contract["sceneCode"],
        "selectedSceneCandidate": candidate,
        "selectedSceneSummary": _candidate_summary(candidate),
    }


def _scene_result_ref(scene_code: str, scene_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_type": "SCENE_RUN",
        "task_step_id": scene_result.get("taskStepId"),
        "scene_run_id": scene_result.get("sceneRunId"),
        "scene_code": scene_code,
        "summary": {
            "success": scene_result.get("success"),
            "sceneStatus": scene_result.get("sceneStatus"),
            "outputKeys": scene_result.get("outputKeys") or sorted((scene_result.get("finalOutput") or {}).keys()),
            "finalOutputSize": scene_result.get("finalOutputSize"),
            "errorCount": len(scene_result.get("errors") or []),
        },
    }
