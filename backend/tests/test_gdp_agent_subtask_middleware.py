"""GDP Agent 子任务 middleware 测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.middlewares.subtask import complete_gdp_subtask, create_gdp_subtask, fail_gdp_subtask, start_gdp_subtask
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskRunCreateRequest,
    DatagenTaskSubagentType,
)
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_repository import DatagenTaskSubtaskRepository
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def subtask_middleware_services(tmp_path):
    db_path = tmp_path / "gdp-agent-subtask-middleware.db"
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
async def test_subtask_middleware_returns_lightweight_refs(subtask_middleware_services):
    task_service, subtask_service = subtask_middleware_services
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="拆分 Source 分析"))

    created_ref = await create_gdp_subtask(
        subtask_service,
        task_run_id=task.taskRunId,
        phase=DatagenTaskPhase.SCENE_DESIGN,
        subagent_type=DatagenTaskSubagentType.SOURCE_ANALYSIS_AGENT,
        goal="分析可复用 Source。",
        input_snapshot={"goal": "Source 分析"},
    )
    assert created_ref["ref_type"] == "SUBTASK"
    assert created_ref["status"] == "PENDING"

    running_ref = await start_gdp_subtask(
        subtask_service,
        task_run_id=task.taskRunId,
        subtask_id=created_ref["subtask_id"],
    )
    assert running_ref["status"] == "RUNNING"

    completed_ref = await complete_gdp_subtask(
        subtask_service,
        task_run_id=task.taskRunId,
        subtask_id=created_ref["subtask_id"],
        result_summary={"sourceCount": 2},
        result_payload={"sources": [{"sourceCode": "createOrderApi"}]},
        result_ref={"refType": "SOURCE_ANALYSIS", "artifactId": "artifact_1"},
        token_usage={"totalTokens": 128},
    )
    assert completed_ref["status"] == "SUCCESS"
    assert completed_ref["summary"]["resultSummary"] == {"sourceCount": 2}
    assert completed_ref["summary"]["resultRef"]["artifactId"] == "artifact_1"


@pytest.mark.anyio
async def test_subtask_middleware_records_failure_ref(subtask_middleware_services):
    task_service, subtask_service = subtask_middleware_services
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="校验子任务失败"))
    created_ref = await create_gdp_subtask(
        subtask_service,
        task_run_id=task.taskRunId,
        phase=DatagenTaskPhase.SCENE_DESIGN,
        subagent_type=DatagenTaskSubagentType.SCENE_VALIDATION_AGENT,
        goal="校验自动场景。",
    )

    failed_ref = await fail_gdp_subtask(
        subtask_service,
        task_run_id=task.taskRunId,
        subtask_id=created_ref["subtask_id"],
        error_type="VALIDATION_ERROR",
        error_message="缺少输出映射。",
    )

    assert failed_ref["status"] == "FAILED"
    assert failed_ref["summary"]["errorType"] == "VALIDATION_ERROR"
    events = await task_service.list_events(task.taskRunId)
    assert events[-1].eventType == "SUBTASK_FAILED"
