"""GDP Agent Runtime MVP5 契约漂移检测专项测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import ReplyType, SceneCandidate, SuspendReason, TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store
from app.gdp.agent_runtime.support.contract_hash import DriftCheck, compare_contract_hash
from app.gdp.agent_runtime.workflows.reply_commands import parse_runtime_command
from app.gdp.agent_runtime.workflows.reply_workflow import handle_reply


class _Request:
    scene_code = None

    def __init__(self, inputs: dict[str, object]) -> None:
        self.inputs = inputs


def _candidate(scene_code: str, *, contract_hash: str, score: float = 0.9) -> SceneCandidate:
    return SceneCandidate(
        scene_code=scene_code,
        scene_name=scene_code,
        score=score,
        reasons=[f"命中 {scene_code}"],
        missing_inputs=[],
        requires_confirmation=False,
        contract_hash=contract_hash,
    )


class _DriftingCatalog:
    """search 给出选定快照哈希；get_contract 的哈希可切换，模拟执行前契约漂移。"""

    def __init__(self, *, search_hash: str, contract_hash: str) -> None:
        self._search_hash = search_hash
        self.contract_hash = contract_hash  # 可在测试中途修改以模拟"用户接受新契约"
        self.get_contract_calls = 0

    async def search(self, **kwargs):
        goal = str(kwargs["goal"])
        return (
            [
                _candidate("scene_a", contract_hash=self._search_hash),
                _candidate("scene_b", contract_hash=self._search_hash),
            ],
            [goal],
        )

    async def get_contract(self, *, scene_code: str, user_inputs: dict[str, object]):
        self.get_contract_calls += 1
        return _candidate(scene_code, contract_hash=self.contract_hash)


def test_compare_contract_hash_detects_drift_and_ignores_empty():
    assert compare_contract_hash("h1", "h2") == DriftCheck(drifted=True, stored_hash="h1", fresh_hash="h2")
    assert compare_contract_hash("h1", "h1").drifted is False
    # 任一为空视为不漂移，避免历史无快照误报。
    assert compare_contract_hash(None, "h2").drifted is False
    assert compare_contract_hash("h1", None).drifted is False


@pytest.mark.anyio
async def test_select_scene_blocks_on_contract_drift(monkeypatch: pytest.MonkeyPatch):
    """select_scene 恢复路径执行前重验：契约漂移则阻断等用户确认，不发起写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {"order_id": "O1"}, "errors": []}

    catalog = _DriftingCatalog(search_hash="hash-selected", contract_hash="hash-DRIFTED")
    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)

    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    waiting = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=catalog)
    assert waiting.status == TaskRunStatus.WAITING_USER  # 多候选挂起待选

    command = parse_runtime_command(ReplyType.SELECT_SCENE, {"scene_code": "scene_a"})
    drifted = await handle_reply(store.get_task_run(waiting.task_run_id), command, store)

    assert called is False  # 漂移阻断，未发起场景写请求
    assert drifted.status == TaskRunStatus.WAITING_USER
    assert drifted.suspend_reason == SuspendReason.CONTRACT_DRIFT
    timeline = store.get_timeline(drifted.task_run_id)
    drift_decision = next(d for d in timeline["decisions"] if d["decision_kind"] == "CONTRACT_DRIFT")
    assert drift_decision["status"] == "WAITING_USER"
    assert drift_decision["target_id"] == "scene_a"
    # 决策只记录哈希，不含敏感载荷。
    assert "hash-selected" in str(drift_decision)
    assert "hash-DRIFTED" in str(drift_decision)
    assert "input_ref" not in drift_decision
    assert "payload://" not in str(drift_decision)


@pytest.mark.anyio
async def test_accept_contract_drift_executes_with_new_contract(monkeypatch: pytest.MonkeyPatch):
    """用户接受新契约后按新契约执行，不再重验漂移。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {"status": "SUCCESS", "finalOutput": {"order_id": "O1"}, "errors": []}

    catalog = _DriftingCatalog(search_hash="hash-selected", contract_hash="hash-DRIFTED")
    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)

    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    waiting = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=catalog)
    select = parse_runtime_command(ReplyType.SELECT_SCENE, {"scene_code": "scene_a"})
    drifted = await handle_reply(store.get_task_run(waiting.task_run_id), select, store)
    assert drifted.suspend_reason == SuspendReason.CONTRACT_DRIFT

    accept = parse_runtime_command(ReplyType.ACCEPT_CONTRACT_DRIFT, {})
    done = await handle_reply(store.get_task_run(drifted.task_run_id), accept, store)

    assert done.status == TaskRunStatus.COMPLETED
    assert done.final_verdict_id is not None


@pytest.mark.anyio
async def test_select_scene_no_drift_executes_normally(monkeypatch: pytest.MonkeyPatch):
    """选定快照与执行前契约一致时正常执行，无漂移挂起。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {"status": "SUCCESS", "finalOutput": {"order_id": "O1"}, "errors": []}

    catalog = _DriftingCatalog(search_hash="hash-same", contract_hash="hash-same")
    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)

    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)

    waiting = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=catalog)
    select = parse_runtime_command(ReplyType.SELECT_SCENE, {"scene_code": "scene_a"})
    done = await handle_reply(store.get_task_run(waiting.task_run_id), select, store)

    assert done.status == TaskRunStatus.COMPLETED
    assert done.suspend_reason is None
