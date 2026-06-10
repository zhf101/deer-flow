"""造数子任务 API 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.router import router
from deerflow.persistence.engine import close_engine, init_engine


@pytest.fixture
async def subtask_client(tmp_path):
    db_path = tmp_path / "datagen-subtask-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_task_subtask_api_lifecycle(subtask_client: AsyncClient):
    task_response = await subtask_client.post(
        "/api/v1/datagen/tasks/runs",
        json={"userIntent": "拆分场景设计子任务"},
    )
    assert task_response.status_code == 200, task_response.text
    task_run_id = task_response.json()["taskRunId"]

    created = await subtask_client.post(
        f"/api/v1/datagen/tasks/runs/{task_run_id}/subtasks",
        json={
            "phase": "SCENE_DESIGN",
            "subagentType": "source-analysis-agent",
            "goal": "分析 Source 能力。",
            "inputSnapshot": {"goal": "设计场景"},
        },
    )
    assert created.status_code == 200, created.text
    subtask = created.json()
    assert subtask["subtaskId"].startswith("subtask_")
    assert subtask["status"] == "PENDING"

    started = await subtask_client.post(
        f"/api/v1/datagen/tasks/runs/{task_run_id}/subtasks/start",
        json={"subtaskId": subtask["subtaskId"]},
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "RUNNING"

    completed = await subtask_client.post(
        f"/api/v1/datagen/tasks/runs/{task_run_id}/subtasks/complete",
        json={
            "subtaskId": subtask["subtaskId"],
            "resultSummary": {"sourceCount": 1},
            "resultRef": {"refType": "SOURCE_ANALYSIS", "artifactId": "artifact_1"},
            "tokenUsage": {"totalTokens": 64},
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "SUCCESS"
    assert completed.json()["resultSummary"] == {"sourceCount": 1}

    listed = await subtask_client.get(f"/api/v1/datagen/tasks/runs/{task_run_id}/subtasks")
    assert listed.status_code == 200, listed.text
    assert [item["subtaskId"] for item in listed.json()] == [subtask["subtaskId"]]

    detail = await subtask_client.get(
        f"/api/v1/datagen/tasks/runs/{task_run_id}/subtasks/{subtask['subtaskId']}"
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["resultRef"]["artifactId"] == "artifact_1"

    events = await subtask_client.get(f"/api/v1/datagen/tasks/runs/{task_run_id}/events")
    assert events.status_code == 200, events.text
    event_types = [event["eventType"] for event in events.json()]
    assert "SUBTASK_CREATED" in event_types
    assert "SUBTASK_STARTED" in event_types
    assert "SUBTASK_COMPLETED" in event_types


@pytest.mark.anyio
async def test_task_subtask_routes_only_use_get_and_post(subtask_client: AsyncClient):
    route_methods = {
        method
        for route in router.routes
        if hasattr(route, "path") and "/subtasks" in str(route.path)
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert route_methods == {"GET", "POST"}
