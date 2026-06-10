"""造数任务控制面 API 测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest, DatagenTaskStatus
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.router import router
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def datagen_client(tmp_path):
    db_path = tmp_path / "datagen-task-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_task_run_api_create_get_events_summary_and_cancel(datagen_client: AsyncClient):
    create = await datagen_client.post(
        "/api/v1/datagen/tasks/runs",
        json={"userIntent": "帮我造一笔已支付订单", "inputs": {"count": 1}},
    )
    assert create.status_code == 200, create.text
    task = create.json()
    assert task["taskRunId"].startswith("task_")
    assert task["envCode"] == "DEV"
    assert task["envSource"] == "SYSTEM_DEFAULT"

    detail = await datagen_client.get(f"/api/v1/datagen/tasks/runs/{task['taskRunId']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["userIntent"] == "帮我造一笔已支付订单"

    events = await datagen_client.get(f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/events")
    assert events.status_code == 200, events.text
    assert [event["eventType"] for event in events.json()] == [
        "TASK_CREATED",
        "DEFAULT_ENV_SELECTED",
        "TASK_PLAN_CREATED",
    ]

    reply = await datagen_client.post(
        f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/user-reply",
        json={"reply": {"approved": True}},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["eventType"] == "USER_REPLY"

    summary = await datagen_client.get(f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json()["status"] == "PLANNING"

    cancel = await datagen_client.post(f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"


@pytest.mark.anyio
async def test_continue_bound_task_submits_gdp_agent_run(datagen_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    session_factory = get_session_factory()
    assert session_factory is not None
    service = DatagenTaskService(DatagenTaskRepository(session_factory))
    task = await service.create_task_run(
        DatagenTaskRunCreateRequest(userIntent="继续造订单"),
        deerflow_thread_id="thread-bound-task",
    )
    calls = []

    async def _fake_start_run(body, thread_id, request):
        calls.append({"body": body, "threadId": thread_id, "request": request})

        class _Record:
            run_id = "run_continue_1"

        return _Record()

    monkeypatch.setattr("app.gateway.services.start_run", _fake_start_run)

    response = await datagen_client.post(f"/api/v1/datagen/tasks/runs/{task.taskRunId}/continue")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "已提交 GDP Agent 运行继续推进任务。"
    assert body["taskRun"]["deerflowRunId"] == "run_continue_1"
    assert calls[0]["threadId"] == "thread-bound-task"
    assert calls[0]["body"].assistant_id == "gdp_agent"
    assert calls[0]["body"].input == {"task_run_id": task.taskRunId}
    events = await service.list_events(task.taskRunId)
    assert events[-1].eventType == "CONTINUE_RUN_REQUESTED"


@pytest.mark.anyio
async def test_start_task_run_submits_gdp_agent_run_and_records_events(
    datagen_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    create = await datagen_client.post(
        "/api/v1/datagen/tasks/runs",
        json={"userIntent": "帮我准备登录账号", "inputs": {}},
    )
    assert create.status_code == 200, create.text
    task = create.json()
    calls = []

    async def _fake_start_run(body, thread_id, request):
        calls.append({"body": body, "threadId": thread_id, "request": request})
        return SimpleNamespace(
            run_id="run_start_1",
            thread_id=thread_id,
            assistant_id="gdp_agent",
            status="pending",
            metadata={"task_run_id": task["taskRunId"]},
            kwargs={"input": body.input},
            multitask_strategy="reject",
            created_at="2026-06-10T17:03:38",
            updated_at="2026-06-10T17:03:38",
            total_input_tokens=0,
            total_output_tokens=0,
            total_tokens=0,
            llm_call_count=0,
            lead_agent_tokens=0,
            subagent_tokens=0,
            middleware_tokens=0,
            message_count=0,
        )

    monkeypatch.setattr("app.gateway.services.start_run", _fake_start_run)

    response = await datagen_client.post(
        f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/start",
        json={"threadId": "thread-start-task"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "已提交 GDP Agent 运行。"
    assert body["taskRun"]["deerflowThreadId"] == "thread-start-task"
    assert body["taskRun"]["deerflowRunId"] == "run_start_1"
    assert body["run"]["run_id"] == "run_start_1"
    assert calls[0]["threadId"] == "thread-start-task"
    assert calls[0]["body"].assistant_id == "gdp_agent"
    assert calls[0]["body"].input == {"task_run_id": task["taskRunId"]}
    assert calls[0]["body"].metadata["source"] == "datagen-task-run-start"
    assert calls[0]["body"].stream_mode == ["values", "custom"]

    events = await datagen_client.get(f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/events")
    assert events.status_code == 200, events.text
    event_types = [event["eventType"] for event in events.json()]
    assert event_types[-2:] == ["GDP_AGENT_RUN_REQUESTED", "GDP_AGENT_RUN_SUBMITTED"]


@pytest.mark.anyio
async def test_start_task_run_records_failure_event_when_runtime_rejects(
    datagen_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    create = await datagen_client.post(
        "/api/v1/datagen/tasks/runs",
        json={"userIntent": "帮我准备登录账号", "inputs": {}},
    )
    assert create.status_code == 200, create.text
    task = create.json()

    async def _fake_start_run(_body, _thread_id, _request):
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr("app.gateway.services.start_run", _fake_start_run)

    response = await datagen_client.post(
        f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/start",
        json={"threadId": "thread-start-failed"},
    )

    assert response.status_code == 500, response.text
    assert "提交 GDP Agent 运行失败" in response.json()["detail"]
    events = await datagen_client.get(f"/api/v1/datagen/tasks/runs/{task['taskRunId']}/events")
    assert events.status_code == 200, events.text
    event_types = [event["eventType"] for event in events.json()]
    assert event_types[-2:] == ["GDP_AGENT_RUN_REQUESTED", "GDP_AGENT_RUN_FAILED"]
    assert events.json()[-1]["payload"] == {
        "deerflowThreadId": "thread-start-failed",
        "error": "runtime unavailable",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "terminal_status",
    [DatagenTaskStatus.COMPLETED, DatagenTaskStatus.FAILED, DatagenTaskStatus.CANCELLED],
)
async def test_continue_terminal_bound_task_rejects_without_starting_run(
    datagen_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: DatagenTaskStatus,
):
    session_factory = get_session_factory()
    assert session_factory is not None
    service = DatagenTaskService(DatagenTaskRepository(session_factory))
    task = await service.create_task_run(
        DatagenTaskRunCreateRequest(userIntent="继续已结束任务"),
        deerflow_thread_id="thread-terminal-task",
    )
    if terminal_status == DatagenTaskStatus.COMPLETED:
        await service.mark_completed(task.taskRunId, final_summary="任务已完成。")
    elif terminal_status == DatagenTaskStatus.FAILED:
        await service.fail_task(
            task.taskRunId,
            failure_type="TEST_FAILURE",
            failure_message="任务已失败。",
        )
    else:
        await service.cancel_task(task.taskRunId)
    calls = []

    async def _fake_start_run(body, thread_id, request):
        calls.append({"body": body, "threadId": thread_id, "request": request})

    monkeypatch.setattr("app.gateway.services.start_run", _fake_start_run)

    response = await datagen_client.post(f"/api/v1/datagen/tasks/runs/{task.taskRunId}/continue")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "任务已结束，不能继续推进。"
    assert calls == []
    updated = await service.get_task_run(task.taskRunId)
    assert updated.status == terminal_status
    assert updated.deerflowRunId is None


@pytest.mark.anyio
async def test_task_routes_only_use_get_and_post(datagen_client: AsyncClient):
    route_methods = {
        method
        for route in router.routes
        if hasattr(route, "path") and str(route.path).startswith("/api/v1/datagen/tasks")
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert route_methods == {"GET", "POST"}
