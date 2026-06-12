"""GDP Agent Runtime 第二阶段 Scene 选择链路验收测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store

from _agent_runtime_catalog_fakes import FakeSceneCatalog, make_candidate


@pytest.mark.anyio
async def test_scene_selection_runner_auto_select_happy_path(monkeypatch: pytest.MonkeyPatch):
    """单候选高分时自动选定并执行。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "create_paid_order"
        assert inputs == {"buyer_id": "U1"}
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
async def test_scene_selection_runner_multiple_candidates_wait_for_user(monkeypatch: pytest.MonkeyPatch):
    """多个候选时进入 WAITING_USER，不发起写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[
                make_candidate("scene_a", score=0.9),
                make_candidate("scene_b", score=0.9),
            ]
        ),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert len(timeline["proposals"][0]["candidates"]) == 2


@pytest.mark.anyio
async def test_scene_selection_runner_zero_candidate_waits_for_supply_scene_code(monkeypatch: pytest.MonkeyPatch):
    """零候选时挂起等待用户补 scene_code。"""
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
async def test_scene_selection_runner_missing_inputs_needs_user_without_write(monkeypatch: pytest.MonkeyPatch):
    """候选缺参时不发写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[make_candidate("create_paid_order", score=0.9, missing_inputs=["buyer_id"])]
        ),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["attempts"] == []


@pytest.mark.anyio
async def test_scene_selection_runner_requires_approval_without_write(monkeypatch: pytest.MonkeyPatch):
    """候选需审批时不发写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[make_candidate("create_paid_order", score=0.9, requires_confirmation=True)]
        ),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert timeline["attempts"] == []


@pytest.mark.anyio
async def test_scene_selection_runner_explicit_scene_code_still_uses_contract(monkeypatch: pytest.MonkeyPatch):
    """显式 scene_code 路径仍走契约缺参校验。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
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
    assert timeline["requirements"][0]["status"] == "SATISFIED"


@pytest.mark.anyio
async def test_scene_selection_runner_failed_execution_writes_blacklist(monkeypatch: pytest.MonkeyPatch):
    """执行失败后写黑名单，供后续重搜排除。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "FAILED",
            "finalOutput": {},
            "errors": [{"message": "scene failed"}],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(candidates=[make_candidate("create_paid_order", score=0.9)]),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.FAILED
    assert timeline["requirements"][0]["blacklist"] == ["create_paid_order"]
