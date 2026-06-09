"""GDP Agent Source 和基础配置 API 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.datagen.config.base.models import DatasourceConfig, EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, SqlOperation
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig
from app.gdp.router import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def agent_config_client(tmp_path):
    db_path = tmp_path / "gdp-agent-source-infra-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_agent_http_source_api_reports_infra_gap_then_saves(agent_config_client: AsyncClient):
    gap = await agent_config_client.post(
        "/api/v1/datagen/agent/sources/http/upsert",
        json={"envCode": "DEV", "config": _order_http_source().model_dump(mode="json")},
    )

    assert gap.status_code == 200, gap.text
    assert gap.json()["success"] is False
    assert gap.json()["nextPhase"] == "INFRA_CONFIG"
    assert gap.json()["basis"]["missingFields"] == ["system", "serviceEndpoint"]

    await _create_http_basis(agent_config_client)
    basis = await agent_config_client.post(
        "/api/v1/datagen/agent/sources/http/basis",
        json={"envCode": "DEV", "sysCode": "TRADE"},
    )
    assert basis.status_code == 200, basis.text
    assert basis.json()["ready"] is True

    saved = await agent_config_client.post(
        "/api/v1/datagen/agent/sources/http/upsert",
        json={"envCode": "DEV", "config": _order_http_source().model_dump(mode="json")},
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["success"] is True
    assert saved.json()["source"]["sourceCode"] == "createOrderApi"


@pytest.mark.anyio
async def test_agent_sql_source_api_parse_and_save(agent_config_client: AsyncClient):
    await _create_sql_basis(agent_config_client)

    parsed = await agent_config_client.post(
        "/api/v1/datagen/agent/sources/sql/parse",
        json={"sqlText": "SELECT order_id FROM orders WHERE user_id = :userId"},
    )
    assert parsed.status_code == 200, parsed.text
    assert parsed.json()["operation"] == "SELECT"
    assert parsed.json()["parameters"][0]["name"] == "userId"

    basis = await agent_config_client.post(
        "/api/v1/datagen/agent/sources/sql/basis",
        json={"envCode": "DEV", "sysCode": "TRADE", "datasourceCode": "tradeDb"},
    )
    assert basis.status_code == 200, basis.text
    assert basis.json()["ready"] is True

    saved = await agent_config_client.post(
        "/api/v1/datagen/agent/sources/sql/upsert",
        json={"envCode": "DEV", "config": _order_sql_source().model_dump(mode="json")},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["success"] is True
    assert saved.json()["source"]["sourceCode"] == "queryOrderSql"


@pytest.mark.anyio
async def test_agent_infra_api_resolve_and_upsert(agent_config_client: AsyncClient):
    missing = await agent_config_client.post(
        "/api/v1/datagen/agent/infra/resolve",
        json={"query": "交易订单", "envCode": "DEV", "sysCode": "TRADE", "resourceType": "HTTP"},
    )
    assert missing.status_code == 200, missing.text
    assert missing.json()["ready"] is False
    assert missing.json()["missingFields"] == ["system", "environment", "serviceEndpoint"]

    await _create_http_basis(agent_config_client)
    ready = await agent_config_client.post(
        "/api/v1/datagen/agent/infra/resolve",
        json={"query": "交易订单", "envCode": "DEV", "sysCode": "TRADE", "resourceType": "HTTP"},
    )

    assert ready.status_code == 200, ready.text
    assert ready.json()["ready"] is True
    assert ready.json()["matchedSystems"][0]["sysCode"] == "TRADE"


def test_agent_source_and_infra_routes_only_use_post():
    route_methods = {
        method
        for route in router.routes
        if hasattr(route, "path")
        and (
            str(route.path).startswith("/api/v1/datagen/agent/sources")
            or str(route.path).startswith("/api/v1/datagen/agent/infra")
        )
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert route_methods == {"POST"}


async def _create_http_basis(client: AsyncClient) -> None:
    system = await client.post(
        "/api/v1/datagen/agent/infra/systems/upsert",
        json={"config": SysConfig(sysCode="TRADE", sysName="交易系统").model_dump(mode="json")},
    )
    assert system.status_code == 200, system.text
    environment = await client.post(
        "/api/v1/datagen/agent/infra/environments/upsert",
        json={"config": EnvironmentConfig(envCode="DEV", envName="开发环境").model_dump(mode="json")},
    )
    assert environment.status_code == 200, environment.text
    endpoint = await client.post(
        "/api/v1/datagen/agent/infra/service-endpoints/upsert",
        json={
            "config": ServiceEndpointConfig(
                envCode="DEV",
                sysCode="TRADE",
                baseUrl="http://trade-dev.example",
            ).model_dump(mode="json")
        },
    )
    assert endpoint.status_code == 200, endpoint.text


async def _create_sql_basis(client: AsyncClient) -> None:
    await _create_http_basis(client)
    datasource = await client.post(
        "/api/v1/datagen/agent/infra/datasources/upsert",
        json={
            "config": DatasourceConfig(
                envCode="DEV",
                sysCode="TRADE",
                datasourceCode="tradeDb",
                datasourceName="交易库",
                dbType="sqlite",
                host="localhost",
                port=1,
                databaseName="trade.sqlite",
            ).model_dump(mode="json")
        },
    )
    assert datasource.status_code == 200, datasource.text


def _order_http_source() -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode="createOrderApi",
        sourceName="创建订单接口",
        tags=["订单", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sysCode="TRADE",
        path="/orders",
        method=HttpMethod.POST,
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
        sysCode="TRADE",
        datasourceCode="tradeDb",
        operation=SqlOperation.SELECT,
        sqlText="SELECT order_id FROM orders WHERE user_id = :userId",
    )
