"""GDP Agent Runtime MVP6-B 用户驱动回退计划测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import make_candidate

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store
from app.gdp.agent_runtime.support.errors import RuntimeConflictError
from app.gdp.agent_runtime.workflows.rollback_plan import build_rollback_plan


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


async def _failed_multistep_with_tainted_order(monkeypatch: pytest.MonkeyPatch):
    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1"}, "errors": []}
        return {"status": "FAILED", "errors": [{"message": "支付失败"}]}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)
    result = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=_GoalCatalog())
    return result, store


@pytest.mark.anyio
async def test_build_rollback_plan_explains_tainted_variable_impact(monkeypatch: pytest.MonkeyPatch):
    """失败任务的回退计划能解释污染变量、生产步骤、失败步骤和后续受影响步骤。"""
    result, store = await _failed_multistep_with_tainted_order(monkeypatch)
    timeline_before = store.get_timeline(result.task_run_id)

    plan = build_rollback_plan(result, store)
    timeline_after = store.get_timeline(result.task_run_id)

    order_variable = next(variable for variable in timeline_before["variables"] if variable["name"] == "order_id")
    assert plan.task_run_id == result.task_run_id
    assert plan.failed_step_id == timeline_before["steps"][1]["step_id"]
    assert plan.tainted_variable_ids == [order_variable["variable_id"]]
    assert plan.rollback_candidate_step_ids == [
        timeline_before["steps"][0]["step_id"],
        timeline_before["steps"][1]["step_id"],
    ]
    assert plan.affected_step_ids == [
        timeline_before["steps"][1]["step_id"],
        timeline_before["steps"][2]["step_id"],
    ]
    assert plan.can_auto_replay is False
    assert "不会自动重放" in " ".join(plan.safety_warnings)
    assert len(timeline_after["actions"]) == len(timeline_before["actions"])
    assert len(timeline_after["attempts"]) == len(timeline_before["attempts"])


@pytest.mark.anyio
async def test_build_rollback_plan_rejects_task_without_tainted_variables(monkeypatch: pytest.MonkeyPatch):
    """没有污染变量证据的任务不能生成回退计划。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)
    result = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=_GoalCatalog())

    with pytest.raises(RuntimeConflictError):
        build_rollback_plan(result, store)
