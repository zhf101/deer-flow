"""GDP Agent 节点审计中间件测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.middlewares.node_audit import wrap_gdp_node_audit
from app.gdp.datagen.config.task.models import DatagenTaskPhase


class _FakeTaskService:
    """记录节点审计事件的轻量任务服务。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

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


async def _scene_design_node(state, config):
    return {
        "task_run_id": state["task_run_id"],
        "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
    }


@pytest.mark.anyio
async def test_node_audit_records_attempt_number_and_returns_counter_delta():
    task_service = _FakeTaskService()
    node = wrap_gdp_node_audit(
        node_name="scene_design",
        node=_scene_design_node,
        task_service=task_service,
    )

    result = await node(
        {
            "task_run_id": "task_audit_1",
            "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            "node_attempts": {"scene_design": 2},
        },
        {},
    )

    assert result["node_attempts"] == {"scene_design": 1}
    assert [event["eventType"] for event in task_service.events] == ["AGENT_NODE_STARTED", "AGENT_NODE_FINISHED"]
    assert task_service.events[0]["payload"]["attemptNo"] == 3
    assert task_service.events[1]["payload"]["attemptNo"] == 3
