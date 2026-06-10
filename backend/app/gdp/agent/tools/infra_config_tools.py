"""GDP Task Agent 基础配置工具。"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import StructuredTool

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    EnvironmentConfig,
    ServiceEndpointConfig,
    SysConfig,
)
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import ConfigStatus


async def resolve_infra_basis(
    base_repository: BaseConfigRepository,
    *,
    query: str,
    env_code: str = "DEV",
    sys_code: str | None = None,
    datasource_code: str | None = None,
    resource_type: str = "HTTP",
) -> dict[str, Any]:
    """解析基础配置候选、置信度和缺口。"""

    systems = await base_repository.list_systems()
    environments = await base_repository.list_environments()
    endpoints = await base_repository.list_service_endpoints(env_code=env_code, sys_code=sys_code)
    datasources = await base_repository.list_datasources(env_code=env_code, sys_code=sys_code)

    matched_systems = _score_systems(_enabled_items(systems), query=query, sys_code=sys_code)
    matched_envs = [item for item in environments if item.envCode == env_code and _is_enabled(item)]
    matched_sys_codes = {str(item.get("sysCode")) for item in matched_systems if item.get("sysCode")}
    enabled_endpoints = [
        item
        for item in endpoints
        if _is_enabled(item) and (not matched_sys_codes or item.sysCode in matched_sys_codes)
    ]
    enabled_datasources = [
        item
        for item in datasources
        if _is_enabled(item) and (not matched_sys_codes or item.sysCode in matched_sys_codes)
    ]
    missing_fields: list[str] = []
    if not matched_systems:
        missing_fields.append("system")
    if not matched_envs:
        missing_fields.append("environment")
    if resource_type.upper() == "HTTP" and not enabled_endpoints:
        missing_fields.append("serviceEndpoint")
    if resource_type.upper() == "SQL":
        datasource_matches = [
            item
            for item in enabled_datasources
            if datasource_code is None or item.datasourceCode == datasource_code
        ]
        if not datasource_matches:
            missing_fields.append("datasource")
    else:
        datasource_matches = []

    confidence = _confidence(matched_systems, matched_envs, missing_fields)
    return {
        "matchedSystems": [item for item in matched_systems],
        "matchedEnvironments": [item.model_dump(mode="json") for item in matched_envs],
        "matchedServiceEndpoints": [item.model_dump(mode="json") for item in enabled_endpoints],
        "matchedDatasources": [item.model_dump(mode="json") for item in datasource_matches],
        "confidence": confidence,
        "missingFields": missing_fields,
        "ready": not missing_fields,
    }


async def upsert_system_from_agent(
    base_repository: BaseConfigRepository,
    *,
    config: SysConfig,
    operator: str | None = "gdp_agent",
) -> dict[str, Any]:
    """Agent 新增或更新系统配置。"""

    saved = await base_repository.upsert_system(config, operator=operator)
    return {"success": True, "system": saved.model_dump(mode="json")}


async def upsert_environment_from_agent(
    base_repository: BaseConfigRepository,
    *,
    config: EnvironmentConfig,
    operator: str | None = "gdp_agent",
) -> dict[str, Any]:
    """Agent 新增或更新环境配置。"""

    saved = await base_repository.upsert_environment(config, operator=operator)
    return {"success": True, "environment": saved.model_dump(mode="json")}


async def upsert_service_endpoint_from_agent(
    base_repository: BaseConfigRepository,
    *,
    config: ServiceEndpointConfig,
    operator: str | None = "gdp_agent",
) -> dict[str, Any]:
    """Agent 新增或更新服务端点配置。"""

    existing = await base_repository.list_service_endpoints(env_code=config.envCode, sys_code=config.sysCode)
    if existing:
        saved = await base_repository.update_service_endpoint(existing[0].id, config, operator=operator)
    else:
        saved = await base_repository.create_service_endpoint(config, operator=operator)
    return {"success": True, "serviceEndpoint": saved.model_dump(mode="json")}


async def upsert_datasource_from_agent(
    base_repository: BaseConfigRepository,
    *,
    config: DatasourceConfig,
    operator: str | None = "gdp_agent",
) -> dict[str, Any]:
    """Agent 新增或更新数据源配置。"""

    existing = await base_repository.list_datasources(env_code=config.envCode, sys_code=config.sysCode)
    matched = [item for item in existing if item.datasourceCode == config.datasourceCode]
    if matched:
        saved = await base_repository.update_datasource(matched[0].id, config, operator=operator)
    else:
        saved = await base_repository.create_datasource(config, operator=operator)
    return {"success": True, "datasource": saved.model_dump(mode="json")}


def build_infra_config_tools(base_repository: BaseConfigRepository) -> list[StructuredTool]:
    """构造基础配置阶段 LangChain 工具。"""

    async def _resolve_infra_basis(
        query: str,
        env_code: str = "DEV",
        sys_code: str | None = None,
        datasource_code: str | None = None,
        resource_type: str = "HTTP",
    ) -> dict[str, Any]:
        return await resolve_infra_basis(
            base_repository,
            query=query,
            env_code=env_code,
            sys_code=sys_code,
            datasource_code=datasource_code,
            resource_type=resource_type,
        )

    async def _upsert_system_from_agent(config: SysConfig) -> dict[str, Any]:
        return await upsert_system_from_agent(base_repository, config=config)

    async def _upsert_environment_from_agent(config: EnvironmentConfig) -> dict[str, Any]:
        return await upsert_environment_from_agent(base_repository, config=config)

    async def _upsert_service_endpoint_from_agent(config: ServiceEndpointConfig) -> dict[str, Any]:
        return await upsert_service_endpoint_from_agent(base_repository, config=config)

    async def _upsert_datasource_from_agent(config: DatasourceConfig) -> dict[str, Any]:
        return await upsert_datasource_from_agent(base_repository, config=config)

    return [
        StructuredTool.from_function(
            coroutine=_resolve_infra_basis,
            name="resolve_infra_basis",
            description="解析系统、环境、服务端点和数据源候选，返回置信度和缺口。",
        ),
        StructuredTool.from_function(
            coroutine=_upsert_system_from_agent,
            name="upsert_system_from_agent",
            description="新增或更新系统基础配置。",
        ),
        StructuredTool.from_function(
            coroutine=_upsert_environment_from_agent,
            name="upsert_environment_from_agent",
            description="新增或更新环境基础配置。",
        ),
        StructuredTool.from_function(
            coroutine=_upsert_service_endpoint_from_agent,
            name="upsert_service_endpoint_from_agent",
            description="新增或更新系统在目标环境下的 HTTP 服务端点。",
        ),
        StructuredTool.from_function(
            coroutine=_upsert_datasource_from_agent,
            name="upsert_datasource_from_agent",
            description="新增或更新系统在目标环境下的数据源。",
        ),
    ]


def _score_systems(systems, *, query: str, sys_code: str | None) -> list[dict[str, Any]]:
    terms = _terms(query)
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


def _enabled_items(items):
    """仅保留启用状态配置，作为 Agent 可直接复用的基础配置。"""

    return [item for item in items if _is_enabled(item)]


def _is_enabled(item: Any) -> bool:
    """判断基础配置是否处于启用状态。"""

    return getattr(item, "status", None) == ConfigStatus.ENABLED


def _terms(text: str) -> list[str]:
    return [item for item in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,8}", text.lower()) if item.strip()]


def _confidence(matched_systems: list[dict[str, Any]], matched_envs: list[Any], missing_fields: list[str]) -> float:
    if missing_fields:
        return 0.0 if not matched_systems else 0.45
    base = 0.6 if matched_envs else 0.4
    if matched_systems:
        base += min(0.35, matched_systems[0]["score"] * 0.35)
    return round(min(base, 0.95), 4)
