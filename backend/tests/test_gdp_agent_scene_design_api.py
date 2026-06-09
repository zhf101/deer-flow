"""GDP Agent 场景设计 API 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, InputFieldDefinition, InputFieldType
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.router import router
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def agent_scene_client(tmp_path):
    db_path = tmp_path / "gdp-agent-scene-design-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        await HttpSourceRepository(session_factory).upsert_http_source(_order_http_source())
        task_run = await DatagenTaskService(DatagenTaskRepository(session_factory)).create_task_run(
            DatagenTaskRunCreateRequest(userIntent="帮我造一笔订单")
        )
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, task_run.taskRunId
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_agent_scene_design_api_draft_validate_and_publish(agent_scene_client):
    client, task_run_id = agent_scene_client
    search = await client.post(
        "/api/v1/datagen/agent/catalog/sources/search",
        json={"goal": "帮我造一笔订单", "userInputs": {"buyerId": "U1"}},
    )
    assert search.status_code == 200, search.text
    source_contract = search.json()["candidates"][0]["contract"]

    draft = await client.post(
        "/api/v1/datagen/agent/scenes/draft",
        json={"taskRunId": task_run_id, "goal": "帮我造一笔订单", "sourceContract": source_contract},
    )
    assert draft.status_code == 200, draft.text
    definition = draft.json()["definition"]
    assert definition["steps"][0]["templateRef"]["sourceCode"] == "createOrderApi"

    validate = await client.post(
        "/api/v1/datagen/agent/scenes/validate",
        json={"definition": definition},
    )
    assert validate.status_code == 200, validate.text
    assert validate.json()["valid"] is True

    publish = await client.post(
        "/api/v1/datagen/agent/scenes/publish",
        json={"taskRunId": task_run_id, "goal": "帮我造一笔订单", "sourceContract": source_contract},
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["sceneCode"].startswith("agent_createOrderApi_")


def test_agent_scene_design_routes_only_use_post():
    route_methods = {
        method
        for route in router.routes
        if hasattr(route, "path") and str(route.path).startswith("/api/v1/datagen/agent/scenes")
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert route_methods == {"POST"}


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
                aliases=["buyerId"],
                required=False,
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        outputMeta={"orderId": {"label": "订单号", "remark": "创建后的订单号。", "semanticType": "ORDER_ID"}},
        status=ConfigStatus.ENABLED,
    )
