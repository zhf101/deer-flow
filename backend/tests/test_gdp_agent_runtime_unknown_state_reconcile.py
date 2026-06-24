"""GDP Agent Runtime MVP5 UNKNOWN_STATE 对账双路径专项测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import FakeSceneCatalog

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import ReplyType, TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store
from app.gdp.agent_runtime.support.errors import RuntimeValidationError
from app.gdp.agent_runtime.workflows.reply_commands import parse_runtime_command
from app.gdp.agent_runtime.workflows.reply_workflow import handle_reply


class _Request:
    def __init__(self, scene_code: str | None, inputs: dict[str, object]) -> None:
        self.scene_code = scene_code
        self.inputs = inputs


def _install_catalog(monkeypatch: pytest.MonkeyPatch) -> FakeSceneCatalog:
    catalog = FakeSceneCatalog()
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)
    return catalog


async def _start_unknown_state(monkeypatch: pytest.MonkeyPatch, store: Store):
    """启动一个写场景并令其超时进入 UNKNOWN_STATE，返回挂起的 TaskRun。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        if scene_code == "verify_order":
            return {
                "status": "SUCCESS",
                "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
                "errors": [],
            }
        raise TimeoutError("write timeout")

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    _install_catalog(monkeypatch)

    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)
    waiting = await run_task(
        task_run,
        _Request("create_paid_order", {"buyer_id": "U1"}),
        store,
    )
    assert waiting.status == TaskRunStatus.WAITING_USER
    return waiting


@pytest.mark.anyio
async def test_confirm_failed_keeps_failure_closure(monkeypatch: pytest.MonkeyPatch):
    """actual_outcome=FAILED（含缺省）维持失败收口，向后兼容旧客户端。"""
    store = Store()
    waiting = await _start_unknown_state(monkeypatch, store)

    command = parse_runtime_command(ReplyType.CONFIRM_UNKNOWN_STATE, {"message": "人工确认失败"})
    result = await handle_reply(store.get_task_run(waiting.task_run_id), command, store)

    assert result.status == TaskRunStatus.FAILED
    assert "避免重复写请求" in (result.failure_reason or "")


@pytest.mark.anyio
async def test_confirm_success_with_verify_scene_promotes_to_completed(monkeypatch: pytest.MonkeyPatch):
    """actual_outcome=SUCCEEDED + 只读核查场景证据证明成功 → COMPLETED 带 final_verdict_id。"""
    store = Store()
    waiting = await _start_unknown_state(monkeypatch, store)

    command = parse_runtime_command(
        ReplyType.CONFIRM_UNKNOWN_STATE,
        {"actual_outcome": "SUCCEEDED", "verify_scene_code": "verify_order"},
    )
    result = await handle_reply(store.get_task_run(waiting.task_run_id), command, store)

    assert result.status == TaskRunStatus.COMPLETED
    assert result.final_verdict_id is not None


@pytest.mark.anyio
async def test_confirm_success_requires_verify_scene_code(monkeypatch: pytest.MonkeyPatch):
    """确认成功但不提供核查场景 → 拒绝，不接受无证据的成功断言。"""
    store = Store()
    waiting = await _start_unknown_state(monkeypatch, store)

    command = parse_runtime_command(ReplyType.CONFIRM_UNKNOWN_STATE, {"actual_outcome": "SUCCEEDED"})
    with pytest.raises(RuntimeValidationError):
        await handle_reply(store.get_task_run(waiting.task_run_id), command, store)


@pytest.mark.anyio
async def test_confirm_success_verify_not_proven_does_not_complete(monkeypatch: pytest.MonkeyPatch):
    """核查场景证据未证明成功（pay_status 非 PAID）→ 不推进为 COMPLETED。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        if scene_code == "verify_order":
            # 证据不达标：pay_status 非 PAID → judge 不会 DONE。
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1", "pay_status": "UNPAID"}, "errors": []}
        raise TimeoutError("write timeout")

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    _install_catalog(monkeypatch)
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)
    waiting = await run_task(task_run, _Request("create_paid_order", {"buyer_id": "U1"}), store)
    assert waiting.status == TaskRunStatus.WAITING_USER

    command = parse_runtime_command(
        ReplyType.CONFIRM_UNKNOWN_STATE,
        {"actual_outcome": "SUCCEEDED", "verify_scene_code": "verify_order"},
    )
    result = await handle_reply(store.get_task_run(waiting.task_run_id), command, store)

    assert result.status != TaskRunStatus.COMPLETED


@pytest.mark.anyio
async def test_confirm_uncertain_stays_waiting(monkeypatch: pytest.MonkeyPatch):
    """actual_outcome=UNCERTAIN 维持 WAITING_USER，不改终态。"""
    store = Store()
    waiting = await _start_unknown_state(monkeypatch, store)

    command = parse_runtime_command(ReplyType.CONFIRM_UNKNOWN_STATE, {"actual_outcome": "UNCERTAIN"})
    result = await handle_reply(store.get_task_run(waiting.task_run_id), command, store)

    assert result.status == TaskRunStatus.WAITING_USER
