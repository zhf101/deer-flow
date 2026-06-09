"""GDP Agent 基础配置工具测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.tools.infra_config_tools import (
    build_infra_config_tools,
    resolve_infra_basis,
    upsert_datasource_from_agent,
    upsert_environment_from_agent,
    upsert_service_endpoint_from_agent,
    upsert_system_from_agent,
)
from app.gdp.datagen.config.base.models import DatasourceConfig, EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def base_repo(tmp_path):
    db_path = tmp_path / "gdp-infra-config-tools.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        yield BaseConfigRepository(session_factory)
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_resolve_infra_basis_reports_missing_fields(base_repo: BaseConfigRepository):
    result = await resolve_infra_basis(base_repo, query="交易订单", env_code="DEV", sys_code="TRADE")

    assert result["ready"] is False
    assert result["missingFields"] == ["system", "environment", "serviceEndpoint"]
    assert result["confidence"] == 0.0


@pytest.mark.anyio
async def test_upsert_http_infra_then_resolve_ready(base_repo: BaseConfigRepository):
    await upsert_system_from_agent(base_repo, config=SysConfig(sysCode="TRADE", sysName="交易系统"))
    await upsert_environment_from_agent(base_repo, config=EnvironmentConfig(envCode="DEV", envName="开发环境"))
    await upsert_service_endpoint_from_agent(
        base_repo,
        config=ServiceEndpointConfig(envCode="DEV", sysCode="TRADE", baseUrl="http://trade-dev.example"),
    )

    result = await resolve_infra_basis(base_repo, query="交易订单", env_code="DEV", sys_code="TRADE")

    assert result["ready"] is True
    assert result["missingFields"] == []
    assert result["matchedSystems"][0]["sysCode"] == "TRADE"
    assert result["matchedServiceEndpoints"][0]["baseUrl"] == "http://trade-dev.example"


@pytest.mark.anyio
async def test_upsert_datasource_then_resolve_sql_ready(base_repo: BaseConfigRepository):
    await upsert_system_from_agent(base_repo, config=SysConfig(sysCode="TRADE", sysName="交易系统"))
    await upsert_environment_from_agent(base_repo, config=EnvironmentConfig(envCode="DEV", envName="开发环境"))
    await upsert_datasource_from_agent(
        base_repo,
        config=DatasourceConfig(
            envCode="DEV",
            sysCode="TRADE",
            datasourceCode="tradeDb",
            datasourceName="交易库",
            dbType="sqlite",
            host="localhost",
            port=1,
            databaseName="trade.sqlite",
        ),
    )

    result = await resolve_infra_basis(
        base_repo,
        query="交易订单",
        env_code="DEV",
        sys_code="TRADE",
        datasource_code="tradeDb",
        resource_type="SQL",
    )

    assert result["ready"] is True
    assert result["matchedDatasources"][0]["datasourceCode"] == "tradeDb"


@pytest.mark.anyio
async def test_build_infra_config_tools_exposes_expected_names(base_repo: BaseConfigRepository):
    tools = build_infra_config_tools(base_repo)

    assert {tool.name for tool in tools} == {
        "resolve_infra_basis",
        "upsert_system_from_agent",
        "upsert_environment_from_agent",
        "upsert_service_endpoint_from_agent",
        "upsert_datasource_from_agent",
    }
