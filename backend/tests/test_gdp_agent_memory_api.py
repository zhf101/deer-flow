"""GDP Agent 记忆 API 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.router import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def memory_client(tmp_path):
    db_path = tmp_path / "gdp-agent-memory-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_agent_memory_fact_api_create_list_update_disable_delete(memory_client: AsyncClient):
    created = await memory_client.post(
        "/api/v1/datagen/agent-memory/facts/create",
        json={
            "userId": "user_1",
            "scopeType": "USER",
            "scopeKey": "user_1",
            "category": "system_alias",
            "memoryKey": "trade-system-alias",
            "value": {"sysCode": "TRADE", "aliases": ["交易", "订单"]},
            "confidence": 0.9,
            "evidenceSummary": "用户多次把交易系统称为订单系统。",
        },
    )
    assert created.status_code == 200, created.text
    fact = created.json()
    assert fact["factId"].startswith("mem_")
    assert fact["status"] == "ACTIVE"

    listed = await memory_client.get(
        "/api/v1/datagen/agent-memory/facts",
        params={"userId": "user_1", "category": "system_alias"},
    )
    assert listed.status_code == 200, listed.text
    assert [item["factId"] for item in listed.json()] == [fact["factId"]]

    updated = await memory_client.post(
        "/api/v1/datagen/agent-memory/facts/update",
        json={
            "factId": fact["factId"],
            "confidence": 0.95,
            "value": {"sysCode": "TRADE", "aliases": ["交易", "订单", "下单"]},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["confidence"] == 0.95
    assert updated.json()["value"]["aliases"][-1] == "下单"

    disabled = await memory_client.post(
        "/api/v1/datagen/agent-memory/facts/disable",
        json={"factId": fact["factId"]},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "DISABLED"

    deleted = await memory_client.post(
        "/api/v1/datagen/agent-memory/facts/delete",
        json={"factId": fact["factId"]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["reloaded"] is True

    empty = await memory_client.get("/api/v1/datagen/agent-memory/facts", params={"userId": "user_1"})
    assert empty.status_code == 200, empty.text
    assert empty.json() == []


@pytest.mark.anyio
async def test_agent_memory_routes_only_use_get_and_post(memory_client: AsyncClient):
    route_methods = {
        method
        for route in router.routes
        if hasattr(route, "path") and str(route.path).startswith("/api/v1/datagen/agent-memory")
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert route_methods == {"GET", "POST"}
