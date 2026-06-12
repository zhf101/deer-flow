"""GDP Agent Runtime API 专项测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.agent_runtime import api as runtime_api
from app.gdp.agent_runtime.store import Store


def _make_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(runtime_api, "_store", Store())
    app = FastAPI()
    app.include_router(runtime_api.router, prefix="/api/v1/datagen")
    return app


@pytest.mark.anyio
async def test_api_reply_confirm_unknown_state_stops_without_replay(monkeypatch: pytest.MonkeyPatch):
    """确认未知结果后不重放写请求，也不能停在 RUNNING。"""
    call_count = 0

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal call_count
        call_count += 1
        raise TimeoutError("timeout")

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]

        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "create_paid_order", "inputs": {"buyer_id": "U1"}},
        )
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "WAITING_USER"

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "CONFIRM_UNKNOWN_STATE", "payload": {"message": "人工确认不重试"}},
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "FAILED"
        assert "避免重复写请求" in reply.json()["failure_reason"]

        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        assert len(timeline.json()["attempts"]) == 1
        assert call_count == 1


@pytest.mark.anyio
async def test_api_reply_rejects_unknown_reply_type(monkeypatch: pytest.MonkeyPatch):
    """reply_type 必须被校验，不能任意字符串无脑放行。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        raise TimeoutError("timeout")

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "create_paid_order", "inputs": {"buyer_id": "U1"}},
        )

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "UNKNOWN_REPLY", "payload": {}},
        )

    assert reply.status_code == 422


@pytest.mark.anyio
async def test_api_reply_supply_input_resumes_preflight_gap_without_prior_write(monkeypatch: pytest.MonkeyPatch):
    """尚未发起写请求的缺信息任务，可补输入后恢复执行。"""
    call_count = 0

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal call_count
        call_count += 1
        assert env_code == "SIT1"
        assert inputs == {"buyer_id": "U1"}
        return {
            "status": "SUCCESS",
            "finalOutput": {
                "order_id": "ORDER-1",
                "pay_status": "PAID",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": None},
        )
        task_run_id = create.json()["task_run_id"]

        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "create_paid_order", "inputs": {}},
        )
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "WAITING_USER"

        before_reply = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        assert before_reply.json()["attempts"] == []

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={
                "reply_type": "SUPPLY_INPUT",
                "payload": {"env_code": "SIT1", "inputs": {"buyer_id": "U1"}},
            },
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "COMPLETED"

        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        assert len(timeline.json()["attempts"]) == 1
        assert call_count == 1


@pytest.mark.anyio
async def test_api_cancel_created_task_and_reject_terminal_cancel(monkeypatch: pytest.MonkeyPatch):
    """取消接口覆盖 CREATED 和终态不可回退。"""
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]

        cancel = await client.post(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/cancel")
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["status"] == "CANCELLED"

        cancel_again = await client.post(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/cancel")
        assert cancel_again.status_code == 409

