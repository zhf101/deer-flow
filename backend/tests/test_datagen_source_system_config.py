"""Datagen source configuration system ownership tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.router import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def datagen_client(tmp_path):
    db_path = tmp_path / "datagen-source.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_http_source_requires_enabled_system(datagen_client: AsyncClient):
    response = await datagen_client.post(
        "/api/v1/datagen/http-sources",
        json={
            "sourceCode": "createOrder",
            "sourceName": "Create order",
            "sysCode": "ORDER",
            "path": "/orders",
            "method": "POST",
            "requestMapping": {},
            "outputMapping": {},
            "status": "ENABLED",
        },
    )

    assert response.status_code == 422
    assert "enabled system not found" in response.json()["detail"]


@pytest.mark.anyio
async def test_http_source_accepts_enabled_system(datagen_client: AsyncClient):
    await _create_system(datagen_client, "ORDER")

    response = await datagen_client.post(
        "/api/v1/datagen/http-sources",
        json={
            "sourceCode": "createOrder",
            "sourceName": "Create order",
            "sysCode": "ORDER",
            "path": "/orders",
            "method": "POST",
            "requestMapping": {},
            "outputMapping": {},
            "status": "ENABLED",
        },
    )

    assert response.status_code == 200
    assert response.json()["sysCode"] == "ORDER"


@pytest.mark.anyio
async def test_sql_source_requires_enabled_datasource_for_system(datagen_client: AsyncClient):
    await _create_system(datagen_client, "ORDER")

    response = await datagen_client.post(
        "/api/v1/datagen/sql-sources",
        json={
            "sourceCode": "queryOrder",
            "sourceName": "Query order",
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "operation": "SELECT",
            "sqlText": "select * from orders where id = :orderId",
            "parameters": [],
            "status": "ENABLED",
        },
    )

    assert response.status_code == 422
    assert "enabled datasource not found" in response.json()["detail"]


@pytest.mark.anyio
async def test_sql_source_accepts_enabled_datasource_for_system(datagen_client: AsyncClient):
    await _create_system(datagen_client, "ORDER")
    await _create_environment(datagen_client, "DEV")
    await _create_datasource(datagen_client, "DEV", "ORDER", "tradeDb")

    response = await datagen_client.post(
        "/api/v1/datagen/sql-sources",
        json={
            "sourceCode": "queryOrder",
            "sourceName": "Query order",
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "operation": "SELECT",
            "sqlText": "select * from orders where id = :orderId",
            "parameters": [],
            "status": "ENABLED",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sysCode"] == "ORDER"
    assert body["datasourceCode"] == "tradeDb"


async def _create_system(client: AsyncClient, sys_code: str) -> None:
    response = await client.post(
        "/api/v1/datagen/systems",
        json={"sysCode": sys_code, "sysName": f"{sys_code} system", "status": "ENABLED"},
    )
    assert response.status_code == 200


async def _create_environment(client: AsyncClient, env_code: str) -> None:
    response = await client.post(
        "/api/v1/datagen/environments",
        json={"envCode": env_code, "envName": f"{env_code} environment", "status": "ENABLED"},
    )
    assert response.status_code == 200


async def _create_datasource(
    client: AsyncClient,
    env_code: str,
    sys_code: str,
    datasource_code: str,
) -> None:
    response = await client.post(
        "/api/v1/datagen/datasources",
        json={
            "envCode": env_code,
            "sysCode": sys_code,
            "datasourceCode": datasource_code,
            "datasourceName": f"{datasource_code} datasource",
            "dbType": "MySQL",
            "host": "127.0.0.1",
            "port": 3306,
            "databaseName": "trade",
            "status": "ENABLED",
        },
    )
    assert response.status_code == 200
