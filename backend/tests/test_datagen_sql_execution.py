"""造数 SQL 运行时执行测试。"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.router import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def datagen_client(tmp_path):
    db_path = tmp_path / "datagen-config.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_sql_source_test_executes_sqlite_select(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)
    await _create_sql_source(
        datagen_client,
        source_code="queryInventory",
        operation="SELECT",
        sql_text=("SELECT sku_id, stock_num FROM inventory WHERE sku_id = :skuId"),
        parameters=[
            {
                "name": "skuId",
                "type": "string",
                "required": True,
                "defaultValue": "SKU10001",
                "description": "商品 SKU",
            }
        ],
    )

    response = await datagen_client.post(
        "/api/v1/datagen/sql-sources/test",
        json={
            "envCode": "DEV",
            "sourceCode": "queryInventory",
            "parameters": {"skuId": "SKU10001"},
            "options": {"maxRows": 10},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["operation"] == "SELECT"
    assert body["columns"][0]["name"] == "sku_id"
    assert body["row"] == {"sku_id": "SKU10001", "stock_num": 120}
    assert body["affectedRows"] == 0


@pytest.mark.anyio
async def test_sql_source_test_rejects_update_without_where(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)
    await _create_sql_source(
        datagen_client,
        source_code="unsafeUpdate",
        operation="UPDATE",
        sql_text="UPDATE inventory SET stock_num = stock_num - :quantity",
        parameters=[
            {
                "name": "quantity",
                "type": "number",
                "required": True,
                "defaultValue": 1,
            }
        ],
        safety={"requireWhere": True, "maxAffectedRows": 1},
    )

    response = await datagen_client.post(
        "/api/v1/datagen/sql-sources/test",
        json={
            "envCode": "DEV",
            "sourceCode": "unsafeUpdate",
            "parameters": {"quantity": 1},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"]["type"] == "SqlSafetyError"
    assert "顶层 WHERE" in body["error"]["message"]


@pytest.mark.anyio
async def test_sql_source_test_rejects_update_with_only_nested_where(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)
    await _create_sql_source(
        datagen_client,
        source_code="nestedWhereUpdate",
        operation="UPDATE",
        sql_text="UPDATE inventory SET stock_num = (SELECT 1 WHERE 1 = 1)",
        parameters=[],
        safety={"requireWhere": True, "maxAffectedRows": None},
    )

    response = await datagen_client.post(
        "/api/v1/datagen/sql-sources/test",
        json={
            "envCode": "DEV",
            "sourceCode": "nestedWhereUpdate",
            "parameters": {},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"]["type"] == "SqlSafetyError"
    assert "顶层 WHERE" in body["error"]["message"]
    assert _stock_num(business_db, "SKU10001") == 120
    assert _stock_num(business_db, "SKU10002") == 35


@pytest.mark.anyio
async def test_sql_source_test_rolls_back_when_max_affected_rows_exceeded(
    datagen_client: AsyncClient,
    tmp_path,
):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)
    await _create_sql_source(
        datagen_client,
        source_code="bulkLockInventory",
        operation="UPDATE",
        sql_text=("UPDATE inventory SET stock_num = stock_num - :quantity WHERE stock_num >= :quantity"),
        parameters=[
            {
                "name": "quantity",
                "type": "number",
                "required": True,
                "defaultValue": 1,
            }
        ],
        safety={"requireWhere": True, "maxAffectedRows": 1},
    )

    response = await datagen_client.post(
        "/api/v1/datagen/sql-sources/test",
        json={
            "envCode": "DEV",
            "sourceCode": "bulkLockInventory",
            "parameters": {"quantity": 1},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"]["type"] == "SqlSafetyError"
    assert _stock_num(business_db, "SKU10001") == 120
    assert _stock_num(business_db, "SKU10002") == 35


@pytest.mark.anyio
async def test_direct_sql_execute_uses_current_unsaved_sql(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    await _create_base_sqlite_config(datagen_client, business_db)

    response = await datagen_client.post(
        "/api/v1/datagen/sql/execute",
        json={
            "envCode": "DEV",
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "operation": "SELECT",
            "sqlText": "SELECT sku_id FROM inventory WHERE sku_id = :skuId",
            "parameters": {"skuId": "SKU10002"},
            "options": {"maxRows": 5},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["row"] == {"sku_id": "SKU10002"}


@pytest.mark.anyio
async def test_direct_sql_execute_rejects_removed_transaction_mode(datagen_client: AsyncClient):
    response = await datagen_client.post(
        "/api/v1/datagen/sql/execute",
        json={
            "envCode": "DEV",
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "operation": "UPDATE",
            "sqlText": "UPDATE inventory SET stock_num = stock_num - 1 WHERE sku_id = :skuId",
            "parameters": {"skuId": "SKU10001"},
            "options": {"transactionMode": "READ_ONLY"},
        },
    )

    assert response.status_code == 422


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


async def _create_sql_source(
    client: AsyncClient,
    *,
    source_code: str,
    operation: str,
    sql_text: str,
    parameters: list[dict],
    safety: dict | None = None,
) -> None:
    await _post_ok(
        client,
        "/api/v1/datagen/sql-sources",
        {
            "sourceCode": source_code,
            "sourceName": source_code,
            "sysCode": "ORDER",
            "datasourceCode": "tradeDb",
            "operation": operation,
            "sqlText": sql_text,
            "parameters": parameters,
            "safety": safety or {"requireWhere": True, "maxAffectedRows": None},
            "status": "ENABLED",
        },
    )


async def _post_ok(client: AsyncClient, path: str, json: dict) -> None:
    response = await client.post(path, json=json)
    assert response.status_code == 200, response.text


def _stock_num(path, sku_id: str) -> int:
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT stock_num FROM inventory WHERE sku_id = ?",
            (sku_id,),
        ).fetchone()
        return row[0]
