"""SQL 步骤的场景执行测试。"""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

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
    assert body["runId"]
    assert body["inputs"] == {"skuId": "SKU10001"}
    assert body["status"] == "SUCCESS"
    assert body["stepResults"][0]["stepId"] == "queryInventory"
    assert body["stepResults"][0]["stepOrder"] == 1
    assert body["stepResults"][0]["timelineOrder"] == 1
    assert body["stepResults"][0]["status"] == "SUCCESS"
    assert body["stepResults"][0]["outputs"] == {"stockNum": 120}
    assert body["finalOutput"] == {"stockNum": 120}
    assert body["errors"] == []

    detail = await datagen_client.get(f"/api/v1/datagen/scenes/runs/{body['runId']}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["runId"] == body["runId"]
    assert detail_body["inputs"] == {"skuId": "SKU10001"}
    assert detail_body["stepResults"][0]["outputs"] == {"stockNum": 120}
    assert detail_body["stepResults"][0]["rawResponse"]["rows"] == [{"sku_id": "SKU10001", "stock_num": 120}]


@pytest.mark.anyio
async def test_run_scene_executes_http_step_then_sql_step(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    http_server = _start_token_server()
    try:
        await _create_base_sqlite_config(datagen_client, business_db)
        await _create_http_base_config(datagen_client, http_server.base_url)
        await _create_http_sql_scene(datagen_client)

        publish = await datagen_client.post("/api/v1/datagen/scenes/httpSqlScene/publish")
        assert publish.status_code == 200, publish.text

        response = await datagen_client.post(
            "/api/v1/datagen/scenes/run",
            json={
                "sceneCode": "httpSqlScene",
                "envCode": "DEV",
                "inputs": {"userId": "U10001", "skuId": "SKU10001"},
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sceneCode"] == "httpSqlScene"
        assert body["runId"]
        assert body["inputs"] == {"userId": "U10001", "skuId": "SKU10001"}
        assert body["status"] == "SUCCESS"
        assert [item["stepId"] for item in body["stepResults"]] == ["getToken", "queryInventory"]
        assert [item["stepOrder"] for item in body["stepResults"]] == [1, 2]
        assert [item["timelineOrder"] for item in body["stepResults"]] == [1, 2]
        assert body["stepResults"][0]["status"] == "SUCCESS"
        assert body["stepResults"][0]["outputs"] == {"accessToken": "token_for_U10001"}
        assert body["stepResults"][1]["status"] == "SUCCESS"
        assert body["stepResults"][1]["outputs"] == {"stockNum": 120}
        assert body["finalOutput"] == {
            "accessToken": "token_for_U10001",
            "stockNum": 120,
        }
        assert body["errors"] == []

        detail = await datagen_client.get(f"/api/v1/datagen/scenes/runs/{body['runId']}")
        assert detail.status_code == 200, detail.text
        detail_body = detail.json()
        assert detail_body["stepResults"][0]["rawResponse"]["request"]["url"].endswith("/oauth/token")
        assert detail_body["stepResults"][0]["rawResponse"]["response"]["body"]["data"]["accessToken"] == "token_for_U10001"
        assert detail_body["stepResults"][1]["rawResponse"]["rows"] == [{"sku_id": "SKU10001", "stock_num": 120}]
    finally:
        http_server.stop()


@pytest.mark.anyio
async def test_stop_on_error_respects_scene_step_order(datagen_client: AsyncClient, tmp_path):
    business_db = tmp_path / "trade.sqlite"
    _create_business_db(business_db)
    http_server = _start_token_server()
    try:
        await _create_base_sqlite_config(datagen_client, business_db)
        await _create_http_base_config(datagen_client, http_server.base_url)
        await _create_stop_order_scene(datagen_client)

        publish = await datagen_client.post("/api/v1/datagen/scenes/stopOrderScene/publish")
        assert publish.status_code == 200, publish.text

        response = await datagen_client.post(
            "/api/v1/datagen/scenes/run",
            json={
                "sceneCode": "stopOrderScene",
                "envCode": "DEV",
                "inputs": {"userId": "U10001", "skuId": "SKU10001"},
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "PARTIAL"
        assert [item["stepId"] for item in body["stepResults"]] == ["getToken", "missingSession"]
        assert [item["stepOrder"] for item in body["stepResults"]] == [1, 2]
        assert [item["timelineOrder"] for item in body["stepResults"]] == [1, 2]
        assert body["stepResults"][1]["status"] == "FAILED"
        assert body["stepResults"][1]["statusCode"] == 501
        assert body["errors"] == ["missingSession: HTTP 状态码 501 不在成功列表 [200] 中"]
    finally:
        http_server.stop()


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


async def _create_stop_order_scene(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/datagen/scenes",
        json={
            "sceneCode": "stopOrderScene",
            "sceneName": "Stop on error follows scene order",
            "sceneRemark": "测试 STOP_ON_ERROR 策略按场景步骤顺序停止执行。",
            "tags": ["order", "error-policy"],
            "capabilityType": "QUERY",
            "businessDomain": "trade",
            "agentDescription": "验证 HTTP 步骤失败后，场景按 STOP_ON_ERROR 策略停止后续步骤。",
            "inputSchema": [
                {
                    "name": "userId",
                    "label": "User",
                    "type": "string",
                    "required": True,
                    "batchEnabled": False,
                },
                {
                    "name": "skuId",
                    "label": "SKU",
                    "type": "string",
                    "required": True,
                    "batchEnabled": False,
                },
            ],
            "steps": [
                {
                    "stepId": "getToken",
                    "stepName": "获取 Token",
                    "type": "HTTP",
                    "enabled": True,
                    "dependsOn": [],
                    "sysCode": "AUTH",
                    "method": "POST",
                    "path": "/oauth/token",
                    "timeoutConfig": {
                        "connectTimeoutSeconds": 5,
                        "readTimeoutSeconds": 5,
                        "writeTimeoutSeconds": 5,
                        "poolTimeoutSeconds": 5,
                    },
                    "requestMapping": {
                        "headers": {"Content-Type": "application/json"},
                        "bodyType": "raw-json",
                        "rawBody": "{\"username\":\"${input.userId}\"}",
                    },
                    "httpParamMapping": {},
                    "outputMapping": {
                        "accessToken": "${RES_BODY(data.accessToken)}",
                    },
                },
                {
                    "stepId": "missingSession",
                    "stepName": "失败登录",
                    "type": "HTTP",
                    "enabled": True,
                    "dependsOn": ["getToken"],
                    "sysCode": "AUTH",
                    "method": "GET",
                    "path": "/missing-session",
                    "timeoutConfig": {
                        "connectTimeoutSeconds": 5,
                        "readTimeoutSeconds": 5,
                        "writeTimeoutSeconds": 5,
                        "poolTimeoutSeconds": 5,
                    },
                    "requestMapping": {
                        "headers": {"Accept": "application/json"},
                        "bodyType": "none",
                    },
                    "httpParamMapping": {},
                    "responseHandling": {
                        "statusCode": {"success": [200]},
                        "businessSuccess": {"allOf": [], "anyOf": []},
                        "businessFailure": {"allOf": [], "anyOf": []},
                    },
                    "outputMapping": {},
                },
                {
                    "stepId": "queryInventory",
                    "stepName": "独立 SQL",
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
                },
            ],
            "resultMapping": {
                "accessToken": "${steps.getToken.outputs.accessToken}",
                "stockNum": "${steps.queryInventory.outputs.stockNum}",
            },
            "errorPolicy": "STOP_ON_ERROR",
            "batchConfig": {
                "enabled": False,
                "failurePolicy": "STOP_ON_ERROR",
                "maxConcurrency": 1,
            },
            "status": "DRAFT",
        },
    )
    assert response.status_code == 200, response.text


async def _create_http_sql_scene(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/datagen/scenes",
        json={
            "sceneCode": "httpSqlScene",
            "sceneName": "HTTP and SQLite SQL scene",
            "sceneRemark": "先调用认证接口获取 Token，再查询库存数据。",
            "tags": ["auth", "inventory"],
            "capabilityType": "QUERY",
            "businessDomain": "trade",
            "agentDescription": "根据用户和商品信息获取访问令牌并查询库存数量。",
            "inputSchema": [
                {
                    "name": "userId",
                    "label": "User",
                    "type": "string",
                    "required": True,
                    "batchEnabled": False,
                },
                {
                    "name": "skuId",
                    "label": "SKU",
                    "type": "string",
                    "required": True,
                    "batchEnabled": False,
                },
            ],
            "steps": [
                {
                    "stepId": "getToken",
                    "stepName": "获取 Token",
                    "type": "HTTP",
                    "enabled": True,
                    "dependsOn": [],
                    "sysCode": "AUTH",
                    "method": "POST",
                    "path": "/oauth/token",
                    "timeoutConfig": {
                        "connectTimeoutSeconds": 5,
                        "readTimeoutSeconds": 5,
                        "writeTimeoutSeconds": 5,
                        "poolTimeoutSeconds": 5,
                    },
                    "requestMapping": {
                        "headers": {"Content-Type": "application/json"},
                        "bodyType": "raw-json",
                        "rawBody": "{\"username\":\"${input.userId}\"}",
                    },
                    "httpParamMapping": {},
                    "outputMapping": {
                        "accessToken": "${RES_BODY(data.accessToken)}",
                    },
                },
                {
                    "stepId": "queryInventory",
                    "stepName": "按 Token 查询库存",
                    "type": "SQL",
                    "enabled": True,
                    "dependsOn": ["getToken"],
                    "sysCode": "ORDER",
                    "datasourceCode": "tradeDb",
                    "operation": "SELECT",
                    "sqlText": "SELECT sku_id, stock_num FROM inventory WHERE sku_id = :skuId AND owner_token = :token",
                    "normalizedSql": "SELECT sku_id, stock_num FROM inventory WHERE sku_id = :skuId AND owner_token = :token",
                    "parameters": [
                        {
                            "name": "skuId",
                            "type": "string",
                            "required": True,
                            "description": "商品 SKU",
                        },
                        {
                            "name": "token",
                            "type": "string",
                            "required": True,
                            "description": "HTTP 步骤返回的 Token",
                        },
                    ],
                    "paramMapping": {
                        "skuId": "${input.skuId}",
                        "token": "${steps.getToken.outputs.accessToken}",
                    },
                    "safety": {"requireWhere": True, "maxAffectedRows": None},
                    "outputMapping": {"stockNum": "${SQL_RESULT(row.stock_num)}"},
                },
            ],
            "resultMapping": {
                "accessToken": "${steps.getToken.outputs.accessToken}",
                "stockNum": "${steps.queryInventory.outputs.stockNum}",
            },
            "batchConfig": {
                "enabled": False,
                "failurePolicy": "STOP_ON_ERROR",
                "maxConcurrency": 1,
            },
            "status": "DRAFT",
        },
    )
    assert response.status_code == 200, response.text


async def _create_sql_scene(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/datagen/scenes",
        json={
            "sceneCode": "sqliteScene",
            "sceneName": "SQLite SQL scene",
            "sceneRemark": "按商品 SKU 查询 SQLite 库存数据。",
            "tags": ["inventory"],
            "capabilityType": "QUERY",
            "businessDomain": "trade",
            "agentDescription": "根据商品 SKU 查询库存数量。",
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


async def _create_http_base_config(client: AsyncClient, base_url: str) -> None:
    await _post_ok(
        client,
        "/api/v1/datagen/systems",
        {"sysCode": "AUTH", "sysName": "Auth system", "status": "ENABLED"},
    )
    await _post_ok(
        client,
        "/api/v1/datagen/service-endpoints",
        {
            "envCode": "DEV",
            "sysCode": "AUTH",
            "baseUrl": base_url,
            "status": "ENABLED",
        },
    )


def _create_business_db(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE inventory (
              sku_id TEXT PRIMARY KEY,
              stock_num INTEGER NOT NULL,
              owner_token TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.executemany(
            "INSERT INTO inventory(sku_id, stock_num, owner_token) VALUES (?, ?, ?)",
            [
                ("SKU10001", 120, "token_for_U10001"),
                ("SKU10002", 35, "token_for_U10002"),
            ],
        )
        conn.commit()


class _TokenServer:
    def __init__(self, server: ThreadingHTTPServer, thread: Thread) -> None:
        self._server = server
        self._thread = thread
        self.base_url = f"http://127.0.0.1:{server.server_port}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _start_token_server() -> _TokenServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            length = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            username = str(payload.get("username") or "unknown")
            body = json.dumps(
                {
                    "success": True,
                    "data": {"accessToken": f"token_for_{username}"},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return _TokenServer(server, thread)


async def _post_ok(client: AsyncClient, path: str, json: dict) -> None:
    response = await client.post(path, json=json)
    assert response.status_code == 200, response.text
