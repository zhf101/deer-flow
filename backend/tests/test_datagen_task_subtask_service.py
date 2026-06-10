"""造数子任务服务测试。"""

from __future__ import annotations

import pytest

from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskRunCreateRequest,
    DatagenTaskSubagentType,
    DatagenTaskSubtaskCreateRequest,
    DatagenTaskSubtaskIdRequest,
    DatagenTaskSubtaskUpdateRequest,
)
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_repository import DatagenTaskSubtaskRepository
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def subtask_services(tmp_path):
    db_path = tmp_path / "datagen-subtask-service.db"
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
async def test_subtask_lifecycle_records_task_events(subtask_services):
    task_service, subtask_service = subtask_services
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="分析订单造数方案"))

    created = await subtask_service.create_subtask(
        task.taskRunId,
        DatagenTaskSubtaskCreateRequest(
            phase=DatagenTaskPhase.SCENE_DESIGN,
            subagentType=DatagenTaskSubagentType.SOURCE_ANALYSIS_AGENT,
            goal="分析订单 Source 是否足够生成场景。",
            operationId="run_source_analysis_1",
            inputSnapshot={"goal": "订单造数"},
        ),
    )
    assert created.subtaskId.startswith("subtask_")
    assert created.status == "PENDING"

    running = await subtask_service.start_subtask(task.taskRunId, DatagenTaskSubtaskIdRequest(subtaskId=created.subtaskId))
    assert running.status == "RUNNING"
    assert running.startedAt is not None

    completed = await subtask_service.complete_subtask(
        task.taskRunId,
        DatagenTaskSubtaskUpdateRequest(
            subtaskId=created.subtaskId,
            resultSummary={"sourceCount": 2},
            resultPayload={"sources": [{"sourceCode": "createOrderApi"}]},
            resultRef={"refType": "SOURCE_ANALYSIS", "artifactId": "artifact_1"},
            tokenUsage={"totalTokens": 128},
        ),
    )
    assert completed.status == "SUCCESS"
    assert completed.resultSummary == {"sourceCount": 2}
    assert completed.resultPayload["sources"][0]["sourceCode"] == "createOrderApi"
    assert completed.finishedAt is not None

    subtasks = await subtask_service.list_subtasks(task.taskRunId)
    assert [item.subtaskId for item in subtasks] == [created.subtaskId]
    events = await task_service.list_events(task.taskRunId)
    event_types = [event.eventType for event in events]
    assert "SUBTASK_CREATED" in event_types
    assert "SUBTASK_STARTED" in event_types
    assert "SUBTASK_COMPLETED" in event_types


@pytest.mark.anyio
async def test_subtask_failure_records_error(subtask_services):
    task_service, subtask_service = subtask_services
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="校验场景"))
    created = await subtask_service.create_subtask(
        task.taskRunId,
        DatagenTaskSubtaskCreateRequest(
            phase=DatagenTaskPhase.SCENE_DESIGN,
            subagentType=DatagenTaskSubagentType.SCENE_VALIDATION_AGENT,
            goal="校验自动生成场景。",
        ),
    )

    failed = await subtask_service.fail_subtask(
        task.taskRunId,
        DatagenTaskSubtaskUpdateRequest(
            subtaskId=created.subtaskId,
            errorType="VALIDATION_ERROR",
            errorMessage="场景缺少输出映射。",
        ),
    )

    assert failed.status == "FAILED"
    assert failed.errorType == "VALIDATION_ERROR"
    assert failed.errorMessage == "场景缺少输出映射。"
    events = await task_service.list_events(task.taskRunId)
    assert events[-1].eventType == "SUBTASK_FAILED"
