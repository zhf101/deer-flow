"""GDP Agent Runtime API 专项测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.agent_runtime import api as runtime_api
from app.gdp.agent_runtime import runner as runtime_runner
from app.gdp.agent_runtime.store import Store

from _agent_runtime_catalog_fakes import FakeSceneCatalog, make_candidate


def _make_app(monkeypatch: pytest.MonkeyPatch, *, catalog: FakeSceneCatalog | None = None) -> FastAPI:
    monkeypatch.setattr(runtime_api, "_store", Store())
    # 显式 scene_code 路径现在契约驱动，需注入假 Catalog，避免触达真实持久化。
    fake = catalog or FakeSceneCatalog()
    monkeypatch.setattr(runtime_runner, "get_catalog", lambda: fake)
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


@pytest.mark.anyio
async def test_api_start_allows_missing_scene_code_and_auto_selects(monkeypatch: pytest.MonkeyPatch):
    """第二阶段 start 允许不传 scene_code，由 Catalog 自动选定。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "create_paid_order"
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch, catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order")]))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_api_reply_select_scene_rejects_scene_outside_candidates(monkeypatch: pytest.MonkeyPatch):
    """SELECT_SCENE 只能选择最近候选内的 scene_code。"""
    app = _make_app(
        monkeypatch,
        catalog=FakeSceneCatalog(
            candidates=[make_candidate("scene_a", score=0.9), make_candidate("scene_b", score=0.9)]
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )
        assert start.json()["status"] == "WAITING_USER"

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "SELECT_SCENE", "payload": {"scene_code": "not_found"}},
        )
        assert reply.status_code == 422


@pytest.mark.anyio
async def test_api_reply_select_scene_requires_approval_before_execution(monkeypatch: pytest.MonkeyPatch):
    """候选有副作用且未批准时，SELECT_SCENE 只写选定事实，不执行。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch, catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order", requires_confirmation=True)]))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )
        assert start.json()["status"] == "WAITING_USER"

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "SELECT_SCENE", "payload": {"scene_code": "create_paid_order"}},
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "WAITING_USER"
        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        body = timeline.json()
        assert called is False
        assert body["requirements"][0]["status"] == "SATISFIED"
        assert body["proposals"][0]["status"] == "SELECTED"
        assert body["approval_records"] == []


@pytest.mark.anyio
async def test_api_reply_select_scene_with_approval_executes(monkeypatch: pytest.MonkeyPatch):
    """SELECT_SCENE + approved=true 一次完成选择和批准。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "create_paid_order"
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch, catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order", requires_confirmation=True)]))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={
                "reply_type": "SELECT_SCENE",
                "payload": {"scene_code": "create_paid_order", "approved": True},
            },
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "COMPLETED"

        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        assert len(timeline.json()["approval_records"]) == 1


@pytest.mark.anyio
async def test_api_reply_supply_scene_code_resolves_zero_candidate(monkeypatch: pytest.MonkeyPatch):
    """零候选等待时可通过 SUPPLY_SCENE_CODE 手动补录场景。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    fake_catalog = FakeSceneCatalog()

    async def fake_get_contract(*, scene_code: str, user_inputs: dict[str, object]):
        return await FakeSceneCatalog().get_contract(scene_code=scene_code, user_inputs=user_inputs)

    fake_catalog.get_contract = fake_get_contract  # type: ignore[method-assign]
    app = _make_app(monkeypatch, catalog=fake_catalog)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )
        assert start.json()["status"] == "WAITING_USER"

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={
                "reply_type": "SUPPLY_SCENE_CODE",
                "payload": {"scene_code": "create_paid_order", "inputs": {"buyer_id": "U1"}},
            },
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_api_reply_approve_executes_selected_candidate(monkeypatch: pytest.MonkeyPatch):
    """APPROVE 只处理已选定待审批候选，并继续执行。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch, catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order", requires_confirmation=True)]))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )
        select_resp = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "SELECT_SCENE", "payload": {"scene_code": "create_paid_order"}},
        )
        assert select_resp.json()["status"] == "WAITING_USER"

        approve = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "APPROVE", "payload": {}},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_api_reply_approve_after_explicit_side_effect_scene(monkeypatch: pytest.MonkeyPatch):
    """显式 scene_code 的副作用场景先写选定事实，后续 APPROVE 可继续执行。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    catalog = FakeSceneCatalog()

    async def fake_get_contract(*, scene_code: str, user_inputs: dict[str, object]):
        candidate = await FakeSceneCatalog().get_contract(scene_code=scene_code, user_inputs=user_inputs)
        candidate.requires_confirmation = True
        return candidate

    catalog.get_contract = fake_get_contract  # type: ignore[method-assign]
    app = _make_app(monkeypatch, catalog=catalog)

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

        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        assert timeline.json()["proposals"][0]["status"] == "SELECTED"
        assert timeline.json()["requirements"][0]["status"] == "SATISFIED"

        approve = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "APPROVE", "payload": {}},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_api_reply_select_scene_missing_inputs_does_not_execute(monkeypatch: pytest.MonkeyPatch):
    """SELECT_SCENE 后若仍缺必填输入，不允许发写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(
        monkeypatch,
        catalog=FakeSceneCatalog(
            candidates=[
                make_candidate("scene_a", score=0.9),
                make_candidate("create_paid_order", score=0.9, missing_inputs=["buyer_id"]),
            ]
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {}},
        )

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "SELECT_SCENE", "payload": {"scene_code": "create_paid_order"}},
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "WAITING_USER"
        assert "inputs.buyer_id" in (reply.json()["pending_question"] or "")
        assert called is False


@pytest.mark.anyio
async def test_api_reply_supply_scene_code_missing_inputs_does_not_execute(monkeypatch: pytest.MonkeyPatch):
    """SUPPLY_SCENE_CODE 后若契约仍缺参，不允许发写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch, catalog=FakeSceneCatalog())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {}},
        )

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "SUPPLY_SCENE_CODE", "payload": {"scene_code": "create_paid_order"}},
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "WAITING_USER"
        assert "inputs.buyer_id" in (reply.json()["pending_question"] or "")
        assert called is False


@pytest.mark.anyio
async def test_api_start_returns_503_when_catalog_persistence_missing(monkeypatch: pytest.MonkeyPatch):
    """真实 Catalog 持久化不可用时返回 503，而不是 500。"""
    from fastapi import HTTPException

    monkeypatch.setattr(runtime_api, "_store", Store())

    class _BrokenCatalog:
        async def search(self, **kwargs):
            raise HTTPException(status_code=503, detail="Catalog persistence not available")

        async def get_contract(self, **kwargs):
            raise HTTPException(status_code=503, detail="Catalog persistence not available")

    monkeypatch.setattr(runtime_runner, "get_catalog", lambda: _BrokenCatalog())
    app = FastAPI()
    app.include_router(runtime_api.router, prefix="/api/v1/datagen")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {}},
        )
        assert start.status_code == 503
