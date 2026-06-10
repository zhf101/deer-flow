"""GDP Agent 目标锚点保护测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent.middlewares.goal_guard import wrap_gdp_goal_guard
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus


class _FakeTaskService:
    """提供目标锚点测试所需的轻量任务服务。"""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.task_run = SimpleNamespace(
            taskRunId="task_goal_1",
            userIntent="帮我造一笔已支付订单",
            envCode="DEV",
            status=DatagenTaskStatus.RUNNING,
            phase=DatagenTaskPhase.SCENE_FULFILLMENT,
            goalStack=[],
            plan=None,
            visibleVariables=[],
        )

    async def get_task_run(self, task_run_id: str):
        assert task_run_id == self.task_run.taskRunId
        return self.task_run

    async def list_steps(self, task_run_id: str):
        assert task_run_id == self.task_run.taskRunId
        return []

    async def record_event(self, task_run_id: str, *, event_type: str, phase: DatagenTaskPhase, message: str, payload: dict):
        self.events.append(
            {
                "taskRunId": task_run_id,
                "eventType": event_type,
                "phase": phase.value,
                "message": message,
                "payload": payload,
            }
        )


async def _plain_node(state, config=None):
    return {"task_run_id": state["task_run_id"], "current_phase": DatagenTaskPhase.SCENE_DESIGN.value}


async def _drifting_node(state, config=None):
    return {
        "task_run_id": state["task_run_id"],
        "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
        "user_intent": "改成查询订单",
    }


@pytest.mark.anyio
async def test_goal_guard_refreshes_authoritative_goal_summary():
    task_service = _FakeTaskService()
    node = wrap_gdp_goal_guard(
        node_name="scene_design",
        node=_plain_node,
        task_service=task_service,
    )

    result = await node({"task_run_id": "task_goal_1", "user_intent": "帮我造一笔已支付订单"})

    assert result["context_summary"]["goalAnchor"]["userIntent"] == "帮我造一笔已支付订单"
    assert result["decision_context"]["goalGuard"]["nodeName"] == "scene_design"
    assert result["decision_context"]["goalGuard"]["unfinishedGoalCount"] == 0
    assert result["user_intent"] == "帮我造一笔已支付订单"
    assert "errors" not in result
    assert task_service.events == []


@pytest.mark.anyio
async def test_goal_guard_blocks_user_intent_drift_and_records_event():
    task_service = _FakeTaskService()
    node = wrap_gdp_goal_guard(
        node_name="scene_design",
        node=_drifting_node,
        task_service=task_service,
    )

    result = await node({"task_run_id": "task_goal_1", "user_intent": "帮我造一笔已支付订单"})

    assert result["user_intent"] == "帮我造一笔已支付订单"
    assert result["errors"][0]["errorType"] == "GOAL_DRIFT_DETECTED"
    assert result["errors"][0]["actual"] == "改成查询订单"
    assert task_service.events[0]["eventType"] == "AGENT_GOAL_DRIFT_DETECTED"
    assert task_service.events[0]["payload"]["expected"] == "帮我造一笔已支付订单"
