"""GDP Task Agent 最小端到端闭环测试。"""

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


@pytest.mark.anyio
async def test_gdp_task_agent_minimal_e2e_with_existing_write_scene(tmp_path):
    db_path = tmp_path / "gdp-task-agent-e2e.db"
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
        await scene_repo.create_scene(_paid_order_scene())
        await scene_repo.publish_scene("createPaidOrder", validation_result=ValidationResult(valid=True, issues=[]))
        graph = make_gdp_graph(
            GDPAgentServices(
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
            checkpointer=MemorySaver(),
        )
        config = {"configurable": {"thread_id": "thread-gdp-e2e"}}

        first_chunks = [
            chunk
            async for chunk in graph.astream(
                {"messages": [HumanMessage(content="帮我造一笔已支付订单")]},
                config=config,
                stream_mode="values",
            )
        ]

        assert "__interrupt__" in first_chunks[-1]
        waiting = (await task_service.list_task_runs(status=DatagenTaskStatus.WAITING_USER))[0]
        assert waiting.envCode == "DEV"
        assert waiting.envSource == "SYSTEM_DEFAULT"
        assert waiting.pendingInterrupts["details"]["sceneCode"] == "createPaidOrder"

        final_chunks = [
            chunk
            async for chunk in graph.astream(
                Command(resume={"approved": True}),
                config=config,
                stream_mode="values",
            )
        ]

        assert final_chunks[-1]["current_phase"] == "COMPLETED"
        completed = (await task_service.list_task_runs(status=DatagenTaskStatus.COMPLETED))[0]
        assert completed.finalSummary == "造数任务已完成。执行场景 createPaidOrder，场景运行记录 scene_run_paid_order。"
        steps = await task_service.list_steps(completed.taskRunId)
        ask_steps = [step for step in steps if step.stepType == "ASK_USER"]
        scene_steps = [step for step in steps if step.stepType == "RUN_SCENE"]
        reflect_steps = [step for step in steps if step.stepType == "REFLECT"]
        assert ask_steps[0].selectedResource["questionType"] == "WRITE_SCENE_APPROVAL"
        assert scene_steps[0].selectedResource["sceneCode"] == "createPaidOrder"
        assert scene_steps[0].sceneRunId == "scene_run_paid_order"
        assert reflect_steps[0].sceneRunId == "scene_run_paid_order"
        events = await task_service.list_events(completed.taskRunId)
        event_types = [event.eventType for event in events]
        assert event_types[:2] == ["TASK_CREATED", "DEFAULT_ENV_SELECTED"]
        assert "SCENE_CANDIDATES_FOUND" in event_types
        assert "ASK_USER" in event_types
        assert "SCENE_RUN_FINISHED" in event_types
        assert "TASK_COMPLETED" in event_types
        assert event_types.index("SCENE_RUN_FINISHED") < event_types.index("TASK_COMPLETED")
        assert event_types[-1] == "AGENT_NODE_FINISHED"
    finally:
        await close_engine()


class _FakeSceneService:
    async def run_scene(self, request: SceneRunRequest) -> SceneExecutionResult:
        now = datetime.now(UTC)
        return SceneExecutionResult(
            runId="scene_run_paid_order",
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
                    stepId="createPaidOrder",
                    stepName="创建已支付订单",
                    type=StepType.HTTP,
                    status="SUCCESS",
                    startedAt=now,
                    finishedAt=now,
                    durationMs=1,
                    outputs={"orderId": "O1", "orderStatus": "PAID"},
                )
            ],
            finalOutput={"orderId": "O1", "orderStatus": "PAID"},
            errors=[],
        )


def _paid_order_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="createPaidOrder",
        sceneName="创建已支付订单",
        sceneRemark="创建一笔已支付测试订单并返回订单号和订单状态。",
        tags=["订单", "支付", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[{"effectType": "CREATE_PAID_ORDER", "target": "orders"}],
        agentDescription="创建一笔已支付测试订单，返回订单号和支付状态。",
        inputSchema=[
            InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING),
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
                stepId="createPaidOrder",
                stepName="创建已支付订单",
                type=StepType.HTTP,
                sysCode="TRADE",
                method=HttpMethod.POST,
                path="/orders/paid",
                outputMapping={
                    "orderId": "${RES_BODY(data.orderId)}",
                    "orderStatus": "${RES_BODY(data.orderStatus)}",
                },
            )
        ],
        resultMapping={
            "orderId": "${steps.createPaidOrder.outputs.orderId}",
            "orderStatus": "${steps.createPaidOrder.outputs.orderStatus}",
        },
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )
