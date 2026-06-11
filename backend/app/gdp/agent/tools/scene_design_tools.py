"""GDP Task Agent 场景设计工具。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool

from app.gdp.agent.llm.decision import enhance_gdp_scene_draft, llm_decision_payload, llm_failure_payload
from app.gdp.agent.llm.schemas import GDPSceneDraftEnhancementDecision
from app.gdp.agent.middlewares.idempotency import find_successful_scene_publish_step
from app.gdp.datagen.agent_catalog.models import AgentSourceSearchRequest
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.common.models import InputFieldDefinition, InputFieldType, StepType
from app.gdp.datagen.config.httpsource.models import HttpSourceResponse
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.models import (
    BatchConfig,
    HttpStepDefinition,
    SceneDefinition,
    SqlStepDefinition,
    StepTemplateRef,
)
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.scene.validation import validate_scene_draft
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter, SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.config.app_config import AppConfig

_INPUT_REF_RE = re.compile(r"\$\{input\.([A-Za-z_][A-Za-z0-9_]*)(?:[.\[].*?)?\}")


@dataclass
class SceneDraftCompositionResult:
    """场景草稿生成结果，携带模型补全审计摘要。"""

    scene: SceneDefinition
    base_scene: SceneDefinition
    llm_decision: GDPSceneDraftEnhancementDecision | None = None
    llm_event_ref: dict[str, Any] | None = None
    enhanced: bool = False
    fallback_reason: str | None = None


async def search_source_contracts(
    catalog_service: AgentCatalogService,
    *,
    goal: str,
    source_types: list[str] | None = None,
    env_code: str | None = None,
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """搜索可用于生成场景的 HTTP/SQL Source 能力契约。"""

    result = await catalog_service.search_source_contracts(
        AgentSourceSearchRequest(
            goal=goal,
            sourceTypes=source_types or ["HTTP", "SQL"],
            envCode=env_code,
            userInputs=user_inputs or {},
            visibleVariables=visible_variables or [],
            limit=limit,
        )
    )
    return result.model_dump(mode="json")


async def compose_scene_draft_from_source(
    *,
    task_run_id: str,
    goal: str,
    source_contract: dict[str, Any],
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
) -> SceneDefinition:
    """基于单个 Source 生成单步骤场景草稿。"""

    source_type = str(source_contract["sourceType"]).upper()
    if source_type == "HTTP":
        source = await http_source_repository.get_http_source(source_contract["sourceCode"])
        return _compose_http_scene(task_run_id=task_run_id, goal=goal, source=source)
    source = await sql_source_repository.get_sql_source(source_contract["sourceCode"])
    return _compose_sql_scene(task_run_id=task_run_id, goal=goal, source=source)


async def compose_scene_draft_preview_from_source(
    *,
    task_run_id: str,
    goal: str,
    source_contract: dict[str, Any],
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
    task_service: DatagenTaskService | None = None,
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    normalized_goal: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    llm_enabled: bool = False,
    llm_model: Any | None = None,
    stage: str = "approval_preview",
) -> SceneDraftCompositionResult:
    """生成场景草稿预览，并在开启模型时补全语义信息。"""

    base_scene = await compose_scene_draft_from_source(
        task_run_id=task_run_id,
        goal=goal,
        source_contract=source_contract,
        http_source_repository=http_source_repository,
        sql_source_repository=sql_source_repository,
    )
    if not llm_enabled:
        return SceneDraftCompositionResult(scene=base_scene, base_scene=base_scene)
    return await _try_enhance_scene_draft_with_llm(
        task_service=task_service,
        task_run_id=task_run_id,
        goal=goal,
        source_contract=source_contract,
        base_scene=base_scene,
        user_inputs=user_inputs or {},
        visible_variables=visible_variables or [],
        context_summary=context_summary or {},
        normalized_goal=normalized_goal or {},
        config=config,
        app_config=app_config,
        llm_model=llm_model,
        stage=stage,
    )


async def publish_scene_from_source(
    *,
    task_service: DatagenTaskService,
    scene_service: SceneService,
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
    task_run_id: str,
    goal: str,
    source_contract: dict[str, Any],
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    normalized_goal: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    llm_enabled: bool = False,
    llm_model: Any | None = None,
) -> dict[str, Any]:
    """基于 Source 生成、保存并发布新场景。"""

    source_code = str(source_contract["sourceCode"])
    steps = await task_service.list_steps(task_run_id)
    reused_step = find_successful_scene_publish_step(steps, source_code=source_code)
    if reused_step is not None:
        await task_service.record_event(
            task_run_id,
            event_type="SCENE_PUBLISH_IDEMPOTENT_REUSED",
            phase=DatagenTaskPhase.SCENE_DESIGN,
            message=f"检测到 Source {source_code} 已生成并发布过场景，复用已有场景。",
            payload={
                "taskStepId": reused_step.taskStepId,
                "sourceCode": source_code,
                "output": reused_step.output or {},
            },
        )
        return await _build_reused_scene_publish_output(scene_service, reused_step.output or {})

    composition = await compose_scene_draft_preview_from_source(
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
        stage="publish",
    )
    scene = composition.scene
    await task_service.record_event(
        task_run_id,
        event_type="SCENE_DRAFT_COMPOSED",
        phase=DatagenTaskPhase.SCENE_DESIGN,
        message=f"已基于 Source {source_contract['sourceCode']} 生成场景草稿 {scene.sceneCode}。",
        payload={
            "scene": scene.model_dump(mode="json"),
            "source": source_contract,
            "llmEnhanced": composition.enhanced,
            "llmDecision": _scene_draft_decision_summary(composition.llm_decision),
        },
    )
    created = await scene_service.create_scene(scene, operator="gdp_agent")
    published = await scene_service.publish_scene(created.sceneCode, operator="gdp_agent")
    await task_service.record_task_step(
        task_run_id,
        phase=DatagenTaskPhase.SCENE_DESIGN,
        step_type=DatagenTaskStepType.DESIGN_SCENE,
        goal=f"基于 Source {source_contract['sourceCode']} 生成并发布造数场景。",
        status=DatagenTaskStepStatus.SUCCESS,
        selected_resource={"source": source_contract},
        output={"sceneCode": published.sceneCode, "versionNo": published.versionNo},
    )
    await task_service.record_event(
        task_run_id,
        event_type="SCENE_AUTO_PUBLISHED",
        phase=DatagenTaskPhase.SCENE_DESIGN,
        message=f"已自动发布新场景 {published.sceneCode}。",
        payload={"sceneCode": published.sceneCode, "versionNo": published.versionNo},
    )
    await task_service.move_to_phase(
        task_run_id,
        status=DatagenTaskStatus.RUNNING,
        phase=DatagenTaskPhase.SCENE_FULFILLMENT,
        event_type="PHASE_CHANGED",
        message="新场景已发布，回到已有场景满足阶段继续执行。",
        payload={"from": DatagenTaskPhase.SCENE_DESIGN.value, "to": DatagenTaskPhase.SCENE_FULFILLMENT.value},
    )
    return {
        "sceneCode": published.sceneCode,
        "versionNo": published.versionNo,
        "definition": published.definition.model_dump(mode="json"),
        "llmEnhanced": composition.enhanced,
        "llmDecision": _scene_draft_decision_summary(composition.llm_decision),
    }


async def _build_reused_scene_publish_output(
    scene_service: SceneService,
    output: dict[str, Any],
) -> dict[str, Any]:
    """从已记录发布步骤恢复返回值，尽量补齐场景定义。"""

    result = dict(output)
    result["idempotentReuse"] = True
    scene_code = result.get("sceneCode")
    version_no = result.get("versionNo")
    if not scene_code or "definition" in result:
        return result
    try:
        version = await scene_service.get_scene_version(str(scene_code), version_no=int(version_no) if version_no else None)
    except Exception:
        return result
    result["definition"] = version.definition.model_dump(mode="json")
    return result


async def _try_enhance_scene_draft_with_llm(
    *,
    task_service: DatagenTaskService | None,
    task_run_id: str,
    goal: str,
    source_contract: dict[str, Any],
    base_scene: SceneDefinition,
    user_inputs: dict[str, Any],
    visible_variables: list[dict[str, Any]],
    context_summary: dict[str, Any],
    normalized_goal: dict[str, Any],
    config: RunnableConfig | None,
    app_config: AppConfig | None,
    llm_model: Any | None,
    stage: str,
) -> SceneDraftCompositionResult:
    """调用模型补全场景草稿，失败时保留后端基础草稿。"""

    try:
        decision = await enhance_gdp_scene_draft(
            goal=goal,
            source_contract=source_contract,
            base_scene_draft=base_scene.model_dump(mode="json"),
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            context_summary=context_summary,
            normalized_goal=normalized_goal,
            config=config,
            app_config=app_config,
            model=llm_model,
        )
        if decision.decision != "ENHANCE_SCENE":
            event_ref = await _record_scene_draft_llm_event(
                task_service,
                task_run_id,
                event_type="LLM_SCENE_DRAFT_KEPT",
                message="模型建议保持后端基础场景草稿或等待补充信息。",
                payload={**llm_decision_payload(decision), "stage": stage},
            )
            return SceneDraftCompositionResult(
                scene=base_scene,
                base_scene=base_scene,
                llm_decision=decision,
                llm_event_ref=event_ref,
                fallback_reason=decision.decision,
            )
        scene = _merge_scene_draft_enhancement(base_scene, decision, source_contract)
        event_ref = await _record_scene_draft_llm_event(
            task_service,
            task_run_id,
            event_type="LLM_SCENE_DRAFT_ENHANCED",
            message="模型已补全 SceneDefinition 场景草稿，后端已完成保护字段合并和草稿校验。",
            payload={**llm_decision_payload(decision), "stage": stage, "sceneCode": scene.sceneCode},
        )
        return SceneDraftCompositionResult(
            scene=scene,
            base_scene=base_scene,
            llm_decision=decision,
            llm_event_ref=event_ref,
            enhanced=True,
        )
    except Exception as exc:
        event_ref = await _record_scene_draft_llm_event(
            task_service,
            task_run_id,
            event_type="LLM_SCENE_DRAFT_ENHANCEMENT_FAILED",
            message="模型补全 SceneDefinition 场景草稿失败，已回退到后端基础草稿。",
            payload={**llm_failure_payload(exc), "stage": stage},
        )
        return SceneDraftCompositionResult(
            scene=base_scene,
            base_scene=base_scene,
            llm_event_ref=event_ref,
            fallback_reason=type(exc).__name__,
        )


async def _record_scene_draft_llm_event(
    task_service: DatagenTaskService | None,
    task_run_id: str,
    *,
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """记录场景草稿模型补全事件，供节点写入 checkpoint 引用。"""

    if task_service is None:
        return None
    event = await task_service.record_event(
        task_run_id,
        event_type=event_type,
        phase=DatagenTaskPhase.SCENE_DESIGN,
        message=message,
        payload=payload,
    )
    return {"eventId": event.eventId, "eventType": event.eventType, "decisionType": "scene_draft_enhancement"}


def _merge_scene_draft_enhancement(
    base_scene: SceneDefinition,
    decision: GDPSceneDraftEnhancementDecision,
    source_contract: dict[str, Any],
) -> SceneDefinition:
    """只把模型草稿中的语义字段合并回基础草稿。"""

    if not decision.sceneDraft:
        raise ValueError("模型场景草稿补全缺少 sceneDraft。")
    candidate = SceneDefinition.model_validate(decision.sceneDraft)
    if candidate.sceneCode != base_scene.sceneCode:
        raise ValueError("模型场景草稿不能修改 sceneCode。")

    base_payload = base_scene.model_dump(mode="json")
    candidate_payload = candidate.model_dump(mode="json")
    for field in ("sceneName", "sceneRemark", "sceneType", "businessDomain", "agentDescription"):
        if _has_semantic_value(candidate_payload.get(field)):
            base_payload[field] = candidate_payload[field]
    if candidate_payload.get("tags"):
        base_payload["tags"] = candidate_payload["tags"]
    if candidate_payload.get("preconditions"):
        base_payload["preconditions"] = candidate_payload["preconditions"]
    base_payload["sideEffects"] = _merge_side_effects(
        base_payload.get("sideEffects") or [],
        candidate_payload.get("sideEffects") or [],
    )
    base_payload["inputSchema"] = _merge_field_schema(
        base_payload.get("inputSchema") or [],
        candidate_payload.get("inputSchema") or [],
    )
    base_payload["resultSchema"] = _merge_field_schema(
        base_payload.get("resultSchema") or [],
        candidate_payload.get("resultSchema") or [],
    )
    base_payload["steps"] = _merge_step_semantics(
        base_payload.get("steps") or [],
        candidate_payload.get("steps") or [],
    )
    scene = SceneDefinition.model_validate(base_payload)
    _validate_source_backed_scene_integrity(base_scene, scene, source_contract)
    validation = validate_scene_draft(scene)
    if not validation.valid:
        messages = "；".join(issue.message for issue in validation.issues)
        raise ValueError(f"模型补全后的场景草稿未通过草稿校验：{messages}")
    return scene


def _merge_field_schema(
    base_fields: list[dict[str, Any]],
    candidate_fields: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按字段名合并字段中文名、备注和语义元数据，保留后端字段骨架。"""

    candidates_by_name = {str(field.get("name")): field for field in candidate_fields if field.get("name")}
    result: list[dict[str, Any]] = []
    for base_field in base_fields:
        merged = dict(base_field)
        candidate = candidates_by_name.get(str(base_field.get("name") or ""))
        if candidate:
            for key in ("label", "remark", "semanticType", "aliases", "exampleValue", "optionsSource", "validation", "batchEnabled"):
                if _has_semantic_value(candidate.get(key)):
                    merged[key] = candidate[key]
            if isinstance(merged.get("children"), list) and isinstance(candidate.get("children"), list):
                merged["children"] = _merge_field_schema(merged["children"], candidate["children"])
        result.append(merged)
    return result


def _merge_step_semantics(
    base_steps: list[dict[str, Any]],
    candidate_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并步骤展示说明和输出元数据，保留执行配置。"""

    candidates_by_id = {str(step.get("stepId")): step for step in candidate_steps if step.get("stepId")}
    result: list[dict[str, Any]] = []
    for base_step in base_steps:
        merged = dict(base_step)
        candidate = candidates_by_id.get(str(base_step.get("stepId") or ""))
        if candidate and candidate.get("type") == base_step.get("type"):
            for key in ("stepName", "description"):
                if _has_semantic_value(candidate.get(key)):
                    merged[key] = candidate[key]
            merged["outputMeta"] = _merge_output_meta(
                merged.get("outputMapping") or {},
                merged.get("outputMeta") or {},
                candidate.get("outputMeta") or {},
            )
        result.append(merged)
    return result


def _merge_output_meta(
    output_mapping: dict[str, Any],
    base_meta: dict[str, Any],
    candidate_meta: dict[str, Any],
) -> dict[str, Any]:
    """只为已有输出字段补全 label、remark 和 semanticType。"""

    result = {str(name): dict(meta or {}) for name, meta in base_meta.items()}
    for output_name in output_mapping:
        candidate = candidate_meta.get(output_name)
        if not isinstance(candidate, dict):
            continue
        current = result.setdefault(str(output_name), {})
        for key in ("label", "remark", "semanticType"):
            if _has_semantic_value(candidate.get(key)):
                current[key] = candidate[key]
    return result


def _merge_side_effects(
    base_effects: list[dict[str, Any]],
    candidate_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """保留已有副作用，并允许模型补充副作用说明或追加更保守的风险描述。"""

    result = [dict(effect) for effect in base_effects]
    matched_indexes: set[int] = set()
    for effect in result:
        match_index, candidate = _find_side_effect_match(effect, candidate_effects)
        if candidate is None:
            continue
        matched_indexes.add(match_index)
        if _has_semantic_value(candidate.get("description")):
            effect["description"] = candidate["description"]
    for index, candidate in enumerate(candidate_effects):
        if index not in matched_indexes:
            result.append(candidate)
    return result


def _find_side_effect_match(
    effect: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[int, dict[str, Any] | None]:
    for index, candidate in enumerate(candidates):
        if candidate.get("effectType") == effect.get("effectType") and candidate.get("target") == effect.get("target"):
            return index, candidate
    return -1, None


def _validate_source_backed_scene_integrity(
    base_scene: SceneDefinition,
    scene: SceneDefinition,
    source_contract: dict[str, Any],
) -> None:
    """确保模型补全没有改变 Source 导入步骤身份。"""

    if scene.sceneCode != base_scene.sceneCode:
        raise ValueError("模型补全后的 sceneCode 与基础草稿不一致。")
    if len(scene.steps) != len(base_scene.steps):
        raise ValueError("模型补全不能增删 Source 生成的基础步骤。")
    source_code = str(source_contract["sourceCode"])
    for base_step, step in zip(base_scene.steps, scene.steps, strict=True):
        if step.stepId != base_step.stepId or step.type != base_step.type:
            raise ValueError("模型补全不能修改 Source 步骤身份。")
        if base_step.templateRef is None:
            continue
        if step.templateRef is None:
            raise ValueError("模型补全不能删除 Source 步骤快照引用。")
        if step.templateRef.sourceCode != base_step.templateRef.sourceCode or step.templateRef.sourceCode != source_code:
            raise ValueError("模型补全不能修改 Source 步骤快照 sourceCode。")


def _has_semantic_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | dict):
        return bool(value)
    return True


def _scene_draft_decision_summary(decision: GDPSceneDraftEnhancementDecision | None) -> dict[str, Any] | None:
    """生成场景草稿模型决策摘要，避免重复塞入完整草稿。"""

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


def build_scene_design_tools(
    *,
    catalog_service: AgentCatalogService,
    task_service: DatagenTaskService,
    scene_service: SceneService,
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
) -> list[StructuredTool]:
    """构造场景设计阶段 LangChain 工具。"""

    async def _search_source_contracts(
        goal: str,
        source_types: list[str] | None = None,
        env_code: str | None = None,
        user_inputs: dict[str, Any] | None = None,
        visible_variables: list[dict[str, Any]] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        return await search_source_contracts(
            catalog_service,
            goal=goal,
            source_types=source_types,
            env_code=env_code,
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            limit=limit,
        )

    async def _compose_scene_draft_from_source(
        task_run_id: str,
        goal: str,
        source_contract: dict[str, Any],
    ) -> dict[str, Any]:
        scene = await compose_scene_draft_from_source(
            task_run_id=task_run_id,
            goal=goal,
            source_contract=source_contract,
            http_source_repository=http_source_repository,
            sql_source_repository=sql_source_repository,
        )
        return scene.model_dump(mode="json")

    async def _publish_scene_from_source(
        task_run_id: str,
        goal: str,
        source_contract: dict[str, Any],
    ) -> dict[str, Any]:
        return await publish_scene_from_source(
            task_service=task_service,
            scene_service=scene_service,
            http_source_repository=http_source_repository,
            sql_source_repository=sql_source_repository,
            task_run_id=task_run_id,
            goal=goal,
            source_contract=source_contract,
        )

    return [
        StructuredTool.from_function(
            coroutine=_search_source_contracts,
            name="search_source_contracts",
            description="搜索可用于生成造数场景的 HTTP/SQL Source 能力契约。",
        ),
        StructuredTool.from_function(
            coroutine=_compose_scene_draft_from_source,
            name="compose_scene_draft_from_source",
            description="基于单个 Source 能力契约生成单步骤造数场景草稿，不保存配置。",
        ),
        StructuredTool.from_function(
            coroutine=_publish_scene_from_source,
            name="publish_scene_from_source",
            description="基于 Source 生成、保存并发布新造数场景，同时记录任务步骤和审计事件。",
        ),
    ]


def _compose_http_scene(*, task_run_id: str, goal: str, source: HttpSourceResponse) -> SceneDefinition:
    step_id = _safe_step_id(source.sourceCode)
    output_mapping = source.outputMapping or _http_output_mapping_from_response(source.responseSchema or [])
    return SceneDefinition(
        sceneCode=_generated_scene_code(task_run_id, source.sourceCode),
        sceneName=f"自动场景-{source.sourceName}",
        sceneRemark=f"由 GDP Agent 根据用户目标“{goal}”基于 HTTP Source 自动生成。",
        tags=source.tags or [source.sourceName],
        capabilityType=source.capabilityType,
        businessDomain=source.businessDomain,
        sideEffects=source.sideEffects,
        agentDescription=source.agentDescription or f"基于接口 {source.sourceName} 自动生成的造数场景。",
        inputSchema=_http_input_schema(source),
        resultSchema=_result_schema_from_mapping(output_mapping, source.outputMeta),
        steps=[
            HttpStepDefinition(
                stepId=step_id,
                stepName=source.sourceName,
                type=StepType.HTTP,
                executionOrder=1,
                templateRef=StepTemplateRef(
                    type="HTTP_SOURCE",
                    sourceCode=source.sourceCode,
                    sourceNameAtSnapshot=source.sourceName,
                    sourceUpdatedAtSnapshot=source.updatedAt,
                ),
                sourceName=source.sourceName,
                sysCode=source.sysCode,
                method=source.method,
                path=source.path,
                timeoutConfig=source.timeoutConfig,
                requestMapping=source.requestMapping,
                bodySchema=source.bodySchema,
                responseSchema=source.responseSchema,
                responseHeadersSchema=source.responseHeadersSchema,
                responseCookiesSchema=source.responseCookiesSchema,
                responseHandling=source.responseHandling,
                errorMapping=source.errorMapping,
                businessErrorMapping=source.businessErrorMapping,
                outputMapping=output_mapping,
                outputMeta=source.outputMeta,
                retryPolicy=source.retryPolicy,
            )
        ],
        resultMapping={name: f"${{steps.{step_id}.outputs.{name}}}" for name in output_mapping},
        batchConfig=BatchConfig(),
    )


def _compose_sql_scene(*, task_run_id: str, goal: str, source: SqlSourceResponse) -> SceneDefinition:
    step_id = _safe_step_id(source.sourceCode)
    output_mapping = _sql_output_mapping(source)
    return SceneDefinition(
        sceneCode=_generated_scene_code(task_run_id, source.sourceCode),
        sceneName=f"自动场景-{source.sourceName}",
        sceneRemark=f"由 GDP Agent 根据用户目标“{goal}”基于 SQL Source 自动生成。",
        tags=source.tags or [source.sourceName],
        capabilityType=source.capabilityType,
        businessDomain=source.businessDomain,
        sideEffects=source.sideEffects,
        agentDescription=source.agentDescription or f"基于 SQL {source.sourceName} 自动生成的造数场景。",
        inputSchema=[_env_field(), *[_sql_parameter_to_input(parameter) for parameter in source.parameters]],
        resultSchema=_sql_result_schema(source),
        steps=[
            SqlStepDefinition(
                stepId=step_id,
                stepName=source.sourceName,
                type=StepType.SQL,
                executionOrder=1,
                templateRef=StepTemplateRef(
                    type="SQL_SOURCE",
                    sourceCode=source.sourceCode,
                    sourceNameAtSnapshot=source.sourceName,
                    sourceUpdatedAtSnapshot=source.updatedAt,
                ),
                sourceName=source.sourceName,
                sysCode=source.sysCode,
                datasourceCode=source.datasourceCode,
                operation=source.operation,
                sqlText=source.sqlText,
                normalizedSql=source.normalizedSql,
                tables=[item.model_dump(mode="json") for item in source.tables],
                resultFields=[item.model_dump(mode="json") for item in source.resultFields],
                conditionFields=[item.model_dump(mode="json") for item in source.conditionFields],
                parameters=[item.model_dump(mode="json") for item in source.parameters],
                safety=source.safety,
                paramMapping={parameter.name: f"${{input.{parameter.name}}}" for parameter in source.parameters},
                outputMapping=output_mapping,
            )
        ],
        resultMapping={name: f"${{steps.{step_id}.outputs.{name}}}" for name in output_mapping},
        batchConfig=BatchConfig(),
    )


def _env_field() -> InputFieldDefinition:
    return InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING, required=True, semanticType="ENV_CODE")


def _http_input_schema(source: HttpSourceResponse) -> list[InputFieldDefinition]:
    fields = [_env_field()]
    fields_by_name = {field.name: field for field in source.bodySchema or []}
    fields.extend(fields_by_name.values())
    for name in _input_names_from_mapping(source.requestMapping):
        if name == "env" or name in fields_by_name:
            continue
        field = InputFieldDefinition(name=name, label=name, type=InputFieldType.STRING, required=True)
        fields_by_name[name] = field
        fields.append(field)
    return fields


def _input_names_from_mapping(value: Any) -> list[str]:
    names: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            for name in _INPUT_REF_RE.findall(item):
                if name not in names:
                    names.append(name)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return names


def _sql_parameter_to_input(parameter: SqlSourceParameter) -> InputFieldDefinition:
    field_type = parameter.type if isinstance(parameter.type, InputFieldType) else InputFieldType.STRING
    return InputFieldDefinition(
        name=parameter.name,
        label=parameter.name,
        remark=parameter.description,
        type=field_type,
        required=parameter.required,
        defaultValue=parameter.defaultValue,
    )


def _result_schema_from_mapping(
    output_mapping: dict[str, str],
    output_meta: dict[str, dict[str, str | None]] | None,
) -> list[InputFieldDefinition]:
    fields: list[InputFieldDefinition] = []
    for name in output_mapping:
        meta = (output_meta or {}).get(name, {})
        fields.append(
            InputFieldDefinition(
                name=name,
                label=meta.get("label") or name,
                remark=meta.get("remark"),
                type=InputFieldType.STRING,
                required=False,
                semanticType=meta.get("semanticType"),
            )
        )
    return fields


def _http_output_mapping_from_response(fields: list[InputFieldDefinition]) -> dict[str, str]:
    return {field.name: f"${{RES_BODY({field.name})}}" for field in fields}


def _sql_output_mapping(source: SqlSourceResponse) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for field in source.resultFields:
        output_name = field.alias or field.fieldName
        mapping[output_name] = f"${{SQL_RESULT(row.{output_name})}}"
    return mapping


def _sql_result_schema(source: SqlSourceResponse) -> list[InputFieldDefinition]:
    fields: list[InputFieldDefinition] = []
    for field in source.resultFields:
        name = field.alias or field.fieldName
        fields.append(
            InputFieldDefinition(
                name=name,
                label=field.description or name,
                remark=field.description,
                type=InputFieldType.STRING,
                required=False,
            )
        )
    return fields


def _generated_scene_code(task_run_id: str, source_code: str) -> str:
    raw = f"agent_{source_code}_{task_run_id[-8:]}"
    return _safe_step_id(raw)[:128]


def _safe_step_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return normalized or "agent_step"
