"""GDP Agent 场景设计节点。"""

from __future__ import annotations

from typing import Any

from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.scene_design_tools import publish_scene_from_source, search_source_contracts
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService

AUTO_SELECT_MIN_SCORE = 0.25
CLOSE_SCORE_DELTA = 0.08


def build_scene_design_node(
    *,
    catalog_service: AgentCatalogService,
    task_service: DatagenTaskService,
    scene_service: SceneService,
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
):
    """构造缺场景时的场景设计节点。"""

    async def scene_design(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        visible_variables = [_visible_variable_summary(item) for item in task_run.visibleVariables]
        source_result = await search_source_contracts(
            catalog_service,
            goal=task_run.userIntent,
            env_code=task_run.envCode,
            user_inputs=state.get("user_inputs") or {},
            visible_variables=visible_variables,
            limit=5,
        )
        await task_service.record_event(
            task_run_id,
            event_type="SOURCE_CANDIDATES_FOUND",
            phase=DatagenTaskPhase.SCENE_DESIGN,
            message=f"已找到 {len(source_result['candidates'])} 个候选 Source。",
            payload={"candidates": [_candidate_summary(item) for item in source_result["candidates"]]},
        )

        if not source_result["candidates"]:
            await task_service.move_to_phase(
                task_run_id,
                status=DatagenTaskStatus.RUNNING,
                phase=DatagenTaskPhase.SOURCE_CONFIG,
                event_type="RESOURCE_MISSING",
                message="没有找到可用于生成场景的 HTTP/SQL Source，需要进入 Source 配置分支。",
                payload={"resourceType": "SOURCE", "goal": task_run.userIntent},
            )
            return {
                "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
                "last_tool_result": {"resourceMissing": True, "resourceType": "SOURCE", **source_result},
            }

        user_inputs = state.get("user_inputs") or {}
        top = _select_source_candidate(source_result["candidates"], user_inputs.get("selectedSourceCode"))
        confirmation_reason = _source_candidate_confirmation_reason(
            source_result["candidates"],
            top,
            selected_code=user_inputs.get("selectedSourceCode"),
        )
        if confirmation_reason:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_DESIGN.value,
                "resumePhase": DatagenTaskPhase.SCENE_DESIGN.value,
                "questionType": "SOURCE_CANDIDATE_CONFIRM",
                "question": "找到多个可用于生成场景的 Source，请确认本次优先使用哪一个。",
                "details": _source_candidate_confirmation_details(
                    source_result["candidates"],
                    recommended=top["contract"]["sourceCode"],
                    confirmation_reason=confirmation_reason,
                ),
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="候选 Source 不够明确，等待用户确认。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "last_tool_result": {"sourceCandidateConfirmationRequired": True, **source_result},
            }

        if top["missingInputs"]:
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_DESIGN.value,
                "questionType": "SOURCE_INPUT_REQUIRED",
                "question": "候选 Source 生成场景仍缺少必填入参，请补充后继续。",
                "details": {
                    "sourceCode": top["contract"]["sourceCode"],
                    "sourceType": top["contract"]["sourceType"],
                    "missingInputs": top["missingInputs"],
                },
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="候选 Source 缺少必填入参，等待用户补充。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "last_tool_result": {"selectedSourceCandidate": top, **source_result},
            }

        published = await publish_scene_from_source(
            task_service=task_service,
            scene_service=scene_service,
            http_source_repository=http_source_repository,
            sql_source_repository=sql_source_repository,
            task_run_id=task_run_id,
            goal=task_run.userIntent,
            source_contract=top["contract"],
        )
        return {
            "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            "last_tool_result": {"selectedSourceCandidate": top, "publishedScene": published, **source_result},
        }

    return scene_design


def _select_source_candidate(candidates: list[dict[str, Any]], selected_code: Any) -> dict[str, Any]:
    if selected_code:
        for candidate in candidates:
            if candidate["contract"]["sourceCode"] == str(selected_code):
                return candidate
    return candidates[0]


def _source_candidate_confirmation_reason(
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


def _source_candidate_confirmation_details(
    candidates: list[dict[str, Any]],
    *,
    recommended: str,
    confirmation_reason: str,
) -> dict[str, Any]:
    return {
        "selectionKey": "selectedSourceCode",
        "selectionType": "single",
        "recommended": recommended,
        "confirmationReason": confirmation_reason,
        "autoSelectMinScore": AUTO_SELECT_MIN_SCORE,
        "closeScoreDelta": CLOSE_SCORE_DELTA,
        "candidates": [_candidate_summary(item) for item in candidates],
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


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    contract = candidate["contract"]
    return {
        "sourceType": contract["sourceType"],
        "sourceCode": contract["sourceCode"],
        "sourceName": contract["sourceName"],
        "capabilityType": contract["capabilityType"],
        "businessDomain": contract["businessDomain"],
        "sysCode": contract["sysCode"],
        "hasSideEffects": contract["hasSideEffects"],
        "score": candidate["score"],
        "reasons": candidate["reasons"],
        "missingInputs": candidate["missingInputs"],
        "requiresConfirmation": candidate["requiresConfirmation"],
    }
