"""GDP Agent 上下文压缩摘要测试。"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app.gdp.agent.middlewares.context_compression import load_gdp_context_summary
from app.gdp.agent.nodes.intake import build_intake_node
from app.gdp.agent.tools.task_tools import get_datagen_task_state
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskRunCreateRequest,
    DatagenTaskStepStatus,
    DatagenTaskSubagentType,
    DatagenTaskSubtaskCreateRequest,
    DatagenTaskSubtaskUpdateRequest,
)
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_repository import DatagenTaskSubtaskRepository
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def context_summary_services(tmp_path):
    db_path = tmp_path / "gdp-agent-context-summary.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        subtask_service = DatagenTaskSubtaskService(DatagenTaskSubtaskRepository(session_factory), task_service)
        yield task_service, subtask_service
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_context_summary_compresses_task_steps_and_subtasks(context_summary_services):
    task_service, subtask_service = context_summary_services
    task = await task_service.create_task_run(
        DatagenTaskRunCreateRequest(
            userIntent="帮我造一批已支付订单",
            inputs={"userId": "U1"},
        )
    )
    large_output = {
        "orders": [{"orderId": f"O{i}", "status": "PAID"} for i in range(5)],
        "rawText": "X" * 300,
    }
    await task_service.record_scene_step(
        task.taskRunId,
        step_no=1,
        goal="执行创建订单场景。",
        selected_resource={"sceneCode": "createOrder", "envCode": "DEV", "contract": {"sceneCode": "createOrder", "agentDescription": "X" * 300}},
        input_binding={"userId": "U1"},
        output=large_output,
        scene_run_id="scene_run_1",
        status=DatagenTaskStepStatus.SUCCESS,
    )
    subtask = await subtask_service.create_subtask(
        task.taskRunId,
        DatagenTaskSubtaskCreateRequest(
            phase=DatagenTaskPhase.SCENE_DESIGN,
            subagentType=DatagenTaskSubagentType.SOURCE_ANALYSIS_AGENT,
            goal="分析可复用 Source。",
            inputSnapshot={"goal": "Source 分析"},
        ),
    )
    await subtask_service.complete_subtask(
        task.taskRunId,
        DatagenTaskSubtaskUpdateRequest(
            subtaskId=subtask.subtaskId,
            resultSummary={"sourceCount": 2},
            resultPayload={"sources": [{"sourceCode": "createOrderApi", "raw": "Y" * 300}]},
            resultRef={"refType": "SOURCE_ANALYSIS", "artifactId": "artifact_1"},
        ),
    )

    summary = await load_gdp_context_summary(task_service, subtask_service, task.taskRunId)

    assert summary["goalAnchor"]["userIntent"] == "帮我造一批已支付订单"
    assert summary["variableStack"]["items"][0]["valuePreview"] == "U1"
    assert summary["steps"]["statusCounts"] == {"SUCCESS": 1}
    assert summary["steps"]["completed"][0]["outputKeys"] == ["orders", "rawText"]
    assert summary["steps"]["completed"][0]["selectedResource"] == {
        "sceneCode": "createOrder",
        "envCode": "DEV",
        "contract": {"sceneCode": "createOrder"},
    }
    assert "orders" not in summary["steps"]["completed"][0]
    assert summary["subtasks"]["statusCounts"] == {"SUCCESS": 1}
    assert summary["subtasks"]["recent"][0]["resultSummary"] == {"sourceCount": 2}
    assert summary["subtasks"]["recent"][0]["resultRef"]["artifactId"] == "artifact_1"
    assert summary["unfinishedGoals"][0]["source"] == "goalStack"


@pytest.mark.anyio
async def test_intake_injects_context_summary(context_summary_services):
    task_service, subtask_service = context_summary_services
    intake = build_intake_node(task_service, subtask_service=subtask_service)

    result = await intake(
        {"messages": [HumanMessage(content="帮我造一笔订单")], "inputs": {"userId": "U1"}},
        {"configurable": {"thread_id": "thread-context-summary"}},
    )

    assert result["context_summary"]["goalAnchor"]["taskRunId"] == result["task_run_id"]
    assert result["context_summary"]["goalAnchor"]["phase"] == "SCENE_FULFILLMENT"
    assert result["context_summary"]["variableStack"]["items"][0]["valuePreview"] == "U1"
    assert result["context_summary"]["unfinishedGoals"]


@pytest.mark.anyio
async def test_get_datagen_task_state_returns_context_summary(context_summary_services):
    task_service, subtask_service = context_summary_services
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="读取任务摘要"))

    state = await get_datagen_task_state(task_service, task.taskRunId, subtask_service)

    assert state["contextSummary"]["goalAnchor"]["taskRunId"] == task.taskRunId
    assert state["subtaskCount"] == 0
    assert state["contextSummary"]["plan"]["steps"][0]["goal"] == "搜索可复用的已发布造数场景，绑定入参后执行。"
