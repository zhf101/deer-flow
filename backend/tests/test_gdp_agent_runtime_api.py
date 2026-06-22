"""GDP Agent Runtime API 专项测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import FakeSceneCatalog, make_candidate
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.agent_runtime import api as runtime_api
from app.gdp.agent_runtime import runner as runtime_runner
from app.gdp.agent_runtime.models import SuspendReason
from app.gdp.agent_runtime.store import Store


def _make_app(monkeypatch: pytest.MonkeyPatch, *, catalog: FakeSceneCatalog | None = None) -> FastAPI:
    monkeypatch.setattr(runtime_api, "_store", Store())
    # 显式 scene_code 路径现在契约驱动，需注入假 Catalog，避免触达真实持久化。
    fake = catalog or FakeSceneCatalog()
    monkeypatch.setattr(runtime_runner, "get_catalog", lambda: fake)
    app = FastAPI()
    app.include_router(runtime_api.router, prefix="/api/v1/datagen")
    return app


class FailingRuntimeRepository:
    async def persist_store(self, store: Store, task_run_id: str) -> None:
        raise RuntimeError("db down")


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
        assert start.json()["suspend_reason"] == SuspendReason.UNKNOWN_STATE_CONFIRMATION

        reply = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/reply",
            json={"reply_type": "CONFIRM_UNKNOWN_STATE", "payload": {"message": "人工确认不重试"}},
        )
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "FAILED"
        assert reply.json()["suspend_reason"] is None
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
        assert start.json()["suspend_reason"] == SuspendReason.MISSING_INPUT

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
        assert len(timeline.json()["steps"]) == 1
        assert len(timeline.json()["requirements"]) == 1
        assert call_count == 1


@pytest.mark.anyio
async def test_api_payload_endpoint_rejects_other_task_run_ref(monkeypatch: pytest.MonkeyPatch):
    """payload 详情必须按 TaskRun 隔离，不能用 A 任务读取 B 任务的 ref。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "runId": f"scene-run-{inputs['buyer_id']}",
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task_ids: list[str] = []
        response_refs: list[str] = []
        for buyer_id in ["U1", "U2"]:
            create = await client.post(
                "/api/v1/datagen/agent-runtime/task-runs",
                json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
            )
            task_run_id = create.json()["task_run_id"]
            task_ids.append(task_run_id)

            start = await client.post(
                f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
                json={"scene_code": "create_paid_order", "inputs": {"buyer_id": buyer_id}},
            )
            assert start.status_code == 200, start.text

            timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
            response_refs.append(timeline.json()["attempts"][0]["response_ref"])

        own_payload = await client.get(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_ids[1]}/payloads",
            params={"ref": response_refs[1]},
        )
        assert own_payload.status_code == 200, own_payload.text
        assert own_payload.json()["payload"]["runId"] == "scene-run-U2"

        cross_payload = await client.get(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_ids[0]}/payloads",
            params={"ref": response_refs[1]},
        )
        assert cross_payload.status_code == 404


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
async def test_api_start_mvp4a_scene_records_five_step_scene_run_audit(monkeypatch: pytest.MonkeyPatch):
    """MVP4A 五步场景从运行台启动后，Runtime 保留场景运行下钻 ID 和完整步骤证据。"""

    scene_code = "mvp4a_order_payment_inventory_sql_flow"
    scene_run_id = "scene-run-mvp4a-1"

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "mvp4a_order_payment_inventory_sql_flow"
        assert env_code == "SIT1"
        assert inputs["approved"] is True
        assert inputs["request_id"] == "req-mvp4a-001"
        return {
            "runId": scene_run_id,
            "sceneCode": scene_code,
            "versionNo": 1,
            "envCode": env_code,
            "inputs": inputs,
            "status": "SUCCESS",
            "startedAt": "2026-06-18T00:00:00Z",
            "finishedAt": "2026-06-18T00:00:01Z",
            "durationMs": 1000,
            "stepResults": [
                {
                    "stepId": "create_order",
                    "stepName": "HTTP 创建带商品订单",
                    "type": "HTTP",
                    "stepOrder": 1,
                    "timelineOrder": 1,
                    "status": "SUCCESS",
                    "startedAt": "2026-06-18T00:00:00Z",
                    "finishedAt": "2026-06-18T00:00:00.200Z",
                    "durationMs": 200,
                    "outputs": {"order_id": "T202606180001", "buyer_id": "U10001", "sku_id": "SKU10001", "quantity": 1},
                    "rawResponse": {"request": {"method": "POST"}, "response": {"statusCode": 200}},
                    "error": None,
                    "statusCode": 200,
                },
                {
                    "stepId": "lock_inventory",
                    "stepName": "HTTP 锁定库存",
                    "type": "HTTP",
                    "stepOrder": 2,
                    "timelineOrder": 2,
                    "status": "SUCCESS",
                    "startedAt": "2026-06-18T00:00:00.200Z",
                    "finishedAt": "2026-06-18T00:00:00.400Z",
                    "durationMs": 200,
                    "outputs": {"lock_id": "LOCK-1"},
                    "rawResponse": {"request": {"method": "POST"}, "response": {"statusCode": 200}},
                    "error": None,
                    "statusCode": 200,
                },
                {
                    "stepId": "create_payment",
                    "stepName": "HTTP 发起支付",
                    "type": "HTTP",
                    "stepOrder": 3,
                    "timelineOrder": 3,
                    "status": "SUCCESS",
                    "startedAt": "2026-06-18T00:00:00.400Z",
                    "finishedAt": "2026-06-18T00:00:00.600Z",
                    "durationMs": 200,
                    "outputs": {"payment_id": "PAY-1"},
                    "rawResponse": {"request": {"method": "POST"}, "response": {"statusCode": 200}},
                    "error": None,
                    "statusCode": 200,
                },
                {
                    "stepId": "query_payment",
                    "stepName": "HTTP 查询支付状态",
                    "type": "HTTP",
                    "stepOrder": 4,
                    "timelineOrder": 4,
                    "status": "SUCCESS",
                    "startedAt": "2026-06-18T00:00:00.600Z",
                    "finishedAt": "2026-06-18T00:00:00.800Z",
                    "durationMs": 200,
                    "outputs": {"pay_status": "PAID"},
                    "rawResponse": {"request": {"method": "GET"}, "response": {"statusCode": 200}},
                    "error": None,
                    "statusCode": 200,
                },
                {
                    "stepId": "check_member_orders",
                    "stepName": "SQL 查询买家历史订单",
                    "type": "SQL",
                    "stepOrder": 5,
                    "timelineOrder": 5,
                    "status": "SUCCESS",
                    "startedAt": "2026-06-18T00:00:00.800Z",
                    "finishedAt": "2026-06-18T00:00:01Z",
                    "durationMs": 200,
                    "outputs": {"history_order_no": "T202606180001", "history_order_status": "PAID"},
                    "rawResponse": {"operation": "SELECT", "rows": [{"order_no": "T202606180001"}]},
                    "error": None,
                    "statusCode": None,
                },
            ],
            "finalOutput": {
                "order_id": "T202606180001",
                "lock_id": "LOCK-1",
                "payment_id": "PAY-1",
                "pay_status": "PAID",
                "history_order_no": "T202606180001",
                "history_order_status": "PAID",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch, catalog=FakeSceneCatalog())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "MVP4A 订单支付库存 SQL 五步闭环", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]

        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={
                "scene_code": scene_code,
                "inputs": {
                    "buyer_id": "U10001",
                    "sku_id": "SKU10001",
                    "quantity": 1,
                    "unit_price": 299,
                    "amount": 299,
                    "payment_method": "ALIPAY",
                    "request_id": "req-mvp4a-001",
                    "warehouse_code": "WH-SH-01",
                    "city": "上海",
                    "address": "浦东新区测试路 100 号",
                    "approved": True,
                },
            },
        )
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "COMPLETED"

        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        body = timeline.json()
        assert body["actions"][0]["scene_code"] == scene_code
        assert body["attempts"][0]["scene_run_id"] == scene_run_id

        payload = await client.get(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/payloads",
            params={"ref": body["attempts"][0]["response_ref"]},
        )
        scene_result = payload.json()["payload"]
        assert [step["stepId"] for step in scene_result["stepResults"]] == [
            "create_order",
            "lock_inventory",
            "create_payment",
            "query_payment",
            "check_member_orders",
        ]
        assert scene_result["finalOutput"]["pay_status"] == "PAID"
        assert scene_result["stepResults"][4]["type"] == "SQL"


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
        assert reply.json()["suspend_reason"] == SuspendReason.NEED_APPROVAL
        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        body = timeline.json()
        assert called is False
        assert body["requirements"][0]["status"] == "SATISFIED"
        assert body["proposals"][0]["status"] == "SELECTED"
        user_decisions = [
            item
            for item in body["decisions"]
            if item["decision_kind"] == "SCENE_SELECTION" and item["decision_source"] == "USER"
        ]
        assert user_decisions[0]["target_id"] == "create_paid_order"
        assert user_decisions[0]["selected_reasons"] == ["用户在候选场景中选择了 create_paid_order。"]
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
    get_contract_call_count = 0

    async def fake_get_contract(*, scene_code: str, user_inputs: dict[str, object]):
        nonlocal get_contract_call_count
        get_contract_call_count += 1
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
        assert get_contract_call_count == 1


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
        assert reply.json()["suspend_reason"] == SuspendReason.MISSING_INPUT
        assert "inputs.buyer_id" in (reply.json()["pending_question"] or "")
        assert called is False


@pytest.mark.anyio
async def test_api_create_rolls_back_memory_when_persistence_fails(monkeypatch: pytest.MonkeyPatch):
    """创建任务落库失败时，不应把未持久化任务留在内存 Store。"""

    app = _make_app(monkeypatch)
    monkeypatch.setattr(runtime_api, "_get_repository", lambda: FailingRuntimeRepository())

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )

    assert create.status_code == 503
    assert runtime_api.get_store().list_task_runs() == []


@pytest.mark.anyio
async def test_api_start_rolls_back_memory_when_persistence_fails(monkeypatch: pytest.MonkeyPatch):
    """启动后落库失败时，内存状态应恢复到启动前。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)
    repository = None
    monkeypatch.setattr(runtime_api, "_get_repository", lambda: repository)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        task_run_id = create.json()["task_run_id"]

        repository = FailingRuntimeRepository()
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "create_paid_order", "inputs": {"buyer_id": "U1"}},
        )

    assert start.status_code == 503
    assert runtime_api.get_store().get_task_run(task_run_id).status == "CREATED"


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
        assert reply.json()["suspend_reason"] == SuspendReason.MISSING_INPUT
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

        get_after_failure = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}")
        assert get_after_failure.status_code == 200
        assert get_after_failure.json()["status"] == "CREATED"

        monkeypatch.setattr(runtime_runner, "get_catalog", lambda: FakeSceneCatalog())
        retry = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "create_paid_order", "inputs": {}},
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["status"] == "WAITING_USER"
        assert retry.json()["suspend_reason"] == SuspendReason.MISSING_INPUT
