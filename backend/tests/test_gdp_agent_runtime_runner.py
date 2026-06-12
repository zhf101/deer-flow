"""GDP Agent Runtime 主循环专项测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store


@pytest.mark.anyio
async def test_runner_missing_required_input_waits_user_without_scene_write(monkeypatch: pytest.MonkeyPatch):
    """缺 MVP 必填输入时不发起 Scene 写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert "inputs.buyer_id" in (result.pending_question or "")
    assert timeline["actions"] == []
    assert timeline["attempts"] == []


@pytest.mark.anyio
async def test_runner_missing_env_waits_user_without_scene_write(monkeypatch: pytest.MonkeyPatch):
    """缺环境编码时不发起 Scene 写请求，等待用户补充。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code=None)
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert "env_code" in (result.pending_question or "")
    assert timeline["actions"] == []
    assert timeline["attempts"] == []


@pytest.mark.anyio
async def test_runner_scene_success_but_failed_evidence_fails_task_with_succeeded_action(
    monkeypatch: pytest.MonkeyPatch,
):
    """Scene 技术执行成功但业务证据不通过时，Action 成功而 TaskRun 失败。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {
                "order_id": "ORDER-1",
                "pay_status": "UNPAID",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.FAILED
    assert timeline["actions"][0]["status"] == "SUCCEEDED"
    assert timeline["evidences"][0]["facts"][-1]["subject"] == "order.pay_status"
    assert timeline["evidences"][0]["facts"][-1]["passed"] is False
    assert timeline["verdicts"][0]["verdict_type"] == "FAILED"


@pytest.mark.anyio
async def test_runner_missing_pay_status_needs_user_not_done(monkeypatch: pytest.MonkeyPatch):
    """Scene 成功但缺 pay_status 时进入 NEED_USER，不误判完成。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {
                "order_id": "ORDER-1",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["actions"][0]["status"] == "SUCCEEDED"
    assert timeline["evidences"][0]["missing_facts"] == ["order.pay_status"]
    assert timeline["verdicts"][0]["verdict_type"] == "NEED_USER"

