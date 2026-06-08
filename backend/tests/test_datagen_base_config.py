"""Datagen base configuration API tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.datagen.config.base.api import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def base_config_client(tmp_path):
    db_path = tmp_path / "datagen-base.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/datagen")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_base_config_crud_matches_frontend_contract(base_config_client: AsyncClient):
    sys_resp = await base_config_client.post(
        "/api/v1/datagen/systems",
        json={"sysCode": "ORDER", "sysName": "Order System", "status": "ENABLED", "remark": "orders"},
    )
    assert sys_resp.status_code == 200
    system = sys_resp.json()
    assert system["sysCode"] == "ORDER"
    assert system["sysName"] == "Order System"

    env_resp = await base_config_client.post(
        "/api/v1/datagen/environments",
        json={"envCode": "DEV", "envName": "Development", "status": "ENABLED", "remark": "local"},
    )
    assert env_resp.status_code == 200
    env = env_resp.json()
    assert env["envCode"] == "DEV"
    assert env["envName"] == "Development"
    assert env["createdAt"]
    assert env["updatedAt"]

    endpoint_resp = await base_config_client.post(
        "/api/v1/datagen/service-endpoints",
        json={
            "envCode": "DEV",
            "sysCode": "ORDER",
            "baseUrl": "https://dev.example.test",
            "status": "ENABLED",
        },
    )
    assert endpoint_resp.status_code == 200
    endpoint = endpoint_resp.json()
    assert endpoint["sysCode"] == "ORDER"

    datasource_resp = await base_config_client.post(
        "/api/v1/datagen/datasources",
        json={
            "envCode": "DEV",
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "datasourceName": "Trade DB",
            "dbType": "MySQL",
            "host": "127.0.0.1",
            "port": 3306,
            "databaseName": "trade",
            "username": "tester",
            "password": "secret",
            "status": "ENABLED",
        },
    )
    assert datasource_resp.status_code == 200
    datasource = datasource_resp.json()
    assert datasource["sysCode"] == "ORDER"
    assert datasource["datasourceCode"] == "tradeDb"
    assert datasource["databaseName"] == "trade"

    systems = (await base_config_client.get("/api/v1/datagen/systems")).json()
    system_detail = (await base_config_client.get("/api/v1/datagen/systems/ORDER")).json()
    envs = (await base_config_client.get("/api/v1/datagen/environments")).json()
    env_detail = (await base_config_client.get("/api/v1/datagen/environments/DEV")).json()
    endpoints = (await base_config_client.get("/api/v1/datagen/service-endpoints?envCode=DEV&sysCode=ORDER")).json()
    datasources = (await base_config_client.get("/api/v1/datagen/datasources?envCode=DEV&sysCode=ORDER")).json()

    assert [item["sysCode"] for item in systems] == ["ORDER"]
    assert system_detail["sysCode"] == "ORDER"
    assert [item["envCode"] for item in envs] == ["DEV"]
    assert env_detail["envCode"] == "DEV"
    assert [item["sysCode"] for item in endpoints] == ["ORDER"]
    assert [item["datasourceCode"] for item in datasources] == ["tradeDb"]


@pytest.mark.anyio
async def test_base_config_requires_existing_environment(base_config_client: AsyncClient):
    response = await base_config_client.post(
        "/api/v1/datagen/service-endpoints",
        json={
            "envCode": "MISSING",
            "sysCode": "ORDER",
            "baseUrl": "https://missing.example.test",
            "status": "ENABLED",
        },
    )

    assert response.status_code == 404
    assert "environment not found" in response.json()["detail"]


@pytest.mark.anyio
async def test_base_config_requires_existing_system(base_config_client: AsyncClient):
    env_resp = await base_config_client.post(
        "/api/v1/datagen/environments",
        json={"envCode": "DEV", "envName": "Development", "status": "ENABLED"},
    )
    assert env_resp.status_code == 200

    response = await base_config_client.post(
        "/api/v1/datagen/service-endpoints",
        json={
            "envCode": "DEV",
            "sysCode": "MISSING",
            "baseUrl": "https://missing.example.test",
            "status": "ENABLED",
        },
    )

    assert response.status_code == 404
    assert "system not found" in response.json()["detail"]
