"""GDP Agent 场景设计工具测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.tools.scene_design_tools import publish_scene_from_source, search_source_contracts
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, InputFieldDefinition, InputFieldType
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def design_services(tmp_path):
    db_path = tmp_path / "gdp-scene-design-tools.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        scene_repo = SceneRepository(session_factory)
        http_repo = HttpSourceRepository(session_factory)
        sql_repo = SqlSourceRepository(session_factory)
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        await http_repo.upsert_http_source(_order_http_source())
        yield {
            "scene_repo": scene_repo,
            "http_repo": http_repo,
            "sql_repo": sql_repo,
            "task_service": task_service,
            "scene_service": SceneService(scene_repo),
            "catalog": AgentCatalogService(scene_repo, http_source_repository=http_repo, sql_source_repository=sql_repo),
        }
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_publish_scene_from_http_source_records_task_events(design_services):
    task_run = await design_services["task_service"].create_task_run(
        DatagenTaskRunCreateRequest(userIntent="帮我造一笔订单", inputs={"buyerId": "U1"})
    )
    source_result = await search_source_contracts(
        design_services["catalog"],
        goal=task_run.userIntent,
        user_inputs={"buyerId": "U1"},
    )

    published = await publish_scene_from_source(
        task_service=design_services["task_service"],
        scene_service=design_services["scene_service"],
        http_source_repository=design_services["http_repo"],
        sql_source_repository=design_services["sql_repo"],
        task_run_id=task_run.taskRunId,
        goal=task_run.userIntent,
        source_contract=source_result["candidates"][0]["contract"],
    )

    assert published["sceneCode"].startswith("agent_createOrderApi_")
    scene = await design_services["scene_repo"].get_published_scene(published["sceneCode"])
    assert scene.definition.steps[0].templateRef.sourceCode == "createOrderApi"
    assert scene.definition.resultMapping == {"orderId": "${steps.createOrderApi.outputs.orderId}"}
    task = await design_services["task_service"].get_task_run(task_run.taskRunId)
    assert task.phase == "SCENE_FULFILLMENT"
    steps = await design_services["task_service"].list_steps(task_run.taskRunId)
    design_steps = [step for step in steps if step.stepType == "DESIGN_SCENE"]
    assert design_steps[0].selectedResource["source"]["sourceCode"] == "createOrderApi"
    assert design_steps[0].output["sceneCode"] == published["sceneCode"]
    events = await design_services["task_service"].list_events(task_run.taskRunId)
    event_types = [event.eventType for event in events]
    assert "SCENE_DRAFT_COMPOSED" in event_types
    assert "SCENE_AUTO_PUBLISHED" in event_types


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
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        outputMeta={"orderId": {"label": "订单号", "remark": "创建后的订单号。", "semanticType": "ORDER_ID"}},
        status=ConfigStatus.ENABLED,
    )
