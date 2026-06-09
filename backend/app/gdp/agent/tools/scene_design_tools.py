"""GDP Task Agent 场景设计工具。"""

from __future__ import annotations

import re
from typing import Any

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
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter, SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService


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


async def publish_scene_from_source(
    *,
    task_service: DatagenTaskService,
    scene_service: SceneService,
    http_source_repository: HttpSourceRepository,
    sql_source_repository: SqlSourceRepository,
    task_run_id: str,
    goal: str,
    source_contract: dict[str, Any],
) -> dict[str, Any]:
    """基于 Source 生成、保存并发布新场景。"""

    scene = await compose_scene_draft_from_source(
        task_run_id=task_run_id,
        goal=goal,
        source_contract=source_contract,
        http_source_repository=http_source_repository,
        sql_source_repository=sql_source_repository,
    )
    await task_service.record_event(
        task_run_id,
        event_type="SCENE_DRAFT_COMPOSED",
        phase=DatagenTaskPhase.SCENE_DESIGN,
        message=f"已基于 Source {source_contract['sourceCode']} 生成场景草稿 {scene.sceneCode}。",
        payload={"scene": scene.model_dump(mode="json"), "source": source_contract},
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
    }


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
        inputSchema=[_env_field(), *(source.bodySchema or [])],
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
