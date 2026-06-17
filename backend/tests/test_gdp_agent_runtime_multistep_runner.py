"""GDP Agent Runtime 多步骤执行集成测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import make_candidate

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import SuspendReason, TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store


class _Request:
    scene_code = None

    def __init__(self, inputs: dict[str, object]) -> None:
        self.inputs = inputs


class _GoalCatalog:
    async def search(self, **kwargs):
        goal = str(kwargs["goal"])
        if "创建" in goal:
            scene_code = "create_order"
        elif "支付" in goal:
            scene_code = "pay_order"
        else:
            scene_code = "query_order"
        return ([make_candidate(scene_code, scene_name=goal)], [goal])

    async def get_contract(self, *, scene_code: str, user_inputs: dict[str, object]):
        return make_candidate(scene_code)


@pytest.mark.anyio
async def test_multistep_runner_executes_create_pay_and_query(monkeypatch: pytest.MonkeyPatch):
    """创建订单并支付主 case：三步依次完成，最后 TaskRun 才完成。"""
    calls: list[dict[str, object]] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append({"scene_code": scene_code, "inputs": dict(inputs)})
        if scene_code == "create_order":
            return {
                "status": "SUCCESS",
                "finalOutput": {"order_id": "ORDER-1"},
                "errors": [],
            }
        if scene_code == "pay_order":
            return {
                "status": "SUCCESS",
                "finalOutput": {"order_id": inputs["order_id"], "pay_status": "PAID", "payment_id": "PAY-1"},
                "errors": [],
            }
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": inputs["order_id"], "pay_status": "PAID", "payment_id": "PAY-1"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=_GoalCatalog())

    timeline = store.get_timeline(task_run.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "DONE", "DONE"]
    assert len(timeline["actions"]) == 3
    assert len(timeline["variables"]) >= 2
    assert all("value_ref" not in variable for variable in timeline["variables"])
    assert timeline["step_edges"][0]["variable_ids"]
    assert calls[0]["inputs"] == {"buyer_id": "U1"}
    assert calls[1]["inputs"] == {"order_id": "ORDER-1"}
    assert calls[2]["inputs"] == {"order_id": "ORDER-1"}


@pytest.mark.anyio
async def test_multistep_runner_fails_when_required_output_missing(monkeypatch: pytest.MonkeyPatch):
    """Step1 缺少 order_id 产出时，Step2 不执行，TaskRun 失败收口。"""
    calls: list[str] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append(scene_code)
        return {
            "status": "SUCCESS",
            "finalOutput": {},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=_GoalCatalog())

    timeline = store.get_timeline(task_run.task_run_id)
    assert result.status == TaskRunStatus.FAILED
    assert result.failure_reason == "缺少必需输出变量：order_id"
    assert [step["status"] for step in timeline["steps"]] == ["FAILED", "PENDING", "PENDING"]
    assert calls == ["create_order"]


@pytest.mark.anyio
async def test_multistep_runner_stops_after_middle_step_failure(monkeypatch: pytest.MonkeyPatch):
    """Step2 执行失败时，Step3 不能继续执行。"""
    calls: list[str] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append(scene_code)
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1"}, "errors": []}
        return {"status": "FAILED", "errors": [{"message": "支付失败"}]}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=_GoalCatalog())

    timeline = store.get_timeline(task_run.task_run_id)
    assert result.status == TaskRunStatus.FAILED
    assert "支付失败" in (result.failure_reason or "")
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "FAILED", "PENDING"]
    assert calls == ["create_order", "pay_order"]


@pytest.mark.anyio
async def test_multistep_runner_waits_on_unknown_state_and_blocks_following_steps(monkeypatch: pytest.MonkeyPatch):
    """Step2 结果未知时，TaskRun 等用户确认，Step3 不能继续执行。"""
    calls: list[str] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append(scene_code)
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1"}, "errors": []}
        raise TimeoutError("支付请求超时")

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=_GoalCatalog())

    timeline = store.get_timeline(task_run.task_run_id)
    assert result.status == TaskRunStatus.WAITING_USER
    assert result.suspend_reason == SuspendReason.UNKNOWN_STATE_CONFIRMATION
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "BLOCKED", "PENDING"]
    assert calls == ["create_order", "pay_order"]
