"""GDP Agent Runtime 多步骤 reply 恢复测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import make_candidate

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store
from app.gdp.agent_runtime.support.errors import RuntimeValidationError
from app.gdp.agent_runtime.workflows.reply_commands import SelectSceneCommand, SupplyInputCommand
from app.gdp.agent_runtime.workflows.reply_workflow import handle_reply


class _Request:
    scene_code = None

    def __init__(self, inputs: dict[str, object]) -> None:
        self.inputs = inputs


class _MissingInputCatalog:
    async def search(self, **kwargs):
        goal = str(kwargs["goal"])
        user_inputs = kwargs["user_inputs"]
        if "创建" in goal:
            scene_code = "create_order"
            candidate = make_candidate(scene_code, scene_name=goal)
        elif "支付" in goal:
            scene_code = "pay_order"
            missing = [] if "pay_channel" in user_inputs else ["pay_channel"]
            candidate = make_candidate(scene_code, scene_name=goal, missing_inputs=missing)
        else:
            scene_code = "query_order"
            candidate = make_candidate(scene_code, scene_name=goal)
        return ([candidate], [goal])

    async def get_contract(self, *, scene_code: str, user_inputs: dict[str, object]):
        if scene_code == "pay_order":
            missing = [] if "pay_channel" in user_inputs else ["pay_channel"]
            return make_candidate(scene_code, missing_inputs=missing)
        return make_candidate(scene_code)


class _MultiCandidateCatalog:
    async def search(self, **kwargs):
        goal = str(kwargs["goal"])
        if "创建" in goal:
            return ([make_candidate("create_order", scene_name=goal)], [goal])
        if "支付" in goal:
            return (
                [
                    make_candidate("pay_order_card", scene_name="银行卡支付"),
                    make_candidate("pay_order_balance", scene_name="余额支付"),
                ],
                [goal],
            )
        return ([make_candidate("query_order", scene_name=goal)], [goal])

    async def get_contract(self, *, scene_code: str, user_inputs: dict[str, object]):
        return make_candidate(scene_code)


@pytest.mark.anyio
async def test_multistep_reply_supply_input_resumes_active_step_and_continues(monkeypatch: pytest.MonkeyPatch):
    """Step2 缺输入时，SUPPLY_INPUT 只恢复当前步骤，并继续跑完 Step3。"""
    calls: list[dict[str, object]] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append({"scene_code": scene_code, "inputs": dict(inputs)})
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1"}, "errors": []}
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

    catalog = _MissingInputCatalog()
    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)

    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)

    waiting = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=catalog)

    timeline = store.get_timeline(task_run.task_run_id)
    assert waiting.status == TaskRunStatus.WAITING_USER
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "PENDING", "PENDING"]
    assert len(timeline["attempts"]) == 1

    result = await handle_reply(
        waiting,
        SupplyInputCommand({"inputs": {"pay_channel": "BALANCE"}}),
        store,
    )

    timeline = store.get_timeline(task_run.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "DONE", "DONE"]
    assert [call["scene_code"] for call in calls] == ["create_order", "pay_order", "query_order"]
    assert calls[1]["inputs"] == {"order_id": "ORDER-1", "pay_channel": "BALANCE"}
    assert calls[2]["inputs"] == {"order_id": "ORDER-1"}


@pytest.mark.anyio
async def test_multistep_reply_select_scene_is_scoped_to_active_step(monkeypatch: pytest.MonkeyPatch):
    """Step2 等用户选场景时，不能选择 Step1 的旧候选。"""
    calls: list[dict[str, object]] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append({"scene_code": scene_code, "inputs": dict(inputs)})
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1"}, "errors": []}
        if scene_code.startswith("pay_order"):
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

    catalog = _MultiCandidateCatalog()
    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)

    store = Store()
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    store.save_task_run(task_run)

    waiting = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=catalog)

    timeline = store.get_timeline(task_run.task_run_id)
    assert waiting.status == TaskRunStatus.WAITING_USER
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "PENDING", "PENDING"]

    with pytest.raises(RuntimeValidationError, match="payload.scene_code 不在最近候选内"):
        await handle_reply(waiting, SelectSceneCommand({"scene_code": "create_order"}), store)

    result = await handle_reply(waiting, SelectSceneCommand({"scene_code": "pay_order_balance"}), store)

    timeline = store.get_timeline(task_run.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert [step["status"] for step in timeline["steps"]] == ["DONE", "DONE", "DONE"]
    assert [call["scene_code"] for call in calls] == ["create_order", "pay_order_balance", "query_order"]
