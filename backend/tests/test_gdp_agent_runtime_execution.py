"""GDP Agent Runtime 执行层专项测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent_runtime.execution import run_action
from app.gdp.agent_runtime.flow import create_single_step, create_task_run, make_scene_action
from app.gdp.agent_runtime.models import AttemptStatus
from app.gdp.agent_runtime.store import Store


@pytest.mark.anyio
async def test_execution_records_scene_run_id_and_payload_refs(monkeypatch: pytest.MonkeyPatch):
    """场景执行成功后，Attempt 应关联场景运行记录并保存请求响应快照。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "create_paid_order"
        assert env_code == "SIT1"
        assert inputs == {"buyer_id": "U1"}
        return {
            "runId": "scene-run-1",
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})

    store.save_task_run(task_run)
    store.save_action(action)
    store.save_payload(task_run.task_run_id, action.input_ref, {"buyer_id": "U1"})

    attempt, observation = await run_action(action, store)

    assert attempt.status == AttemptStatus.SUCCEEDED
    assert attempt.scene_run_id == "scene-run-1"
    assert store.get_payload(task_run.task_run_id, attempt.request_ref) == {
        "scene_code": "create_paid_order",
        "env_code": "SIT1",
        "inputs": {"buyer_id": "U1"},
    }
    assert attempt.response_ref is not None
    assert store.get_payload(task_run.task_run_id, attempt.response_ref)["runId"] == "scene-run-1"
    assert observation.raw_ref == attempt.response_ref


@pytest.mark.anyio
async def test_execution_idempotency_conflict_returns_failed_attempt_without_scene_write(
    monkeypatch: pytest.MonkeyPatch,
):
    """幂等冲突应转成可判定失败，不冒泡成 API 500。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    started_action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
    duplicate_action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
    started_action.attempt_ids.append("att-existing")

    store.save_task_run(task_run)
    store.save_action(started_action)
    store.save_action(duplicate_action)
    store.save_payload(task_run.task_run_id, duplicate_action.input_ref, {"buyer_id": "U1"})

    attempt, observation = await run_action(duplicate_action, store)

    assert called is False
    assert attempt.status == AttemptStatus.FAILED
    assert attempt.error_type == "IDEMPOTENCY_CONFLICT"
    assert "幂等键已发起过写请求" in (attempt.error_message or "")
    assert observation.preview == {"error": attempt.error_message}


@pytest.mark.anyio
async def test_execution_external_idempotency_gate_blocks_scene_write(monkeypatch: pytest.MonkeyPatch):
    """数据库幂等门控命中时，执行层不能继续发起场景写请求。"""

    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    async def idempotency_gate(task_run_id: str, action_id: str, idempotency_key: str) -> bool:
        return True

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})

    store.save_task_run(task_run)
    store.save_action(action)
    store.save_payload(task_run.task_run_id, action.input_ref, {"buyer_id": "U1"})

    attempt, observation = await run_action(action, store, idempotency_gate)

    assert called is False
    assert attempt.status == AttemptStatus.FAILED
    assert attempt.error_type == "IDEMPOTENCY_CONFLICT"
    assert observation.preview == {"error": attempt.error_message}
