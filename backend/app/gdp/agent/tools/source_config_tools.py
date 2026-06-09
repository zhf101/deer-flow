"""GDP Task Agent HTTP/SQL Source 配置工具。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from langchain_core.tools import StructuredTool

from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig, HttpSourceTestRequest
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig, SqlSourceParseRequest
from app.gdp.datagen.config.sqlsource.parser import parse_sql_source
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.runtime.sql.models import SqlSourceTestRequest
from app.gdp.datagen.runtime.sql.service import SqlExecutionService


async def resolve_http_source_basis(
    base_repository: BaseConfigRepository,
    *,
    sys_code: str,
    env_code: str,
) -> dict[str, Any]:
    """解析 HTTP Source 所需系统和服务端点是否齐备。"""

    result: dict[str, Any] = {
        "sysCode": sys_code,
        "envCode": env_code,
        "system": None,
        "serviceEndpoint": None,
        "missingFields": [],
        "ready": False,
    }
    try:
        system = await base_repository.get_system(sys_code)
        result["system"] = system.model_dump(mode="json")
    except BaseConfigNotFoundError:
        result["missingFields"].append("system")
    try:
        endpoint = await base_repository.get_enabled_service_endpoint(env_code=env_code, sys_code=sys_code)
        result["serviceEndpoint"] = endpoint.model_dump(mode="json")
    except BaseConfigNotFoundError:
        result["missingFields"].append("serviceEndpoint")
    result["ready"] = not result["missingFields"]
    return result


async def resolve_sql_source_basis(
    base_repository: BaseConfigRepository,
    *,
    sys_code: str,
    env_code: str,
    datasource_code: str,
) -> dict[str, Any]:
    """解析 SQL Source 所需系统和数据源是否齐备。"""

    result: dict[str, Any] = {
        "sysCode": sys_code,
        "envCode": env_code,
        "datasourceCode": datasource_code,
        "system": None,
        "datasource": None,
        "missingFields": [],
        "ready": False,
    }
    try:
        system = await base_repository.get_system(sys_code)
        result["system"] = system.model_dump(mode="json")
    except BaseConfigNotFoundError:
        result["missingFields"].append("system")
    try:
        datasource = await base_repository.get_enabled_datasource(
            env_code=env_code,
            sys_code=sys_code,
            datasource_code=datasource_code,
        )
        result["datasource"] = datasource.model_dump(mode="json")
    except BaseConfigNotFoundError:
        result["missingFields"].append("datasource")
    result["ready"] = not result["missingFields"]
    return result


async def upsert_http_source_from_agent(
    http_source_service: HttpSourceService,
    base_repository: BaseConfigRepository,
    *,
    config: HttpSourceConfig,
    env_code: str,
    operator: str | None = "gdp_agent",
) -> dict[str, Any]:
    """Agent 保存 HTTP Source，保存前先检查基础配置缺口。"""

    basis = await resolve_http_source_basis(base_repository, sys_code=config.sysCode, env_code=env_code)
    if not basis["ready"]:
        return {
            "success": False,
            "nextPhase": "INFRA_CONFIG",
            "reason": "HTTP Source 缺少系统或目标环境服务端点，不能直接保存为可测试配置。",
            "basis": basis,
        }
    saved = await http_source_service.upsert_http_source(config, operator=operator)
    return {"success": True, "source": saved.model_dump(mode="json"), "basis": basis}


async def test_http_source_from_agent(
    http_source_service: HttpSourceService,
    *,
    request: HttpSourceTestRequest,
) -> dict[str, Any]:
    """Agent 测试 HTTP Source。"""

    result = await http_source_service.test_http_source(request)
    return result.model_dump(mode="json")


def parse_sql_source_from_agent(request: SqlSourceParseRequest) -> dict[str, Any]:
    """Agent 解析 SQL Source。"""

    return parse_sql_source(request.sqlText, request.parameters).model_dump(mode="json")


async def upsert_sql_source_from_agent(
    sql_source_service: SqlSourceService,
    base_repository: BaseConfigRepository,
    *,
    config: SqlSourceConfig,
    env_code: str,
    operator: str | None = "gdp_agent",
) -> dict[str, Any]:
    """Agent 保存 SQL Source，保存前先检查基础配置缺口。"""

    basis = await resolve_sql_source_basis(
        base_repository,
        sys_code=config.sysCode,
        env_code=env_code,
        datasource_code=config.datasourceCode,
    )
    if not basis["ready"]:
        return {
            "success": False,
            "nextPhase": "INFRA_CONFIG",
            "reason": "SQL Source 缺少系统或目标环境数据源，不能直接保存为可测试配置。",
            "basis": basis,
        }
    saved = await sql_source_service.upsert_sql_source(config, operator=operator)
    return {"success": True, "source": saved.model_dump(mode="json"), "basis": basis}


async def test_sql_source_from_agent(
    sql_execution_service: SqlExecutionService,
    *,
    request: SqlSourceTestRequest,
) -> dict[str, Any]:
    """Agent 测试已保存 SQL Source。"""

    try:
        result = await sql_execution_service.execute_source(request)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result.model_dump(mode="json")


def build_source_config_tools(
    *,
    base_repository: BaseConfigRepository,
    http_source_service: HttpSourceService,
    sql_source_service: SqlSourceService,
    sql_execution_service: SqlExecutionService,
) -> list[StructuredTool]:
    """构造 Source 配置阶段 LangChain 工具。"""

    async def _resolve_http_source_basis(sys_code: str, env_code: str) -> dict[str, Any]:
        return await resolve_http_source_basis(base_repository, sys_code=sys_code, env_code=env_code)

    async def _resolve_sql_source_basis(sys_code: str, env_code: str, datasource_code: str) -> dict[str, Any]:
        return await resolve_sql_source_basis(
            base_repository,
            sys_code=sys_code,
            env_code=env_code,
            datasource_code=datasource_code,
        )

    async def _upsert_http_source_from_agent(config: HttpSourceConfig, env_code: str) -> dict[str, Any]:
        return await upsert_http_source_from_agent(
            http_source_service,
            base_repository,
            config=config,
            env_code=env_code,
        )

    async def _upsert_sql_source_from_agent(config: SqlSourceConfig, env_code: str) -> dict[str, Any]:
        return await upsert_sql_source_from_agent(
            sql_source_service,
            base_repository,
            config=config,
            env_code=env_code,
        )

    async def _test_http_source_from_agent(request: HttpSourceTestRequest) -> dict[str, Any]:
        return await test_http_source_from_agent(http_source_service, request=request)

    async def _test_sql_source_from_agent(request: SqlSourceTestRequest) -> dict[str, Any]:
        return await test_sql_source_from_agent(sql_execution_service, request=request)

    def _parse_sql_source_from_agent(request: SqlSourceParseRequest) -> dict[str, Any]:
        return parse_sql_source_from_agent(request)

    return [
        StructuredTool.from_function(
            coroutine=_resolve_http_source_basis,
            name="resolve_http_source_basis",
            description="解析 HTTP Source 保存和测试前所需的系统、环境服务端点是否齐备。",
        ),
        StructuredTool.from_function(
            coroutine=_resolve_sql_source_basis,
            name="resolve_sql_source_basis",
            description="解析 SQL Source 保存和测试前所需的系统、环境数据源是否齐备。",
        ),
        StructuredTool.from_function(
            coroutine=_upsert_http_source_from_agent,
            name="upsert_http_source_from_agent",
            description="保存 HTTP Source。缺少系统或服务端点时返回 INFRA_CONFIG 缺口，不直接创建基础配置。",
        ),
        StructuredTool.from_function(
            coroutine=_upsert_sql_source_from_agent,
            name="upsert_sql_source_from_agent",
            description="保存 SQL Source。缺少系统或数据源时返回 INFRA_CONFIG 缺口，不直接创建基础配置。",
        ),
        StructuredTool.from_function(
            coroutine=_test_http_source_from_agent,
            name="test_http_source_from_agent",
            description="测试 HTTP Source 配置。",
        ),
        StructuredTool.from_function(
            coroutine=_test_sql_source_from_agent,
            name="test_sql_source_from_agent",
            description="测试已保存 SQL Source 配置。",
        ),
        StructuredTool.from_function(
            func=_parse_sql_source_from_agent,
            name="parse_sql_source_from_agent",
            description="解析 SQL 文本，推导操作类型、表、字段、条件和参数。",
        ),
    ]
