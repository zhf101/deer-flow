"""GDP Agent Runtime 主循环专项测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store

from _agent_runtime_catalog_fakes import FakeSceneCatalog, make_candidate


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
        catalog=FakeSceneCatalog(),
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
        catalog=FakeSceneCatalog(),
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
        catalog=FakeSceneCatalog(),
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
        catalog=FakeSceneCatalog(),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["actions"][0]["status"] == "SUCCEEDED"
    assert timeline["evidences"][0]["missing_facts"] == ["order.pay_status"]
    assert timeline["verdicts"][0]["verdict_type"] == "NEED_USER"


@pytest.mark.anyio
async def test_runner_without_scene_code_auto_selects_and_executes(monkeypatch: pytest.MonkeyPatch):
    """不传 scene_code 时，单候选高分可自动选定并执行。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "create_paid_order"
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order", score=0.9)]),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert timeline["requirements"][0]["status"] == "SATISFIED"
    assert timeline["proposals"][0]["selected_scene_code"] == "create_paid_order"


@pytest.mark.anyio
async def test_runner_zero_candidate_waits_user_with_pending_requirement(monkeypatch: pytest.MonkeyPatch):
    """零候选时 Requirement 保持 PENDING，TaskRun 等待用户补 scene。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("找一个场景", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={}),
        store,
        catalog=FakeSceneCatalog(candidates=[]),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["requirements"][0]["status"] == "PENDING"
    assert timeline["proposals"][0]["candidates"] == []


@pytest.mark.anyio
async def test_runner_selection_with_approval_waits_before_scene_write(monkeypatch: pytest.MonkeyPatch):
    """单候选需审批时，runner 不发写请求，只挂起等用户。"""
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
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order", requires_confirmation=True)]),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["attempts"] == []


@pytest.mark.anyio
async def test_runner_explicit_side_effect_scene_records_selected_fact_before_approval(monkeypatch: pytest.MonkeyPatch):
    """显式副作用 scene 在等待审批前也要先写 selected 事实。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    catalog = FakeSceneCatalog()

    async def fake_get_contract(*, scene_code: str, user_inputs: dict[str, object]):
        candidate = await FakeSceneCatalog().get_contract(scene_code=scene_code, user_inputs=user_inputs)
        candidate.requires_confirmation = True
        return candidate

    catalog.get_contract = fake_get_contract  # type: ignore[method-assign]

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
        catalog=catalog,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["requirements"][0]["status"] == "SATISFIED"
    assert timeline["proposals"][0]["status"] == "SELECTED"


@pytest.mark.anyio
async def test_runner_execute_scene_records_approval_required_on_action(monkeypatch: pytest.MonkeyPatch):
    """审批通过后执行时，Action 账本应保留 approval_required=true。"""

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
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1", "approved": True}),
        store,
        catalog=catalog,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert timeline["actions"][0]["approval_required"] is True
