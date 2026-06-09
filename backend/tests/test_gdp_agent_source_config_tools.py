"""GDP Agent Source 配置工具测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.tools.source_config_tools import (
    build_source_config_tools,
    parse_sql_source_from_agent,
    resolve_http_source_basis,
    upsert_http_source_from_agent,
    upsert_sql_source_from_agent,
)
from app.gdp.datagen.config.base.models import EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, InputFieldDefinition, InputFieldType, SqlOperation
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig, SqlSourceParseRequest
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def source_config_services(tmp_path):
    db_path = tmp_path / "gdp-source-config-tools.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        base_repo = BaseConfigRepository(session_factory)
        http_repo = HttpSourceRepository(session_factory)
        sql_repo = SqlSourceRepository(session_factory)
        yield {
            "base": base_repo,
            "http_service": HttpSourceService(http_repo, base_repo),
            "sql_service": SqlSourceService(sql_repo, base_repo),
            "sql_execution": SqlExecutionService(
                base_repository=base_repo,
                sql_source_repository=sql_repo,
                registry=SqlExecutorRegistry(),
            ),
        }
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_resolve_http_source_basis_reports_missing_infra(source_config_services):
    result = await resolve_http_source_basis(source_config_services["base"], sys_code="TRADE", env_code="DEV")

    assert result["ready"] is False
    assert result["missingFields"] == ["system", "serviceEndpoint"]


@pytest.mark.anyio
async def test_upsert_http_source_from_agent_saves_when_basis_ready(source_config_services):
    await _create_http_basis(source_config_services["base"])

    result = await upsert_http_source_from_agent(
        source_config_services["http_service"],
        source_config_services["base"],
        config=_order_http_source(),
        env_code="DEV",
    )

    assert result["success"] is True
    assert result["source"]["sourceCode"] == "createOrderApi"
    assert result["basis"]["ready"] is True


def test_parse_sql_source_from_agent_returns_parameters():
    result = parse_sql_source_from_agent(
        SqlSourceParseRequest(sqlText="SELECT order_id FROM orders WHERE user_id = :userId")
    )

    assert result["operation"] == "SELECT"
    assert [item["name"] for item in result["parameters"]] == ["userId"]


@pytest.mark.anyio
async def test_upsert_sql_source_from_agent_returns_infra_gap_when_datasource_missing(source_config_services):
    await source_config_services["base"].upsert_system(SysConfig(sysCode="TRADE", sysName="交易系统"))
    await source_config_services["base"].upsert_environment(EnvironmentConfig(envCode="DEV", envName="开发环境"))

    result = await upsert_sql_source_from_agent(
        source_config_services["sql_service"],
        source_config_services["base"],
        config=_order_sql_source(),
        env_code="DEV",
    )

    assert result["success"] is False
    assert result["nextPhase"] == "INFRA_CONFIG"
    assert result["basis"]["missingFields"] == ["datasource"]


@pytest.mark.anyio
async def test_build_source_config_tools_exposes_expected_names(source_config_services):
    tools = build_source_config_tools(
        base_repository=source_config_services["base"],
        http_source_service=source_config_services["http_service"],
        sql_source_service=source_config_services["sql_service"],
        sql_execution_service=source_config_services["sql_execution"],
    )

    assert {tool.name for tool in tools} == {
        "resolve_http_source_basis",
        "resolve_sql_source_basis",
        "upsert_http_source_from_agent",
        "upsert_sql_source_from_agent",
        "test_http_source_from_agent",
        "test_sql_source_from_agent",
        "parse_sql_source_from_agent",
    }


async def _create_http_basis(base_repo: BaseConfigRepository) -> None:
    await base_repo.upsert_system(SysConfig(sysCode="TRADE", sysName="交易系统"))
    await base_repo.upsert_environment(EnvironmentConfig(envCode="DEV", envName="开发环境"))
    await base_repo.create_service_endpoint(
        ServiceEndpointConfig(envCode="DEV", sysCode="TRADE", baseUrl="http://trade-dev.example")
    )


def _order_http_source() -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode="createOrderApi",
        sourceName="创建订单接口",
        tags=["订单", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[{"effectType": "CREATE_ORDER", "target": "orders"}],
        agentDescription="创建一笔测试订单，返回订单号。",
        sysCode="TRADE",
        path="/orders",
        method=HttpMethod.POST,
        bodySchema=[
            InputFieldDefinition(
                name="userId",
                label="用户",
                type=InputFieldType.STRING,
                semanticType="USER_ID",
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        status=ConfigStatus.ENABLED,
    )


def _order_sql_source() -> SqlSourceConfig:
    return SqlSourceConfig(
        sourceCode="queryOrderSql",
        sourceName="查询订单 SQL",
        tags=["订单", "查询"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="交易",
        agentDescription="查询订单号。",
        sysCode="TRADE",
        datasourceCode="tradeDb",
        operation=SqlOperation.SELECT,
        sqlText="SELECT order_id FROM orders WHERE user_id = :userId",
    )
