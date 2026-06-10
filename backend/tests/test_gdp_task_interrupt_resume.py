"""GDP Task Agent 中断恢复测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.gdp.agent.graph import GDPAgentServices, make_gdp_graph
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import CapabilityType, HttpMethod, InputFieldDefinition, InputFieldType, SceneStatus, StepType
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
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.config.task.models import DatagenTaskStatus
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def interrupt_services(tmp_path):
    db_path = tmp_path / "gdp-task-interrupt.db"
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
        await scene_repo.create_scene(_write_scene())
        await scene_repo.publish_scene("createOrder", validation_result=ValidationResult(valid=True, issues=[]))
        yield {
            "task_service": task_service,
            "services": GDPAgentServices(
                task_service=task_service,
                catalog_service=AgentCatalogService(scene_repo, http_source_repository=http_repo, sql_source_repository=sql_repo),
                scene_service=_FakeSceneService(),
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


@pytest.mark.anyio
async def test_gdp_task_write_scene_interrupts_and_resumes(interrupt_services):
    graph = make_gdp_graph(interrupt_services["services"], checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "thread-gdp-interrupt"}}

    first_chunks = [
        chunk
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content="帮我造一笔订单")]},
            config=config,
            stream_mode="values",
        )
    ]

    assert "__interrupt__" in first_chunks[-1]
    task_runs = await interrupt_services["task_service"].list_task_runs(status=DatagenTaskStatus.WAITING_USER)
    assert len(task_runs) == 1
    assert task_runs[0].pendingInterrupts["questionType"] == "WRITE_SCENE_APPROVAL"

    final_chunks = [
        chunk
        async for chunk in graph.astream(
            Command(resume={"approved": True}),
            config=config,
            stream_mode="values",
        )
    ]

    assert final_chunks[-1]["current_phase"] == "COMPLETED"
    assert final_chunks[-1].get("pending_confirmation") is None
    assert final_chunks[-1]["decision_context"]["selectedSceneCode"] == "createOrder"
    scene_result = final_chunks[-1]["decision_context"]["lastSceneResult"]
    assert scene_result["sceneRunId"] == "scene_run_create_order"
    assert "finalOutput" not in scene_result
    assert scene_result["finalOutputPreview"] == {"orderId": "O1"}
    assert final_chunks[-1]["last_result_ref"]["summary"]["outputKeys"] == ["orderId"]
    assert final_chunks[-1]["last_result_ref"]["ref_type"] == "SCENE_RUN"
    assert final_chunks[-1]["last_result_ref"]["scene_run_id"] == "scene_run_create_order"
    completed = await interrupt_services["task_service"].list_task_runs(status=DatagenTaskStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].pendingInterrupts is None
    steps = await interrupt_services["task_service"].list_steps(completed[0].taskRunId)
    ask_steps = [step for step in steps if step.stepType == "ASK_USER"]
    scene_steps = [step for step in steps if step.stepType == "RUN_SCENE"]
    assert ask_steps[0].status == "WAITING_USER"
    assert scene_steps[0].sceneRunId == "scene_run_create_order"
    events = await interrupt_services["task_service"].list_events(completed[0].taskRunId)
    event_types = [event.eventType for event in events]
    assert "ASK_USER" in event_types
    assert "USER_CONFIRMATION_RESUMED" in event_types
    assert "SCENE_RUN_STARTED" in event_types
    assert "TASK_COMPLETED" in event_types


class _FakeSceneService:
    async def run_scene(self, request: SceneRunRequest) -> SceneExecutionResult:
        now = datetime.now(UTC)
        return SceneExecutionResult(
            runId="scene_run_create_order",
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
                    stepId="createOrder",
                    stepName="创建订单",
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


def _write_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="createOrder",
        sceneName="创建订单",
        sceneRemark="创建一笔测试订单并返回订单号。",
        tags=["订单", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[{"effectType": "CREATE_ORDER", "target": "orders"}],
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
