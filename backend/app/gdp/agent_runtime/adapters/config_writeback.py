"""datagen 配置写回适配器。"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import CapabilityType, InputFieldDefinition, InputFieldType, StepType
from app.gdp.datagen.config.httpsource.models import HttpSourceResponse
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.factory import build_scene_service
from app.gdp.datagen.config.scene.models import (
    HttpStepDefinition,
    SceneDefinition,
    SqlStepDefinition,
    StepTemplateRef,
)
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.scene.validation import validate_scene_publish
from app.gdp.datagen.config.sqlsource.models import SqlSourceFieldMeta, SqlSourceParameter, SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService

from ..domain.config_writeback import ConfigWritebackResult, ConfigWritebackStatus
from ..models import InfraCandidate, Requirement, RequirementProposal, SourceCandidate, TaskRun
from ..support.errors import RuntimeDependencyError


class DatagenConfigWritebackAdapter:
    """通过 datagen service 合约创建并发布自动组合 Scene。"""

    def __init__(
        self,
        *,
        scene_service: SceneService | None = None,
        http_source_service: HttpSourceService | None = None,
        sql_source_service: SqlSourceService | None = None,
    ) -> None:
        self._scene_service = scene_service
        self._http_source_service = http_source_service
        self._sql_source_service = sql_source_service

    async def create_and_publish_scene_from_sources(
        self,
        *,
        task_run: TaskRun,
        scene_requirement: Requirement,
        source_requirement: Requirement,
        proposal: RequirementProposal,
        source_candidates: list[SourceCandidate],
        infra_candidates: list[InfraCandidate],
        inputs: dict[str, Any],
    ) -> ConfigWritebackResult:
        """基于已有 Source 候选创建并发布 Scene。"""
        precheck = _precheck(
            scene_requirement=scene_requirement,
            source_requirement=source_requirement,
            proposal=proposal,
            source_candidates=source_candidates,
            infra_candidates=infra_candidates,
        )
        if precheck is not None:
            return precheck

        try:
            scene_service, http_service, sql_service = self._get_services()
            scene = await self._build_scene_definition(
                task_run=task_run,
                scene_requirement=scene_requirement,
                source_requirement=source_requirement,
                proposal=proposal,
                source_candidates=source_candidates,
                http_service=http_service,
                sql_service=sql_service,
            )
            validation = validate_scene_publish(scene)
            if not validation.valid:
                return _failed(
                    "SceneDefinition 发布校验失败。",
                    scene_requirement=scene_requirement,
                    source_requirement=source_requirement,
                    proposal=proposal,
                    validation_issues=[f"{issue.field}: {issue.message}" for issue in validation.issues],
                )
            await scene_service.create_scene(scene, operator="agent_runtime")
            await scene_service.publish_scene(scene.sceneCode, operator="agent_runtime")
        except HTTPException as exc:
            return _failed(
                _http_exception_message(exc),
                scene_requirement=scene_requirement,
                source_requirement=source_requirement,
                proposal=proposal,
            )
        except RuntimeDependencyError:
            raise
        except Exception as exc:
            return _failed(
                f"自动发布 Scene 失败：{exc}",
                scene_requirement=scene_requirement,
                source_requirement=source_requirement,
                proposal=proposal,
            )

        return ConfigWritebackResult(
            status=ConfigWritebackStatus.SUCCESS,
            target_kind="SCENE",
            target_code=scene.sceneCode,
            message=f"已基于 {len(source_candidates)} 个 Source 自动创建并发布 Scene：{scene.sceneCode}",
            parent_requirement_id=scene_requirement.requirement_id,
            source_requirement_id=source_requirement.requirement_id,
            proposal_id=proposal.proposal_id,
        )

    def _get_services(self) -> tuple[SceneService, HttpSourceService, SqlSourceService]:
        if self._scene_service and self._http_source_service and self._sql_source_service:
            return self._scene_service, self._http_source_service, self._sql_source_service

        from deerflow.persistence.engine import get_session_factory

        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeDependencyError(503, "Config writeback persistence not available")
        base_repository = BaseConfigRepository(session_factory)
        self._scene_service = self._scene_service or build_scene_service(session_factory)
        self._http_source_service = self._http_source_service or HttpSourceService(
            HttpSourceRepository(session_factory),
            base_repository,
        )
        self._sql_source_service = self._sql_source_service or SqlSourceService(
            SqlSourceRepository(session_factory),
            base_repository,
        )
        return self._scene_service, self._http_source_service, self._sql_source_service

    async def _build_scene_definition(
        self,
        *,
        task_run: TaskRun,
        scene_requirement: Requirement,
        source_requirement: Requirement,
        proposal: RequirementProposal,
        source_candidates: list[SourceCandidate],
        http_service: HttpSourceService,
        sql_service: SqlSourceService,
    ) -> SceneDefinition:
        steps: list[HttpStepDefinition | SqlStepDefinition] = []
        input_schema = []
        result_schema = None
        result_mapping: dict[str, str] = {}
        all_tags = ["agent-runtime", "auto-writeback"]
        side_effects = []
        now = datetime.now(UTC)

        for index, candidate in enumerate(source_candidates[:5], start=1):
            step_id = _step_id(candidate, index)
            if candidate.source_type.upper() == "SQL":
                source = await sql_service.get_sql_source(candidate.source_code)
                step = _sql_step(step_id, index, source, candidate, now)
                input_schema = _merge_input_schema(input_schema, [_sql_parameter_to_input(item) for item in source.parameters])
                result_schema = result_schema or []
                result_schema.extend(_sql_result_field_to_input(item) for item in source.resultFields)
            else:
                source = await http_service.get_http_source(candidate.source_code)
                step = _http_step(step_id, index, source, candidate, now)
                input_schema = _merge_input_schema(input_schema, source.bodySchema or [])
                result_schema = source.responseSchema if result_schema is None else result_schema
            steps.append(step)
            all_tags.extend(_safe_tags(getattr(source, "tags", [])))
            side_effects.extend(getattr(source, "sideEffects", []))
            for output_name in getattr(step, "outputMapping", {}) or {}:
                result_mapping.setdefault(output_name, f"${{steps.{step_id}.outputs.{output_name}}}")

        return SceneDefinition(
            sceneCode=_scene_code(task_run, source_candidates),
            sceneName=f"自动组合场景：{scene_requirement.goal[:80]}",
            sceneRemark=(
                f"由 Agent Runtime 基于 SOURCE 缺口 {source_requirement.requirement_id} "
                f"和候选集 {proposal.proposal_id} 自动生成。"
            ),
            tags=list(dict.fromkeys(all_tags)),
            capabilityType=CapabilityType.COMPOSITE if side_effects else CapabilityType.QUERY,
            sideEffects=side_effects,
            agentDescription=f"自动组合已有 Source 以完成目标：{scene_requirement.goal}",
            inputSchema=input_schema,
            steps=steps,
            resultSchema=result_schema if result_schema else None,
            resultMapping=result_mapping,
        )


def _precheck(
    *,
    scene_requirement: Requirement,
    source_requirement: Requirement,
    proposal: RequirementProposal,
    source_candidates: list[SourceCandidate],
    infra_candidates: list[InfraCandidate],
) -> ConfigWritebackResult | None:
    if not source_candidates:
        return _skipped(
            "没有可用于生成 Scene 的 Source 候选。",
            scene_requirement=scene_requirement,
            source_requirement=source_requirement,
            proposal=proposal,
        )
    if len(infra_candidates) < len(source_candidates):
        return _skipped(
            "基础配置诊断不足，无法确认所有 Source 依赖都已满足。",
            scene_requirement=scene_requirement,
            source_requirement=source_requirement,
            proposal=proposal,
            validation_issues=["infra_diagnostics_missing"],
        )
    missing = sorted({field for item in infra_candidates for field in item.missing_fields})
    if missing or any(not item.ready for item in infra_candidates):
        return _skipped(
            "基础配置仍存在阻塞项：" + "，".join(missing or ["infra_not_ready"]) + "。",
            scene_requirement=scene_requirement,
            source_requirement=source_requirement,
            proposal=proposal,
            validation_issues=missing,
        )
    return None


def _http_step(
    step_id: str,
    index: int,
    source: HttpSourceResponse,
    candidate: SourceCandidate,
    snapshot_at: datetime,
) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId=step_id,
        stepName=source.sourceName,
        type=StepType.HTTP,
        executionOrder=index,
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
        retryPolicy=source.retryPolicy,
        outputMapping=source.outputMapping,
        outputMeta=source.outputMeta,
        templateRef=_template_ref("HTTP_SOURCE", source.sourceCode, source.sourceName, source.updatedAt, candidate, snapshot_at),
    )


def _sql_step(
    step_id: str,
    index: int,
    source: SqlSourceResponse,
    candidate: SourceCandidate,
    snapshot_at: datetime,
) -> SqlStepDefinition:
    return SqlStepDefinition(
        stepId=step_id,
        stepName=source.sourceName,
        type=StepType.SQL,
        executionOrder=index,
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
        paramMapping={item.name: f"${{inputs.{item.name}}}" for item in source.parameters if item.required},
        templateRef=_template_ref("SQL_SOURCE", source.sourceCode, source.sourceName, source.updatedAt, candidate, snapshot_at),
    )


def _template_ref(
    ref_type: str,
    source_code: str,
    source_name: str,
    source_updated_at: datetime,
    candidate: SourceCandidate,
    snapshot_at: datetime,
) -> StepTemplateRef:
    return StepTemplateRef(
        type=ref_type,  # type: ignore[arg-type]
        sourceCode=source_code,
        sourceNameAtSnapshot=source_name,
        sourceUpdatedAtSnapshot=source_updated_at,
        sourceHashSnapshot=candidate.contract_hash,
        snapshotAt=snapshot_at,
    )


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


def _sql_result_field_to_input(field: SqlSourceFieldMeta) -> InputFieldDefinition:
    name = field.alias or field.fieldName
    return InputFieldDefinition(
        name=name,
        label=field.description or name,
        remark=field.description,
        type=InputFieldType.STRING,
        required=False,
    )


def _merge_input_schema(existing: list[Any], incoming: list[Any]) -> list[Any]:
    seen = {item.name for item in existing}
    merged = list(existing)
    for item in incoming:
        if item.name in seen:
            continue
        seen.add(item.name)
        merged.append(item)
    return merged


def _safe_tags(tags: list[str]) -> list[str]:
    return [item for item in tags if item and len(item) <= 64]


def _step_id(candidate: SourceCandidate, index: int) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]+", "_", candidate.source_code).strip("_")
    return f"step_{index}_{raw or 'source'}"[:128]


def _scene_code(task_run: TaskRun, source_candidates: list[SourceCandidate]) -> str:
    raw = "|".join([task_run.task_run_id, *[item.source_code for item in source_candidates[:5]]])
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"agent_scene_{digest}"


def _skipped(
    reason: str,
    *,
    scene_requirement: Requirement,
    source_requirement: Requirement,
    proposal: RequirementProposal,
    validation_issues: list[str] | None = None,
) -> ConfigWritebackResult:
    return ConfigWritebackResult(
        status=ConfigWritebackStatus.SKIPPED,
        target_kind="SCENE",
        message=reason,
        reason=reason,
        validation_issues=validation_issues or [],
        parent_requirement_id=scene_requirement.requirement_id,
        source_requirement_id=source_requirement.requirement_id,
        proposal_id=proposal.proposal_id,
    )


def _failed(
    reason: str,
    *,
    scene_requirement: Requirement,
    source_requirement: Requirement,
    proposal: RequirementProposal,
    validation_issues: list[str] | None = None,
) -> ConfigWritebackResult:
    return ConfigWritebackResult(
        status=ConfigWritebackStatus.FAILED,
        target_kind="SCENE",
        message="自动发布 Scene 失败。",
        reason=reason,
        validation_issues=validation_issues or [],
        parent_requirement_id=scene_requirement.requirement_id,
        source_requirement_id=source_requirement.requirement_id,
        proposal_id=proposal.proposal_id,
    )


def _http_exception_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        issues = detail.get("issues")
        if isinstance(issues, list):
            return "；".join(str(item.get("message") if isinstance(item, dict) else item) for item in issues)
        return str(detail)
    return str(detail or exc)
