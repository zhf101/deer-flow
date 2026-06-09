"""GDP Agent 业务图测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import signature

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.gdp.agent.graph import GDPAgentServices, make_gdp_agent, make_gdp_graph
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.base.models import EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import (
    CapabilitySideEffect,
    CapabilityType,
    ConfigStatus,
    HttpMethod,
    InputFieldDefinition,
    InputFieldType,
    SceneStatus,
    StepType,
)
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.models import (
    BatchConfig,
    HttpStepDefinition,
    SceneDefinition,
    SceneExecutionResult,
    SceneRunRequest,
    StepExecutionResult,
    ValidationResult,
)
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.config.task.models import DatagenTaskStatus
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def gdp_services(tmp_path):
    db_path = tmp_path / "gdp-agent-graph.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        scene_repo = SceneRepository(session_factory)
        base_repo = BaseConfigRepository(session_factory)
        http_repo = HttpSourceRepository(session_factory)
        sql_repo = SqlSourceRepository(session_factory)
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        http_service = HttpSourceService(http_repo, base_repo)
        sql_service = SqlSourceService(sql_repo, base_repo)
        sql_execution = SqlExecutionService(
            base_repository=base_repo,
            sql_source_repository=sql_repo,
            registry=SqlExecutorRegistry(),
        )
        yield {
            "scene_repo": scene_repo,
            "base_repo": base_repo,
            "http_repo": http_repo,
            "sql_repo": sql_repo,
            "task_service": task_service,
            "services": GDPAgentServices(
                task_service=task_service,
                catalog_service=AgentCatalogService(scene_repo, http_source_repository=http_repo, sql_source_repository=sql_repo),
                scene_service=_FakeSceneService(scene_repo),
                base_repository=base_repo,
                http_source_repository=http_repo,
                sql_source_repository=sql_repo,
                http_source_service=http_service,
                sql_source_service=sql_service,
                sql_execution_service=sql_execution,
            ),
        }
    finally:
        await close_engine()


def test_make_gdp_agent_accepts_app_config_signature():
    params = signature(make_gdp_agent).parameters

    assert "config" in params
    assert "app_config" in params


@pytest.mark.anyio
async def test_gdp_graph_asks_for_source_config_when_no_scene_and_no_source(gdp_services):
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())

    chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="帮我造一笔已支付订单")]},
            config={"configurable": {"thread_id": "thread-gdp-missing"}},
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in chunks[-1]
    task_runs = await gdp_services["task_service"].list_task_runs()
    assert task_runs[0].deerflowThreadId == "thread-gdp-missing"
    assert task_runs[0].phase == "WAITING_USER"
    assert task_runs[0].pendingInterrupts["questionType"] == "SOURCE_CONFIG_REQUIRED"
    events = await gdp_services["task_service"].list_events(task_runs[0].taskRunId)
    assert [event.eventNo for event in events] == list(range(1, len(events) + 1))
    resource_missing_events = [event for event in events if event.eventType == "RESOURCE_MISSING"]
    assert [event.payload["resourceType"] for event in resource_missing_events] == ["SCENE", "SOURCE"]


@pytest.mark.anyio
async def test_gdp_graph_extracts_env_hint_from_user_intent(gdp_services):
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())

    chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="帮我在测试服造一笔订单")]},
            config={"configurable": {"thread_id": "thread-gdp-env-hint"}},
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in chunks[-1]
    task_runs = await gdp_services["task_service"].list_task_runs()
    assert task_runs[0].envCode == "TEST"
    assert task_runs[0].envSource == "USER_EXPLICIT"
    events = await gdp_services["task_service"].list_events(task_runs[0].taskRunId)
    assert "DEFAULT_ENV_SELECTED" not in [event.eventType for event in events]


@pytest.mark.anyio
async def test_gdp_graph_runs_query_scene_and_completes_task(gdp_services):
    await gdp_services["scene_repo"].create_scene(_query_scene())
    await gdp_services["scene_repo"].publish_scene("queryOrder", validation_result=ValidationResult(valid=True, issues=[]))
    graph = make_gdp_graph(gdp_services["services"])

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="查询订单")]},
        config={"configurable": {"thread_id": "thread-gdp-success"}},
    )

    assert result["current_phase"] == "COMPLETED"
    task_runs = await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.COMPLETED)
    assert len(task_runs) == 1
    steps = await gdp_services["task_service"].list_steps(task_runs[0].taskRunId)
    scene_steps = _steps_by_type(steps, "RUN_SCENE")
    assert scene_steps[0].sceneRunId == "scene_run_query_order"
    assert _steps_by_type(steps, "REFLECT")
    events = await gdp_services["task_service"].list_events(task_runs[0].taskRunId)
    assert "SCENE_RUN_STARTED" in [event.eventType for event in events]
    assert "TASK_COMPLETED" in [event.eventType for event in events]


@pytest.mark.anyio
async def test_gdp_graph_asks_user_to_choose_ambiguous_scene_candidate(gdp_services):
    scene_a = _query_scene()
    scene_a.sceneCode = "queryOrderA"
    scene_b = _query_scene()
    scene_b.sceneCode = "queryOrderB"
    await gdp_services["scene_repo"].create_scene(scene_a)
    await gdp_services["scene_repo"].publish_scene("queryOrderA", validation_result=ValidationResult(valid=True, issues=[]))
    await gdp_services["scene_repo"].create_scene(scene_b)
    await gdp_services["scene_repo"].publish_scene("queryOrderB", validation_result=ValidationResult(valid=True, issues=[]))
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "thread-gdp-scene-choice"}}

    first_chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="查询订单")]},
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in first_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    assert waiting.pendingInterrupts["questionType"] == "SCENE_CANDIDATE_CONFIRM"
    assert waiting.pendingInterrupts["details"]["selectionKey"] == "selectedSceneCode"
    assert waiting.pendingInterrupts["details"]["confirmationReason"] == "SAME_SCORE"
    assert waiting.pendingInterrupts["details"]["recommended"] in {"queryOrderA", "queryOrderB"}
    assert {item["sceneCode"] for item in waiting.pendingInterrupts["details"]["candidates"]} == {
        "queryOrderA",
        "queryOrderB",
    }
    assert all("capabilityType" in item for item in waiting.pendingInterrupts["details"]["candidates"])

    final_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(resume={"selectedSceneCode": "queryOrderB"}),
            config=config,
            stream_mode="values",
        )
    ]

    assert final_chunks[-1]["current_phase"] == "COMPLETED"
    completed = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.COMPLETED))[0]
    scene_steps = _steps_by_type(await gdp_services["task_service"].list_steps(completed.taskRunId), "RUN_SCENE")
    assert scene_steps[0].selectedResource["sceneCode"] == "queryOrderB"


@pytest.mark.anyio
async def test_gdp_graph_asks_user_to_choose_close_score_scene_candidate(gdp_services):
    primary = _query_scene()
    primary.sceneCode = "queryOrderPrimary"
    primary.sideEffects = [CapabilitySideEffect(effectType="QUERY_ORDER_AUDIT", target="orders")]
    secondary = _query_scene()
    secondary.sceneCode = "queryOrderSecondary"
    await gdp_services["scene_repo"].create_scene(primary)
    await gdp_services["scene_repo"].publish_scene("queryOrderPrimary", validation_result=ValidationResult(valid=True, issues=[]))
    await gdp_services["scene_repo"].create_scene(secondary)
    await gdp_services["scene_repo"].publish_scene("queryOrderSecondary", validation_result=ValidationResult(valid=True, issues=[]))
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())

    chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="查询订单")]},
            config={"configurable": {"thread_id": "thread-gdp-close-scene-choice"}},
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    assert waiting.pendingInterrupts["questionType"] == "SCENE_CANDIDATE_CONFIRM"
    assert waiting.pendingInterrupts["details"]["confirmationReason"] == "CLOSE_SCORE"
    assert waiting.pendingInterrupts["details"]["recommended"] == "queryOrderPrimary"


@pytest.mark.anyio
async def test_gdp_graph_loops_across_existing_scenes_until_goal_completed(gdp_services):
    await gdp_services["scene_repo"].create_scene(_create_order_scene())
    await gdp_services["scene_repo"].publish_scene("createOrder", validation_result=ValidationResult(valid=True, issues=[]))
    await gdp_services["scene_repo"].create_scene(_pay_order_scene())
    await gdp_services["scene_repo"].publish_scene("payOrder", validation_result=ValidationResult(valid=True, issues=[]))
    graph = make_gdp_graph(gdp_services["services"])

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="帮我造一笔已支付订单")]},
        config={"configurable": {"thread_id": "thread-gdp-loop"}},
    )

    assert result["current_phase"] == "COMPLETED"
    task_runs = await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.COMPLETED)
    assert len(task_runs) == 1
    steps = await gdp_services["task_service"].list_steps(task_runs[0].taskRunId)
    scene_steps = _steps_by_type(steps, "RUN_SCENE")
    assert [step.selectedResource["sceneCode"] for step in scene_steps] == ["createOrder", "payOrder"]
    assert scene_steps[0].output == {"orderId": "O1"}
    assert scene_steps[1].output == {"orderId": "O1", "orderStatus": "PAID"}
    assert len(_steps_by_type(steps, "REFLECT")) == 2
    task = await gdp_services["task_service"].get_task_run(task_runs[0].taskRunId)
    assert {item.name: item.valuePreview for item in task.visibleVariables}["orderStatus"] == "PAID"
    events = await gdp_services["task_service"].list_events(task_runs[0].taskRunId)
    assert [event.eventType for event in events].count("TASK_REFLECTED") == 1
    assert [event.eventType for event in events].count("SCENE_RUN_FINISHED") == 2


@pytest.mark.anyio
async def test_gdp_graph_designs_scene_from_http_source_then_resumes_execution(gdp_services):
    await gdp_services["http_repo"].upsert_http_source(_order_http_source())
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "thread-gdp-design"}}

    first_chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="帮我造一笔订单")]},
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in first_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    generated_scene_code = waiting.pendingInterrupts["details"]["sceneCode"]
    assert generated_scene_code.startswith("agent_createOrderApi_")
    events = await gdp_services["task_service"].list_events(waiting.taskRunId)
    event_types = [event.eventType for event in events]
    assert "SOURCE_CANDIDATES_FOUND" in event_types
    assert "SCENE_AUTO_PUBLISHED" in event_types

    final_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(resume={"approved": True}),
            config=config,
            stream_mode="values",
        )
    ]

    assert final_chunks[-1]["current_phase"] == "COMPLETED"
    completed = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.COMPLETED))[0]
    steps = await gdp_services["task_service"].list_steps(completed.taskRunId)
    scene_steps = _steps_by_type(steps, "RUN_SCENE")
    assert scene_steps[0].selectedResource["sceneCode"] == generated_scene_code
    assert _steps_by_type(steps, "DESIGN_SCENE")
    assert _steps_by_type(steps, "ASK_USER")
    published = await gdp_services["scene_repo"].get_published_scene(generated_scene_code)
    assert published.definition.steps[0].templateRef.sourceCode == "createOrderApi"


@pytest.mark.anyio
async def test_gdp_graph_asks_user_to_choose_ambiguous_source_candidate(gdp_services):
    await gdp_services["http_repo"].upsert_http_source(_order_http_source("createOrderApi"))
    await gdp_services["http_repo"].upsert_http_source(_order_http_source("createOrderApiV2"))
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "thread-gdp-source-choice"}}

    first_chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="帮我造一笔订单")]},
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in first_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    assert waiting.pendingInterrupts["questionType"] == "SOURCE_CANDIDATE_CONFIRM"
    assert waiting.pendingInterrupts["details"]["selectionKey"] == "selectedSourceCode"
    assert waiting.pendingInterrupts["details"]["confirmationReason"] == "SAME_SCORE"
    assert waiting.pendingInterrupts["details"]["recommended"] in {"createOrderApi", "createOrderApiV2"}
    assert {item["sourceCode"] for item in waiting.pendingInterrupts["details"]["candidates"]} == {
        "createOrderApi",
        "createOrderApiV2",
    }
    assert all("sysCode" in item for item in waiting.pendingInterrupts["details"]["candidates"])

    source_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(resume={"selectedSourceCode": "createOrderApiV2"}),
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in source_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    generated_scene_code = waiting.pendingInterrupts["details"]["sceneCode"]

    final_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(resume={"approved": True}),
            config=config,
            stream_mode="values",
        )
    ]

    assert final_chunks[-1]["current_phase"] == "COMPLETED"
    published = await gdp_services["scene_repo"].get_published_scene(generated_scene_code)
    assert published.definition.steps[0].templateRef.sourceCode == "createOrderApiV2"


@pytest.mark.anyio
async def test_gdp_graph_configures_source_and_infra_then_returns_to_scene_flow(gdp_services):
    graph = make_gdp_graph(gdp_services["services"], checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "thread-gdp-source-infra"}}

    first_chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="帮我造一笔订单")]},
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in first_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    assert waiting.pendingInterrupts["questionType"] == "SOURCE_CONFIG_REQUIRED"

    source_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(
                resume={
                    "sourceType": "HTTP",
                    "config": _order_http_source().model_dump(mode="json"),
                }
            ),
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in source_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    assert waiting.pendingInterrupts["questionType"] == "INFRA_CONFIG_REQUIRED"

    infra_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(
                resume={
                    "infra": {
                        "system": SysConfig(sysCode="TRADE", sysName="交易系统").model_dump(mode="json"),
                        "environment": EnvironmentConfig(envCode="DEV", envName="开发环境").model_dump(mode="json"),
                        "serviceEndpoint": ServiceEndpointConfig(
                            envCode="DEV",
                            sysCode="TRADE",
                            baseUrl="http://trade-dev.example",
                        ).model_dump(mode="json"),
                    }
                }
            ),
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in infra_chunks[-1]
    waiting = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
    assert waiting.pendingInterrupts["questionType"] == "WRITE_SCENE_APPROVAL"
    generated_scene_code = waiting.pendingInterrupts["details"]["sceneCode"]

    final_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(resume={"approved": True}),
            config=config,
            stream_mode="values",
        )
    ]

    assert final_chunks[-1]["current_phase"] == "COMPLETED"
    completed = (await gdp_services["task_service"].list_task_runs(status=DatagenTaskStatus.COMPLETED))[0]
    steps = await gdp_services["task_service"].list_steps(completed.taskRunId)
    scene_steps = _steps_by_type(steps, "RUN_SCENE")
    assert scene_steps[0].selectedResource["sceneCode"] == generated_scene_code
    assert _steps_by_type(steps, "CONFIG_HTTP_SOURCE")
    assert _steps_by_type(steps, "CONFIG_INFRA")
    assert _steps_by_type(steps, "DESIGN_SCENE")
    assert len(_steps_by_type(steps, "ASK_USER")) >= 3
    events = await gdp_services["task_service"].list_events(completed.taskRunId)
    event_types = [event.eventType for event in events]
    assert "SOURCE_INFRA_MISSING" in event_types
    assert "INFRA_CONFIG_SAVED" in event_types
    assert "SOURCE_CONFIG_SAVED" in event_types
    assert "SCENE_AUTO_PUBLISHED" in event_types


def _steps_by_type(steps, step_type: str):
    return [step for step in steps if step.stepType == step_type]


class _FakeSceneService:
    def __init__(self, scene_repo: SceneRepository) -> None:
        self._scene_service = SceneService(scene_repo)

    async def create_scene(self, scene: SceneDefinition, *, operator: str | None = None):
        return await self._scene_service.create_scene(scene, operator=operator)

    async def publish_scene(self, scene_code: str, *, operator: str | None = None):
        return await self._scene_service.publish_scene(scene_code, operator=operator)

    async def run_scene(self, request: SceneRunRequest) -> SceneExecutionResult:
        now = datetime.now(UTC)
        if request.sceneCode == "createOrder":
            return _scene_result(
                request,
                run_id="scene_run_create_order",
                step_id="createOrder",
                step_name="创建订单",
                outputs={"orderId": "O1"},
            )
        if request.sceneCode == "payOrder":
            return _scene_result(
                request,
                run_id="scene_run_pay_order",
                step_id="payOrder",
                step_name="支付订单",
                outputs={"orderId": "O1", "orderStatus": "PAID"},
            )
        return SceneExecutionResult(
            runId="scene_run_query_order",
            sceneCode=request.sceneCode,
            versionNo=1,
            envCode=request.envCode,
            inputs=request.inputs,
            status="SUCCESS",
            startedAt=now,
            finishedAt=now,
            durationMs=1,
            stepResults=[
                StepExecutionResult(
                    stepId="queryOrder",
                    stepName="查询订单",
                    type=StepType.HTTP,
                    status="SUCCESS",
                    startedAt=now,
                    finishedAt=now,
                    durationMs=1,
                    outputs={"orderId": "O1"},
                )
            ],
            finalOutput={"orderId": "O1"},
            errors=[],
        )


def _scene_result(
    request: SceneRunRequest,
    *,
    run_id: str,
    step_id: str,
    step_name: str,
    outputs: dict,
) -> SceneExecutionResult:
    now = datetime.now(UTC)
    return SceneExecutionResult(
        runId=run_id,
        sceneCode=request.sceneCode,
        versionNo=1,
        envCode=request.envCode,
        inputs=request.inputs,
        status="SUCCESS",
        startedAt=now,
        finishedAt=now,
        durationMs=1,
        stepResults=[
            StepExecutionResult(
                stepId=step_id,
                stepName=step_name,
                type=StepType.HTTP,
                status="SUCCESS",
                startedAt=now,
                finishedAt=now,
                durationMs=1,
                outputs=outputs,
            )
        ],
        finalOutput=outputs,
        errors=[],
    )


def _query_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="queryOrder",
        sceneName="查询订单",
        sceneRemark="查询测试订单并返回订单号。",
        tags=["订单", "查询"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="交易",
        agentDescription="查询一笔测试订单，返回订单号。",
        inputSchema=[
            InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING),
        ],
        resultSchema=[
            InputFieldDefinition(
                name="orderId",
                label="订单号",
                type=InputFieldType.STRING,
                semanticType="ORDER_ID",
            )
        ],
        steps=[
            HttpStepDefinition(
                stepId="queryOrder",
                stepName="查询订单",
                type=StepType.HTTP,
                sysCode="TRADE",
                method=HttpMethod.GET,
                path="/orders/latest",
                outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
            )
        ],
        resultMapping={"orderId": "${steps.queryOrder.outputs.orderId}"},
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )


def _create_order_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="createOrder",
        sceneName="创建订单",
        sceneRemark="创建一笔测试订单并返回订单号。",
        tags=["订单", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        agentDescription="创建一笔测试订单，返回订单号。",
        inputSchema=[
            InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING),
        ],
        resultSchema=[
            InputFieldDefinition(
                name="orderId",
                label="订单号",
                type=InputFieldType.STRING,
                semanticType="ORDER_ID",
            )
        ],
        steps=[
            HttpStepDefinition(
                stepId="createOrder",
                stepName="创建订单",
                type=StepType.HTTP,
                sysCode="TRADE",
                method=HttpMethod.POST,
                path="/orders",
                outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
            )
        ],
        resultMapping={"orderId": "${steps.createOrder.outputs.orderId}"},
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )


def _pay_order_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="payOrder",
        sceneName="支付订单",
        sceneRemark="根据订单号完成订单支付，返回订单支付状态。",
        tags=["订单", "支付"],
        capabilityType=CapabilityType.UPDATE,
        businessDomain="交易",
        agentDescription="消费订单号完成支付，返回 PAID 状态。",
        inputSchema=[
            InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING),
            InputFieldDefinition(
                name="orderId",
                label="订单号",
                type=InputFieldType.STRING,
                semanticType="ORDER_ID",
                required=True,
            ),
        ],
        resultSchema=[
            InputFieldDefinition(
                name="orderId",
                label="订单号",
                type=InputFieldType.STRING,
                semanticType="ORDER_ID",
            ),
            InputFieldDefinition(
                name="orderStatus",
                label="订单状态",
                type=InputFieldType.STRING,
                semanticType="ORDER_STATUS",
            ),
        ],
        steps=[
            HttpStepDefinition(
                stepId="payOrder",
                stepName="支付订单",
                type=StepType.HTTP,
                sysCode="TRADE",
                method=HttpMethod.POST,
                path="/orders/pay",
                requestMapping={"bodyMapping": {"orderId": "${input.orderId}"}},
                outputMapping={
                    "orderId": "${RES_BODY(data.orderId)}",
                    "orderStatus": "${RES_BODY(data.orderStatus)}",
                },
            )
        ],
        resultMapping={
            "orderId": "${steps.payOrder.outputs.orderId}",
            "orderStatus": "${steps.payOrder.outputs.orderStatus}",
        },
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )


def _order_http_source(source_code: str = "createOrderApi") -> HttpSourceConfig:
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
                required=False,
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        outputMeta={"orderId": {"label": "订单号", "remark": "创建后的订单号。", "semanticType": "ORDER_ID"}},
        status=ConfigStatus.ENABLED,
    )
