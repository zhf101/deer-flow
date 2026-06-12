"""GDP Agent Runtime API 数据库持久化恢复测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import FakeSceneCatalog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.agent_runtime import api as runtime_api
from app.gdp.agent_runtime import runner as runtime_runner
from app.gdp.agent_runtime.store import Store
from deerflow.persistence.engine import close_engine, init_engine


@pytest.mark.anyio
async def test_agent_runtime_api_hydrates_timeline_after_memory_store_reset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """内存 Store 清空后，API 仍能从数据库恢复 TaskRun 和 timeline。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "runId": "scene-run-1",
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr(runtime_runner, "get_catalog", lambda: FakeSceneCatalog())
    monkeypatch.setattr(runtime_api, "_store", Store())

    db_path = tmp_path / "agent-runtime-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(runtime_api.router, prefix="/api/v1/datagen")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create = await client.post(
                "/api/v1/datagen/agent-runtime/task-runs",
                json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
            )
            assert create.status_code == 200, create.text
            task_run_id = create.json()["task_run_id"]

            start = await client.post(
                f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
                json={"scene_code": "create_paid_order", "inputs": {"buyer_id": "U1"}},
            )
            assert start.status_code == 200, start.text
            assert start.json()["status"] == "COMPLETED"

            monkeypatch.setattr(runtime_api, "_store", Store())

            restored = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}")
            assert restored.status_code == 200, restored.text
            assert restored.json()["status"] == "COMPLETED"

            timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
            assert timeline.status_code == 200, timeline.text
            assert timeline.json()["attempts"][0]["scene_run_id"] == "scene-run-1"
            assert timeline.json()["decisions"][0]["decision_kind"] == "SCENE_SELECTION"

            decisions = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/decisions")
            assert decisions.status_code == 200, decisions.text
            assert decisions.json()[0]["target_id"] == "create_paid_order"
            assert decisions.json()[0]["decision_source"] == "USER"

            payload = await client.get(
                f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/payloads",
                params={"ref": timeline.json()["attempts"][0]["response_ref"]},
            )
            assert payload.status_code == 200, payload.text
            assert payload.json()["payload"]["runId"] == "scene-run-1"

            list_response = await client.get("/api/v1/datagen/agent-runtime/task-runs")
            assert list_response.status_code == 200, list_response.text
            assert [item["task_run_id"] for item in list_response.json()] == [task_run_id]
    finally:
        await close_engine()
