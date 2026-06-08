"""SQL 步骤的场景执行测试。"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.router import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def datagen_client(tmp_path):
    db_path = tmp_path / "datagen-scene.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_run_scene_executes_published_sqlite_sql_step(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)
    await _create_sql_scene(datagen_client)

    publish = await datagen_client.post("/api/v1/datagen/scenes/sqliteScene/publish")
    assert publish.status_code == 200, publish.text

    response = await datagen_client.post(
        "/api/v1/datagen/scenes/run",
        json={
            "sceneCode": "sqliteScene",
            "envCode": "DEV",
            "inputs": {"skuId": "SKU10001"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sceneCode"] == "sqliteScene"
    assert body["status"] == "SUCCESS"
    assert body["stepResults"][0]["stepId"] == "queryInventory"
    assert body["stepResults"][0]["status"] == "SUCCESS"
    assert body["stepResults"][0]["outputs"] == {"stockNum": 120}
    assert body["finalOutput"] == {"stockNum": 120}
    assert body["errors"] == []


@pytest.mark.anyio
async def test_run_scene_requires_published_version(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)
    await _create_sql_scene(datagen_client)

    response = await datagen_client.post(
        "/api/v1/datagen/scenes/run",
        json={
            "sceneCode": "sqliteScene",
            "envCode": "DEV",
            "inputs": {"skuId": "SKU10001"},
        },
    )

    assert response.status_code == 404
    assert "published scene version not found" in response.json()["detail"]


def test_scene_run_route_uses_post_body_scene_code():
    route_paths = {
        f"{method} {route.path}"
        for route in router.routes
        if hasattr(route, "methods") and hasattr(route, "path")
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert "POST /api/v1/datagen/scenes/run" in route_paths


async def _create_sql_scene(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/datagen/scenes",
        json={
            "sceneCode": "sqliteScene",
            "sceneName": "SQLite SQL scene",
            "inputSchema": [
                {
                    "name": "skuId",
                    "label": "SKU",
                    "type": "string",
                    "required": True,
                    "batchEnabled": False,
                }
            ],
            "steps": [
                {
                    "stepId": "queryInventory",
                    "stepName": "查询库存",
                    "type": "SQL",
                    "enabled": True,
                    "dependsOn": [],
                    "sysCode": "ORDER",
                    "datasourceCode": "tradeDb",
                    "operation": "SELECT",
                    "sqlText": "SELECT sku_id, stock_num FROM inventory WHERE sku_id = :skuId",
                    "normalizedSql": "SELECT sku_id, stock_num FROM inventory WHERE sku_id = :skuId",
                    "parameters": [
                        {
                            "name": "skuId",
                            "type": "string",
                            "required": True,
                            "description": "商品 SKU",
                        }
                    ],
                    "paramMapping": {"skuId": "${input.skuId}"},
                    "safety": {"requireWhere": True, "maxAffectedRows": None},
                    "outputMapping": {"stockNum": "${SQL_RESULT(row.stock_num)}"},
                }
            ],
            "resultMapping": {"stockNum": "${steps.queryInventory.outputs.stockNum}"},
            "batchConfig": {
                "enabled": False,
                "failurePolicy": "STOP_ON_ERROR",
                "maxConcurrency": 1,
            },
            "status": "DRAFT",
        },
    )
    assert response.status_code == 200, response.text


async def _create_base_sqlite_config(client: AsyncClient, database_path) -> None:
    await _post_ok(
        client,
        "/api/v1/datagen/systems",
        {"sysCode": "ORDER", "sysName": "Order system", "status": "ENABLED"},
    )
    await _post_ok(
        client,
        "/api/v1/datagen/environments",
        {"envCode": "DEV", "envName": "Development", "status": "ENABLED"},
    )
    await _post_ok(
        client,
        "/api/v1/datagen/datasources",
        {
            "envCode": "DEV",
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "datasourceName": "Trade SQLite",
            "dbType": "SQLite",
            "host": "localhost",
            "port": 1,
            "databaseName": str(database_path),
            "status": "ENABLED",
        },
    )


def _create_business_db(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE inventory (
              sku_id TEXT PRIMARY KEY,
              stock_num INTEGER NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO inventory(sku_id, stock_num) VALUES (?, ?)",
            [("SKU10001", 120), ("SKU10002", 35)],
        )
        conn.commit()


async def _post_ok(client: AsyncClient, path: str, json: dict) -> None:
    response = await client.post(path, json=json)
    assert response.status_code == 200, response.text
