"""Agent 能力目录测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.datagen.agent_catalog.models import AgentInfraResolveRequest, AgentSceneSearchRequest, AgentSourceSearchRequest
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.base.models import EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, InputFieldDefinition, InputFieldType, SceneStatus
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.models import BatchConfig, HttpStepDefinition, SceneDefinition, ValidationResult
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.router import router
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def scene_repo(tmp_path):
    db_path = tmp_path / "agent-catalog.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repo = SceneRepository(session_factory)
        yield repo
    finally:
        await close_engine()


@pytest.fixture
async def catalog_repos(tmp_path):
    db_path = tmp_path / "agent-catalog-source.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        yield {
            "base": BaseConfigRepository(session_factory),
            "scene": SceneRepository(session_factory),
            "http": HttpSourceRepository(session_factory),
            "sql": SqlSourceRepository(session_factory),
        }
    finally:
        await close_engine()


@pytest.fixture
async def datagen_client(tmp_path):
    db_path = tmp_path / "agent-catalog-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_search_scene_contracts_scores_published_semantic_match(scene_repo: SceneRepository):
    await _publish_scene(scene_repo, _order_scene("createPaidOrder"))
    await scene_repo.create_scene(_inventory_scene("draftInventory"))
    service = AgentCatalogService(scene_repo)

    result = await service.search_scene_contracts(
        AgentSceneSearchRequest(
            goal="帮我造一笔已支付订单",
            userInputs={"buyerId": "U1"},
            visibleVariables=[],
        )
    )

    assert result.queryTerms
    assert [item.contract.sceneCode for item in result.candidates] == ["createPaidOrder"]
    candidate = result.candidates[0]
    assert candidate.score > 0.5
    assert candidate.missingInputs == []
    assert candidate.requiresConfirmation is True
    assert any("能力类型匹配" in reason for reason in candidate.reasons)


@pytest.mark.anyio
async def test_search_scene_contracts_reports_missing_inputs(scene_repo: SceneRepository):
    await _publish_scene(scene_repo, _order_scene("createPaidOrder"))
    service = AgentCatalogService(scene_repo)

    result = await service.search_scene_contracts(
        AgentSceneSearchRequest(goal="创建订单", userInputs={}, visibleVariables=[])
    )

    assert result.candidates[0].missingInputs == ["userId"]


@pytest.mark.anyio
async def test_search_source_contracts_scores_http_source_semantic_match(catalog_repos):
    await catalog_repos["http"].upsert_http_source(_order_http_source("createOrderApi"))
    service = AgentCatalogService(
        catalog_repos["scene"],
        http_source_repository=catalog_repos["http"],
        sql_source_repository=catalog_repos["sql"],
    )

    result = await service.search_source_contracts(
        AgentSourceSearchRequest(
            goal="帮我造一笔订单",
            userInputs={"buyerId": "U1"},
            visibleVariables=[],
        )
    )

    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.contract.sourceType == "HTTP"
    assert candidate.contract.sourceCode == "createOrderApi"
    assert candidate.contract.hasSideEffects is True
    assert candidate.missingInputs == []
    assert candidate.requiresConfirmation is True
    assert any("能力类型匹配" in reason for reason in candidate.reasons)


@pytest.mark.anyio
async def test_resolve_infra_basis_reports_ready_http_basis(catalog_repos):
    await catalog_repos["base"].upsert_system(SysConfig(sysCode="TRADE", sysName="交易系统"))
    await catalog_repos["base"].upsert_environment(EnvironmentConfig(envCode="DEV", envName="开发环境"))
    await catalog_repos["base"].create_service_endpoint(
        ServiceEndpointConfig(envCode="DEV", sysCode="TRADE", baseUrl="http://trade-dev.example")
    )
    service = AgentCatalogService(
        catalog_repos["scene"],
        http_source_repository=catalog_repos["http"],
        sql_source_repository=catalog_repos["sql"],
        base_repository=catalog_repos["base"],
    )

    result = await service.resolve_infra_basis(
        AgentInfraResolveRequest(query="交易订单", envCode="DEV", sysCode="TRADE", resourceType="HTTP")
    )

    assert result.ready is True
    assert result.missingFields == []
    assert result.matchedSystems[0]["sysCode"] == "TRADE"
    assert result.matchedServiceEndpoints[0]["baseUrl"] == "http://trade-dev.example"


@pytest.mark.anyio
async def test_agent_catalog_api_search_and_contract(datagen_client: AsyncClient):
    create = await datagen_client.post(
        "/api/v1/datagen/scenes",
        json=_order_scene("apiCreateOrder").model_dump(mode="json"),
    )
    assert create.status_code == 200, create.text
    publish = await datagen_client.post("/api/v1/datagen/scenes/apiCreateOrder/publish")
    assert publish.status_code == 200, publish.text

    search = await datagen_client.post(
        "/api/v1/datagen/agent/catalog/scenes/search",
        json={"goal": "造订单", "userInputs": {"buyerId": "U1"}},
    )
    assert search.status_code == 200, search.text
    assert search.json()["candidates"][0]["contract"]["sceneCode"] == "apiCreateOrder"

    contract = await datagen_client.get("/api/v1/datagen/agent/catalog/scenes/apiCreateOrder/contract")
    assert contract.status_code == 200, contract.text
    assert contract.json()["hasSideEffects"] is True


@pytest.mark.anyio
async def test_agent_catalog_api_resolve_infra(datagen_client: AsyncClient):
    assert (await datagen_client.post("/api/v1/datagen/systems", json=SysConfig(sysCode="TRADE", sysName="交易系统").model_dump(mode="json"))).status_code == 200
    assert (
        await datagen_client.post(
            "/api/v1/datagen/environments",
            json=EnvironmentConfig(envCode="DEV", envName="开发环境").model_dump(mode="json"),
        )
    ).status_code == 200
    assert (
        await datagen_client.post(
            "/api/v1/datagen/service-endpoints",
            json=ServiceEndpointConfig(envCode="DEV", sysCode="TRADE", baseUrl="http://trade-dev.example").model_dump(mode="json"),
        )
    ).status_code == 200

    response = await datagen_client.post(
        "/api/v1/datagen/agent/catalog/infra/resolve",
        json={"query": "交易订单", "envCode": "DEV", "sysCode": "TRADE", "resourceType": "HTTP"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    assert body["missingFields"] == []
    assert body["matchedSystems"][0]["sysCode"] == "TRADE"


def test_agent_catalog_routes_only_use_get_and_post():
    route_methods = {
        method
        for route in router.routes
        if hasattr(route, "path") and str(route.path).startswith("/api/v1/datagen/agent/catalog")
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert route_methods == {"GET", "POST"}


async def _publish_scene(repo: SceneRepository, scene: SceneDefinition) -> None:
    await repo.create_scene(scene)
    await repo.publish_scene(scene.sceneCode, validation_result=ValidationResult(valid=True, issues=[]))


def _order_scene(scene_code: str) -> SceneDefinition:
    return SceneDefinition(
        sceneCode=scene_code,
        sceneName="创建已支付订单",
        sceneRemark="创建一笔测试订单并完成支付，返回订单号。",
        tags=["订单", "支付"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            {
                "effectType": "CREATE_ORDER",
                "target": "orders",
                "description": "创建一笔测试订单。",
            }
        ],
        agentDescription="用于造一笔已支付订单，产出订单号和订单状态。",
        inputSchema=[
            InputFieldDefinition(
                name="env",
                label="环境",
                type=InputFieldType.STRING,
                required=True,
            ),
            InputFieldDefinition(
                name="userId",
                label="用户",
                type=InputFieldType.STRING,
                required=True,
                semanticType="USER_ID",
                aliases=["buyerId"],
            ),
        ],
        resultSchema=[
            InputFieldDefinition(
                name="orderId",
                label="订单号",
                type=InputFieldType.STRING,
                semanticType="ORDER_ID",
                aliases=["orderNo"],
            )
        ],
        steps=[
            HttpStepDefinition(
                stepId="createOrder",
                stepName="创建订单",
                type="HTTP",
                sysCode="TRADE",
                method=HttpMethod.POST,
                path="/orders",
                requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
                outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
            )
        ],
        resultMapping={"orderId": "${steps.createOrder.outputs.orderId}"},
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )


def _inventory_scene(scene_code: str) -> SceneDefinition:
    scene = _order_scene(scene_code)
    scene.sceneName = "查询库存"
    scene.sceneRemark = "查询商品库存。"
    scene.tags = ["库存"]
    scene.capabilityType = CapabilityType.QUERY
    scene.businessDomain = "库存"
    scene.sideEffects = []
    scene.agentDescription = "查询商品库存数量。"
    return scene


def _order_http_source(source_code: str) -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode=source_code,
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
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        outputMeta={"orderId": {"label": "订单号", "remark": "创建后的订单号。", "semanticType": "ORDER_ID"}},
        status=ConfigStatus.ENABLED,
    )
