"""Agent 能力目录服务。"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from app.gdp.datagen.agent_catalog.models import (
    AgentInfraResolveRequest,
    AgentInfraResolveResponse,
    AgentSceneCandidate,
    AgentSceneContract,
    AgentSceneSearchRequest,
    AgentSceneSearchResponse,
    AgentSourceCandidate,
    AgentSourceContract,
    AgentSourceSearchRequest,
    AgentSourceSearchResponse,
)
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, InputFieldDefinition, InputFieldType, SceneStatus
from app.gdp.datagen.config.httpsource.models import HttpSourceResponse
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.models import SceneVersion
from app.gdp.datagen.config.scene.repository import SceneNotFoundError, SceneRepository
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter, SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository

_ALIASES: dict[str, list[str]] = {
    "订单": ["交易", "下单", "order", "trade"],
    "交易": ["订单", "下单", "order", "trade"],
    "支付": ["付款", "pay", "payment", "paid"],
    "库存": ["商品", "sku", "stock", "inventory"],
    "用户": ["会员", "客户", "user", "customer", "buyer"],
    "创建": ["新增", "生成", "造", "create"],
    "查询": ["获取", "检查", "query", "select", "get"],
    "更新": ["修改", "变更", "update"],
}


class AgentCatalogService:
    """面向 Agent 的只读能力目录服务。"""

    def __init__(
        self,
        scene_repository: SceneRepository,
        http_source_repository: HttpSourceRepository | None = None,
        sql_source_repository: SqlSourceRepository | None = None,
        base_repository: BaseConfigRepository | None = None,
    ) -> None:
        self._scene_repo = scene_repository
        self._http_repo = http_source_repository
        self._sql_repo = sql_source_repository
        self._base_repo = base_repository

    async def search_scene_contracts(self, request: AgentSceneSearchRequest) -> AgentSceneSearchResponse:
        terms = _expand_terms(_tokenize(request.goal))
        summaries = await self._scene_repo.list_scenes(status=SceneStatus.PUBLISHED, limit=200, offset=0)
        candidates: list[AgentSceneCandidate] = []
        provided_keys = _provided_keys(request)
        inferred_capability = _infer_capability(request.goal)

        for summary in summaries:
            try:
                version = await self._scene_repo.get_published_scene(summary.sceneCode)
            except SceneNotFoundError:
                continue
            contract = self._to_scene_contract(version)
            missing_inputs = _missing_required_inputs(contract.inputSchema, provided_keys)
            score, reasons = _score_contract(contract, terms, inferred_capability, missing_inputs)
            if score <= 0:
                continue
            candidates.append(
                AgentSceneCandidate(
                    contract=contract,
                    score=score,
                    reasons=reasons,
                    missingInputs=missing_inputs,
                    requiresConfirmation=contract.hasSideEffects,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return AgentSceneSearchResponse(candidates=candidates[: request.limit], queryTerms=terms)

    async def get_scene_contract(self, scene_code: str) -> AgentSceneContract:
        try:
            version = await self._scene_repo.get_published_scene(scene_code)
        except SceneNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return self._to_scene_contract(version)

    async def search_source_contracts(self, request: AgentSourceSearchRequest) -> AgentSourceSearchResponse:
        terms = _expand_terms(_tokenize(request.goal))
        provided_keys = _provided_keys(request)
        inferred_capability = _infer_capability(request.goal)
        requested_types = {item.upper() for item in request.sourceTypes}
        candidates: list[AgentSourceCandidate] = []

        if "HTTP" in requested_types and self._http_repo is not None:
            http_sources = await self._http_repo.list_http_sources(status=ConfigStatus.ENABLED)
            for source in http_sources:
                contract = _http_to_source_contract(source)
                missing_inputs = _missing_required_inputs(contract.inputSchema, provided_keys)
                score, reasons = _score_source_contract(contract, terms, inferred_capability, missing_inputs)
                if score <= 0:
                    continue
                candidates.append(
                    AgentSourceCandidate(
                        contract=contract,
                        score=score,
                        reasons=reasons,
                        missingInputs=missing_inputs,
                        requiresConfirmation=contract.hasSideEffects,
                    )
                )

        if "SQL" in requested_types and self._sql_repo is not None:
            sql_sources = await self._sql_repo.list_sql_sources(status=ConfigStatus.ENABLED)
            for source in sql_sources:
                contract = _sql_to_source_contract(source)
                missing_inputs = _missing_required_inputs(contract.inputSchema, provided_keys)
                score, reasons = _score_source_contract(contract, terms, inferred_capability, missing_inputs)
                if score <= 0:
                    continue
                candidates.append(
                    AgentSourceCandidate(
                        contract=contract,
                        score=score,
                        reasons=reasons,
                        missingInputs=missing_inputs,
                        requiresConfirmation=contract.hasSideEffects,
                    )
                )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return AgentSourceSearchResponse(candidates=candidates[: request.limit], queryTerms=terms)

    async def resolve_infra_basis(self, request: AgentInfraResolveRequest) -> AgentInfraResolveResponse:
        if self._base_repo is None:
            raise HTTPException(status_code=503, detail="base config repository not available")

        systems = await self._base_repo.list_systems()
        environments = await self._base_repo.list_environments()
        matched_systems = _score_systems(systems, query=request.query, sys_code=request.sysCode)
        matched_envs = [item for item in environments if item.envCode == request.envCode]
        resolved_sys_code = request.sysCode or (matched_systems[0]["sysCode"] if matched_systems else None)
        endpoints = await self._base_repo.list_service_endpoints(env_code=request.envCode, sys_code=resolved_sys_code)
        datasources = await self._base_repo.list_datasources(env_code=request.envCode, sys_code=resolved_sys_code)
        datasource_matches = [
            item
            for item in datasources
            if request.datasourceCode is None or item.datasourceCode == request.datasourceCode
        ]

        missing_fields: list[str] = []
        if not matched_systems:
            missing_fields.append("system")
        if not matched_envs:
            missing_fields.append("environment")
        if request.resourceType.upper() == "SQL":
            if not datasource_matches:
                missing_fields.append("datasource")
        elif not endpoints:
            missing_fields.append("serviceEndpoint")

        return AgentInfraResolveResponse(
            matchedSystems=matched_systems,
            matchedEnvironments=[item.model_dump(mode="json") for item in matched_envs],
            matchedServiceEndpoints=[item.model_dump(mode="json") for item in endpoints],
            matchedDatasources=[item.model_dump(mode="json") for item in datasource_matches],
            confidence=_infra_confidence(matched_systems, matched_envs, missing_fields),
            missingFields=missing_fields,
            ready=not missing_fields,
        )

    @staticmethod
    def _to_scene_contract(version: SceneVersion) -> AgentSceneContract:
        scene = version.definition
        return AgentSceneContract(
            sceneCode=scene.sceneCode,
            sceneName=scene.sceneName,
            sceneRemark=scene.sceneRemark,
            tags=scene.tags,
            capabilityType=scene.capabilityType,
            businessDomain=scene.businessDomain,
            preconditions=scene.preconditions,
            sideEffects=scene.sideEffects,
            agentDescription=scene.agentDescription,
            inputSchema=scene.inputSchema,
            resultSchema=scene.resultSchema,
            resultMapping=scene.resultMapping,
            versionNo=version.versionNo,
            executable=True,
            hasSideEffects=bool(scene.sideEffects),
        )


def _tokenize(text: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,8}", text.lower())
    return [term for term in terms if term.strip()]


def _expand_terms(terms: list[str]) -> list[str]:
    expanded: list[str] = []
    for term in terms:
        if term not in expanded:
            expanded.append(term)
        for key, aliases in _ALIASES.items():
            if term == key or term in aliases:
                for alias in [key, *aliases]:
                    normalized = alias.lower()
                    if normalized not in expanded:
                        expanded.append(normalized)
    return expanded


def _provided_keys(request: AgentSceneSearchRequest) -> set[str]:
    keys = {str(key).lower() for key in request.userInputs}
    for variable in request.visibleVariables:
        for field in ("name", "semanticType", "label"):
            value = variable.get(field)
            if value:
                keys.add(str(value).lower())
    return keys


def _missing_required_inputs(fields: list[InputFieldDefinition], provided_keys: set[str]) -> list[str]:
    missing: list[str] = []
    for field in fields:
        if field.name == "env":
            continue
        if not field.required:
            continue
        candidates = {field.name.lower()}
        if field.semanticType:
            candidates.add(field.semanticType.lower())
        if field.label:
            candidates.add(field.label.lower())
        candidates.update(alias.lower() for alias in field.aliases)
        if candidates.isdisjoint(provided_keys):
            missing.append(field.name)
    return missing


def _infer_capability(goal: str) -> CapabilityType | None:
    lower = goal.lower()
    if any(word in lower for word in ("创建", "新增", "生成", "造", "下单", "create")):
        return CapabilityType.CREATE
    if any(word in lower for word in ("更新", "修改", "变更", "支付", "update", "pay")):
        return CapabilityType.UPDATE
    if any(word in lower for word in ("查询", "获取", "检查", "query", "select", "get")):
        return CapabilityType.QUERY
    return None


def _score_contract(
    contract: AgentSceneContract,
    terms: list[str],
    inferred_capability: CapabilityType | None,
    missing_inputs: list[str],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text_blob = _contract_text(contract)
    matched_terms = [term for term in terms if term and term in text_blob]
    if matched_terms:
        score += min(0.35, 0.08 * len(set(matched_terms)))
        reasons.append(f"文本和标签命中：{', '.join(sorted(set(matched_terms))[:6])}")
    if inferred_capability and contract.capabilityType == inferred_capability:
        score += 0.2
        reasons.append(f"能力类型匹配：{contract.capabilityType.value}")
    result_matches = _result_semantic_matches(contract, terms)
    if result_matches:
        score += min(0.2, 0.08 * len(result_matches))
        reasons.append(f"结果语义匹配：{', '.join(result_matches[:4])}")
    if not missing_inputs:
        score += 0.15
        reasons.append("必填入参均可由用户输入或变量栈绑定")
    else:
        score -= min(0.2, 0.05 * len(missing_inputs))
        reasons.append(f"仍缺少必填入参：{', '.join(missing_inputs)}")
    if contract.hasSideEffects:
        score += 0.05
        reasons.append("场景存在副作用，执行前需要用户确认")
    if not contract.executable:
        score = 0
        reasons.append("场景不可执行")
    return max(0.0, min(1.0, round(score, 4))), reasons


def _contract_text(contract: AgentSceneContract) -> str:
    values: list[str] = [
        contract.sceneCode,
        contract.sceneName,
        contract.sceneRemark or "",
        contract.businessDomain or "",
        contract.agentDescription or "",
        contract.capabilityType.value,
        *contract.tags,
    ]
    for field in [*contract.inputSchema, *(contract.resultSchema or [])]:
        values.extend(_field_texts(field))
    return " ".join(value.lower() for value in values if value)


def _field_texts(field: InputFieldDefinition) -> list[str]:
    values = [
        field.name,
        field.label or "",
        field.remark or "",
        field.semanticType or "",
        *field.aliases,
    ]
    for child in field.children or []:
        values.extend(_field_texts(child))
    return values


def _result_semantic_matches(contract: AgentSceneContract, terms: list[str]) -> list[str]:
    matches: list[str] = []
    for field in contract.resultSchema or []:
        text = " ".join(_field_texts(field)).lower()
        if any(term in text for term in terms):
            matches.append(field.semanticType or field.name)
    return matches


def _http_to_source_contract(source: HttpSourceResponse) -> AgentSourceContract:
    output_mapping = source.outputMapping or _output_mapping_from_fields(source.responseSchema or [])
    return AgentSourceContract(
        sourceType="HTTP",
        sourceCode=source.sourceCode,
        sourceName=source.sourceName,
        tags=source.tags,
        capabilityType=source.capabilityType,
        businessDomain=source.businessDomain,
        sideEffects=source.sideEffects,
        agentDescription=source.agentDescription,
        sysCode=source.sysCode,
        method=source.method.value if hasattr(source.method, "value") else str(source.method),
        path=source.path,
        inputSchema=source.bodySchema or [],
        resultSchema=_source_result_schema(output_mapping, source.outputMeta, source.responseSchema or []),
        outputMapping=output_mapping,
        executable=True,
        hasSideEffects=bool(source.sideEffects),
    )


def _sql_to_source_contract(source: SqlSourceResponse) -> AgentSourceContract:
    output_mapping = _sql_output_mapping(source)
    return AgentSourceContract(
        sourceType="SQL",
        sourceCode=source.sourceCode,
        sourceName=source.sourceName,
        tags=source.tags,
        capabilityType=source.capabilityType,
        businessDomain=source.businessDomain,
        sideEffects=source.sideEffects,
        agentDescription=source.agentDescription,
        sysCode=source.sysCode,
        datasourceCode=source.datasourceCode,
        operation=source.operation.value if hasattr(source.operation, "value") else str(source.operation),
        inputSchema=[_sql_parameter_to_input(parameter) for parameter in source.parameters],
        resultSchema=_sql_result_schema(source),
        outputMapping=output_mapping,
        executable=True,
        hasSideEffects=bool(source.sideEffects),
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
    operation = source.operation.value if hasattr(source.operation, "value") else str(source.operation)
    if not fields and operation == "SELECT":
        fields.append(InputFieldDefinition(name="rows", label="查询结果", type=InputFieldType.ARRAY, required=False))
    return fields


def _source_result_schema(
    output_mapping: dict[str, str],
    output_meta: dict[str, dict[str, str | None]] | None,
    fallback_fields: list[InputFieldDefinition],
) -> list[InputFieldDefinition]:
    if output_mapping:
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
    return fallback_fields


def _output_mapping_from_fields(fields: list[InputFieldDefinition]) -> dict[str, str]:
    return {field.name: f"${{RES_BODY({field.name})}}" for field in fields}


def _sql_output_mapping(source: SqlSourceResponse) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for field in source.resultFields:
        output_name = field.alias or field.fieldName
        mapping[output_name] = f"${{SQL_RESULT(row.{output_name})}}"
    return mapping


def _score_source_contract(
    contract: AgentSourceContract,
    terms: list[str],
    inferred_capability: CapabilityType | None,
    missing_inputs: list[str],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text_blob = _source_contract_text(contract)
    matched_terms = [term for term in terms if term and term in text_blob]
    if matched_terms:
        score += min(0.35, 0.08 * len(set(matched_terms)))
        reasons.append(f"文本和标签命中：{', '.join(sorted(set(matched_terms))[:6])}")
    if inferred_capability and contract.capabilityType == inferred_capability:
        score += 0.2
        reasons.append(f"能力类型匹配：{contract.capabilityType.value}")
    result_matches = _source_result_matches(contract, terms)
    if result_matches:
        score += min(0.2, 0.08 * len(result_matches))
        reasons.append(f"结果语义匹配：{', '.join(result_matches[:4])}")
    if not missing_inputs:
        score += 0.15
        reasons.append("必填入参均可由用户输入或变量栈绑定")
    else:
        score -= min(0.2, 0.05 * len(missing_inputs))
        reasons.append(f"仍缺少必填入参：{', '.join(missing_inputs)}")
    if contract.hasSideEffects:
        score += 0.05
        reasons.append("Source 存在副作用，生成场景执行前需要用户确认")
    if not contract.executable:
        score = 0
        reasons.append("Source 不可用于生成场景")
    return max(0.0, min(1.0, round(score, 4))), reasons


def _source_contract_text(contract: AgentSourceContract) -> str:
    values: list[str] = [
        contract.sourceType,
        contract.sourceCode,
        contract.sourceName,
        contract.businessDomain or "",
        contract.agentDescription or "",
        contract.capabilityType.value,
        contract.sysCode,
        contract.method or "",
        contract.path or "",
        contract.datasourceCode or "",
        contract.operation or "",
        *contract.tags,
    ]
    for field in [*contract.inputSchema, *contract.resultSchema]:
        values.extend(_field_texts(field))
    return " ".join(value.lower() for value in values if value)


def _source_result_matches(contract: AgentSourceContract, terms: list[str]) -> list[str]:
    matches: list[str] = []
    for field in contract.resultSchema:
        text = " ".join(_field_texts(field)).lower()
        if any(term in text for term in terms):
            matches.append(field.semanticType or field.name)
    return matches


def _score_systems(systems, *, query: str, sys_code: str | None) -> list[dict[str, Any]]:
    terms = _expand_terms(_tokenize(query))
    candidates: list[dict[str, Any]] = []
    for system in systems:
        score = 0.0
        reasons: list[str] = []
        if sys_code and system.sysCode == sys_code:
            score += 0.7
            reasons.append("系统编码精确匹配")
        text = " ".join([system.sysCode, system.sysName, system.remark or ""]).lower()
        matched_terms = [term for term in terms if term in text]
        if matched_terms:
            score += min(0.3, 0.1 * len(set(matched_terms)))
            reasons.append(f"系统文本命中：{', '.join(sorted(set(matched_terms))[:4])}")
        if score <= 0:
            continue
        candidates.append(
            {
                **system.model_dump(mode="json"),
                "score": round(min(score, 1.0), 4),
                "reasons": reasons,
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _infra_confidence(
    matched_systems: list[dict[str, Any]],
    matched_envs: list[Any],
    missing_fields: list[str],
) -> float:
    if missing_fields:
        return 0.0 if not matched_systems else 0.45
    base = 0.6 if matched_envs else 0.4
    if matched_systems:
        base += min(0.35, matched_systems[0]["score"] * 0.35)
    return round(min(base, 0.95), 4)
