"""GDP Agent 场景设计节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.llm.decision import llm_decision_payload, llm_failure_payload, select_gdp_source_candidate
from app.gdp.agent.llm.schemas import GDPSourceCandidateDecision
from app.gdp.agent.middlewares.business_guardrail import GDPToolApprovalContext
from app.gdp.agent.nodes.events import emit_waiting_user_event
from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.registry import assert_gdp_registered_tool_allowed, evaluate_gdp_registered_tool_guardrail
from app.gdp.agent.tools.scene_design_tools import (
    SceneDraftCompositionResult,
    compose_scene_draft_preview_from_source,
    publish_scene_from_source,
    search_source_contracts,
)
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.config.app_config import AppConfig

AUTO_SELECT_MIN_SCORE = 0.25
CLOSE_SCORE_DELTA = 0.08
LLM_CANDIDATE_MIN_CONFIDENCE = 0.6


def build_scene_design_node(
    *,
    catalog_service: AgentCatalogService,
    task_service: DatagenTaskService,
    scene_service: SceneService,
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
    app_config: AppConfig | None = None,
    llm_enabled: bool = False,
    llm_model: Any | None = None,
):
    """构造缺场景时的场景设计节点。"""

    async def scene_design(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
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
                "decision_context": {
                    "lastSceneResult": None,
                    "sourceSearch": {"resourceMissing": True, "resourceType": "SOURCE", "candidateCount": 0}
                },
            }

        user_inputs = state.get("user_inputs") or {}
        selected_source_code = user_inputs.get("selectedSourceCode")
        llm_decision: GDPSourceCandidateDecision | None = None
        llm_state_update: dict[str, Any] = {}
        if selected_source_code:
            top = _select_source_candidate(source_result["candidates"], selected_source_code)
            if top is None:
                details = _source_candidate_confirmation_details(
                    source_result["candidates"],
                    recommended=source_result["candidates"][0]["contract"]["sourceCode"],
                    confirmation_reason="INVALID_SELECTION",
                )
                details["invalidSelectedSourceCode"] = str(selected_source_code)
                pending = {
                    "taskRunId": task_run_id,
                    "phase": DatagenTaskPhase.SCENE_DESIGN.value,
                    "resumePhase": DatagenTaskPhase.SCENE_DESIGN.value,
                    "questionType": "SOURCE_CANDIDATE_CONFIRM",
                    "question": "选择的 Source 不存在，请重新确认本次任务优先使用哪一个。",
                    "details": details,
                }
                await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="选择的候选 Source 不存在，等待用户重新确认。")
                emit_waiting_user_event(pending, message="选择的候选 Source 不存在，等待用户重新确认。")
                return {
                    "current_phase": DatagenTaskPhase.WAITING_USER.value,
                    "pending_confirmation": pending,
                    "decision_context": {
                        "lastSceneResult": None,
                        "sourceCandidates": [_candidate_summary(item) for item in source_result["candidates"]],
                        "invalidSelectedSourceCode": str(selected_source_code),
                    },
                }
            confirmation_reason = _source_candidate_confirmation_reason(
                source_result["candidates"],
                top,
                selected_code=selected_source_code,
            )
        else:
            llm_decision, llm_state_update = await _try_select_source_candidate_with_llm(
                task_service,
                task_run_id,
                goal=task_run.userIntent,
                candidates=source_result["candidates"],
                user_inputs=user_inputs,
                visible_variables=visible_variables,
                context_summary=state.get("context_summary") or {},
                config=config,
                app_config=app_config,
                llm_enabled=llm_enabled,
                llm_model=llm_model,
            )
            if llm_decision is not None and llm_decision.decision == "NO_MATCH":
                await task_service.move_to_phase(
                    task_run_id,
                    status=DatagenTaskStatus.RUNNING,
                    phase=DatagenTaskPhase.SOURCE_CONFIG,
                    event_type="RESOURCE_MISSING",
                    message="模型判断候选 Source 无法支撑目标，需要进入 Source 配置分支。",
                    payload={
                        "resourceType": "SOURCE",
                        "goal": task_run.userIntent,
                        "llmDecision": llm_decision.model_dump(mode="json"),
                    },
                )
                return {
                    "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
                    "decision_context": {
                        "lastSceneResult": None,
                        "sourceSearch": {
                            "resourceMissing": True,
                            "resourceType": "SOURCE",
                            "candidateCount": len(source_result["candidates"]),
                            "reason": llm_decision.reason,
                        },
                        **_llm_source_context(llm_decision),
                    },
                    **llm_state_update,
                }
            if llm_decision is not None:
                top = _select_source_candidate(source_result["candidates"], llm_decision.sourceCode)
                if top is None:
                    # 防御：模型给出的 sourceCode 未命中候选时，不静默回退到第一个候选，
                    # 改为推荐第一个候选并强制交给用户确认（与非 LLM 路径的无效选择行为一致）。
                    top = source_result["candidates"][0]
                    confirmation_reason = "LLM_REQUIRES_CONFIRMATION"
                else:
                    confirmation_reason = "LLM_REQUIRES_CONFIRMATION" if _llm_source_needs_confirmation(llm_decision) else None
            else:
                top = _select_source_candidate(source_result["candidates"], selected_source_code)
                confirmation_reason = _source_candidate_confirmation_reason(
                    source_result["candidates"],
                    top,
                    selected_code=selected_source_code,
                )

        if confirmation_reason:
            details = _source_candidate_confirmation_details(
                source_result["candidates"],
                recommended=top["contract"]["sourceCode"],
                confirmation_reason=confirmation_reason,
            )
            if llm_decision is not None:
                details["llmDecision"] = llm_decision.model_dump(mode="json")
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_DESIGN.value,
                "resumePhase": DatagenTaskPhase.SCENE_DESIGN.value,
                "questionType": "SOURCE_CANDIDATE_CONFIRM",
                "question": "找到多个可用于生成场景的 Source，请确认本次优先使用哪一个。",
                "details": details,
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="候选 Source 不够明确，等待用户确认。")
            emit_waiting_user_event(pending, message="候选 Source 不够明确，等待用户确认。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    "lastSceneResult": None,
                    "sourceCandidates": [_candidate_summary(item) for item in source_result["candidates"]],
                    "recommendedSourceCode": top["contract"]["sourceCode"],
                    "sourceConfirmationReason": confirmation_reason,
                    **_llm_source_context(llm_decision),
                },
                **llm_state_update,
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
            emit_waiting_user_event(pending, message="候选 Source 缺少必填入参，等待用户补充。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {**_selected_source_decision(top), **_llm_source_context(llm_decision)},
                **llm_state_update,
            }

        publish_input = {
            "task_run_id": task_run_id,
            "source_contract": top["contract"],
        }
        publish_context = _scene_publish_approval_context(state)
        publish_decision = evaluate_gdp_registered_tool_guardrail(
            "publish_scene_from_source",
            publish_input,
            publish_context,
        )
        if not publish_decision.allowed:
            scene_preview = await _try_compose_scene_draft_preview(
                task_service,
                task_run_id,
                goal=task_run.userIntent,
                source_contract=top["contract"],
                http_source_repository=http_source_repository,
                sql_source_repository=sql_source_repository,
                user_inputs=user_inputs,
                visible_variables=visible_variables,
                context_summary=state.get("context_summary") or {},
                normalized_goal=state.get("normalized_goal") or task_run.normalizedGoal,
                config=config,
                app_config=app_config,
                llm_enabled=llm_enabled,
                llm_model=llm_model,
            )
            pending = {
                "taskRunId": task_run_id,
                "phase": DatagenTaskPhase.SCENE_DESIGN.value,
                "resumePhase": DatagenTaskPhase.SCENE_DESIGN.value,
                "questionType": "SCENE_PUBLISH_APPROVAL",
                "question": "即将根据候选 Source 自动发布新的造数场景，是否确认发布？",
                "details": {
                    "toolName": publish_decision.toolName,
                    "approvalKey": publish_decision.approvalKey,
                    "sourceCode": top["contract"]["sourceCode"],
                    "sourceName": top["contract"]["sourceName"],
                    "sourceType": top["contract"]["sourceType"],
                    "envCode": task_run.envCode,
                    "sideEffectLevel": publish_decision.sideEffectLevel,
                    "reason": publish_decision.reason,
                    **_scene_draft_preview_details(scene_preview),
                },
            }
            await task_service.mark_waiting_user(task_run_id, pending_interrupts=pending, message="场景自动发布前需要用户确认。")
            emit_waiting_user_event(pending, message="场景自动发布前需要用户确认。")
            return {
                "current_phase": DatagenTaskPhase.WAITING_USER.value,
                "pending_confirmation": pending,
                "decision_context": {
                    **_selected_source_decision(top),
                    **_llm_source_context(llm_decision),
                    **_scene_draft_preview_context(scene_preview),
                    "scenePublishGuardrail": publish_decision.model_dump(mode="json"),
                },
                **llm_state_update,
            }
        assert_gdp_registered_tool_allowed(
            "publish_scene_from_source",
            publish_input,
            publish_context,
        )
        published = await publish_scene_from_source(
            task_service=task_service,
            scene_service=scene_service,
            http_source_repository=http_source_repository,
            sql_source_repository=sql_source_repository,
            task_run_id=task_run_id,
            goal=task_run.userIntent,
            source_contract=top["contract"],
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            context_summary=state.get("context_summary") or {},
            normalized_goal=state.get("normalized_goal") or task_run.normalizedGoal,
            config=config,
            app_config=app_config,
            llm_enabled=llm_enabled,
            llm_model=llm_model,
        )
        return {
            "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            "decision_context": {
                **_selected_source_decision(top),
                **_llm_source_context(llm_decision),
                "publishedScene": published,
            },
            "last_result_ref": {
                "ref_type": "SCENE_DEFINITION",
                "scene_code": published.get("sceneCode"),
                "source_code": top["contract"].get("sourceCode"),
                "summary": {"published": published.get("success"), "sceneCode": published.get("sceneCode")},
            },
            **llm_state_update,
        }

    return scene_design


async def _try_compose_scene_draft_preview(
    task_service: DatagenTaskService,
    task_run_id: str,
    *,
    goal: str,
    source_contract: dict[str, Any],
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
    user_inputs: dict[str, Any],
    visible_variables: list[dict[str, Any]],
    context_summary: dict[str, Any],
    normalized_goal: dict[str, Any],
    config: RunnableConfig | None,
    app_config: AppConfig | None,
    llm_enabled: bool,
    llm_model: Any | None,
) -> SceneDraftCompositionResult | None:
    """生成审批前场景草稿预览，失败时不阻断用户审批。"""

    try:
        return await compose_scene_draft_preview_from_source(
            task_run_id=task_run_id,
            goal=goal,
            source_contract=source_contract,
            http_source_repository=http_source_repository,
            sql_source_repository=sql_source_repository,
            task_service=task_service,
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            context_summary=context_summary,
            normalized_goal=normalized_goal,
            config=config,
            app_config=app_config,
            llm_enabled=llm_enabled,
            llm_model=llm_model,
            stage="approval_preview",
        )
    except Exception as exc:
        await task_service.record_event(
            task_run_id,
            event_type="SCENE_DRAFT_PREVIEW_FAILED",
            phase=DatagenTaskPhase.SCENE_DESIGN,
            message="生成场景发布审批预览失败，已保留原发布审批流程。",
            payload=llm_failure_payload(exc),
        )
        return None


async def _try_select_source_candidate_with_llm(
    task_service: DatagenTaskService,
    task_run_id: str,
    *,
    goal: str,
    candidates: list[dict[str, Any]],
    user_inputs: dict[str, Any],
    visible_variables: list[dict[str, Any]],
    context_summary: dict[str, Any],
    config: RunnableConfig | None,
    app_config: AppConfig | None,
    llm_enabled: bool,
    llm_model: Any | None,
) -> tuple[GDPSourceCandidateDecision | None, dict[str, Any]]:
    """调用模型选择 Source 候选，失败时交回规则排序。"""

    if not llm_enabled:
        return None, {}
    try:
        decision = await select_gdp_source_candidate(
            goal=goal,
            candidates=candidates,
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            context_summary=context_summary,
            config=config,
            app_config=app_config,
            model=llm_model,
        )
        _validate_source_candidate_decision(decision, candidates)
        await task_service.record_event(
            task_run_id,
            event_type="LLM_SOURCE_SELECTED",
            phase=DatagenTaskPhase.SCENE_DESIGN,
            message="模型已在 Source 候选中给出选择建议。",
            payload=llm_decision_payload(decision),
        )
        return decision, _source_llm_state_update(decision)
    except Exception as exc:
        await task_service.record_event(
            task_run_id,
            event_type="LLM_SOURCE_SELECTION_FAILED",
            phase=DatagenTaskPhase.SCENE_DESIGN,
            message="模型选择 Source 候选失败，已回退到规则排序。",
            payload=llm_failure_payload(exc),
        )
        return None, {
            "last_llm_decision": {
                "decisionType": "source_candidate_selection",
                "decisionSource": "fallback_rule",
                "errorType": type(exc).__name__,
            },
        }


def _validate_source_candidate_decision(
    decision: GDPSourceCandidateDecision,
    candidates: list[dict[str, Any]],
) -> None:
    """确保模型只能选择已召回的 Source 候选。"""

    codes = {str(item["contract"]["sourceCode"]) for item in candidates}
    if decision.decision == "NO_MATCH":
        return
    if not decision.sourceCode:
        raise ValueError("模型 Source 候选决策缺少 sourceCode。")
    if str(decision.sourceCode) not in codes:
        raise ValueError(f"模型选择了不存在的 Source 候选：{decision.sourceCode}")
    invalid_rank = [code for code in decision.candidateRank if str(code) not in codes]
    if invalid_rank:
        raise ValueError(f"模型候选排序包含不存在的 Source：{', '.join(invalid_rank)}")


def _llm_source_needs_confirmation(decision: GDPSourceCandidateDecision) -> bool:
    """判断模型 Source 建议是否仍应交给用户确认。"""

    return (
        decision.decision == "ASK_USER"
        or decision.requiresUserConfirmation
        or decision.confidence < LLM_CANDIDATE_MIN_CONFIDENCE
    )


def _source_llm_state_update(decision: GDPSourceCandidateDecision) -> dict[str, Any]:
    """生成 Source 候选模型决策的 checkpoint 摘要。"""

    return {
        "last_llm_decision": {
            "decisionType": "source_candidate_selection",
            "decision": decision.decision,
            "sourceCode": decision.sourceCode,
            "confidence": decision.confidence,
            "reason": decision.reason,
        },
    }


def _llm_source_context(decision: GDPSourceCandidateDecision | None) -> dict[str, Any]:
    """把模型 Source 候选决策写入轻量决策上下文。"""

    if decision is None:
        return {}
    return {"llmSourceDecision": decision.model_dump(mode="json")}


def _scene_draft_preview_details(preview: SceneDraftCompositionResult | None) -> dict[str, Any]:
    """构造发布审批详情中的场景草稿预览。"""

    if preview is None:
        return {}
    return {
        "sceneDraftPreview": preview.scene.model_dump(mode="json"),
        "llmSceneDraftEnhanced": preview.enhanced,
        "llmSceneDraftDecision": _scene_draft_decision_summary(preview),
        "llmSceneDraftFallbackReason": preview.fallback_reason,
        "llmSceneDraftEventRef": preview.llm_event_ref,
    }


def _scene_draft_preview_context(preview: SceneDraftCompositionResult | None) -> dict[str, Any]:
    """把场景草稿预览摘要写入轻量决策上下文。"""

    if preview is None:
        return {}
    return {
        "sceneDraftPreviewSummary": {
            "sceneCode": preview.scene.sceneCode,
            "sceneName": preview.scene.sceneName,
            "llmEnhanced": preview.enhanced,
            "fallbackReason": preview.fallback_reason,
            "llmDecision": _scene_draft_decision_summary(preview),
        }
    }


def _scene_draft_decision_summary(preview: SceneDraftCompositionResult) -> dict[str, Any] | None:
    decision = preview.llm_decision
    if decision is None:
        return None
    return {
        "decision": decision.decision,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "missingInformation": decision.missingInformation,
        "assumptions": decision.assumptions,
        "evidence": decision.evidence,
    }


def _select_source_candidate(candidates: list[dict[str, Any]], selected_code: Any) -> dict[str, Any] | None:
    if selected_code:
        for candidate in candidates:
            if candidate["contract"]["sourceCode"] == str(selected_code):
                return candidate
        return None
    return candidates[0]


def _scene_publish_approval_context(state: GDPState) -> GDPToolApprovalContext:
    decision_context = state.get("decision_context") or {}
    approval = decision_context.get("scenePublishApproval") if isinstance(decision_context, dict) else None
    approved_keys: list[str] = []
    if isinstance(approval, dict) and approval.get("approved") is True:
        approval_key = approval.get("approvalKey")
        if approval_key:
            approved_keys.append(str(approval_key))
    return GDPToolApprovalContext(approvedApprovalKeys=approved_keys, operator=_operator(state), reason="场景发布审批上下文。")


def _operator(state: GDPState) -> str | None:
    runtime_context = state.get("runtime_context") or {}
    if isinstance(runtime_context, dict) and runtime_context.get("operator"):
        return str(runtime_context["operator"])
    return None


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


def _selected_source_decision(candidate: dict[str, Any]) -> dict[str, Any]:
    contract = candidate["contract"]
    return {
        "lastSceneResult": None,
        "selectedSourceCode": contract["sourceCode"],
        "selectedSourceCandidate": candidate,
        "selectedSourceSummary": _candidate_summary(candidate),
    }
