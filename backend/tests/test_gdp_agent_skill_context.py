"""GDP Agent 技能上下文中间件测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.middlewares.skill_context import wrap_gdp_skill_context
from app.gdp.agent.skills.registry import get_gdp_skill_context
from app.gdp.datagen.config.task.models import DatagenTaskPhase


class _FakeTaskService:
    """记录测试事件的轻量任务服务。"""

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


async def _scene_design_node(state):
    return {"current_phase": DatagenTaskPhase.SCENE_DESIGN.value}


async def _source_config_node(state):
    return {"current_phase": DatagenTaskPhase.SOURCE_CONFIG.value}


async def _failed_node(state):
    return {"current_phase": DatagenTaskPhase.FAILED.value}


@pytest.mark.anyio
async def test_skill_context_wrapper_injects_phase_skills_and_records_event():
    task_service = _FakeTaskService()
    node = wrap_gdp_skill_context(
        node_name="scene_design",
        node=_scene_design_node,
        task_service=task_service,
        enabled=True,
    )

    result = await node({"task_run_id": "task_skill_1", "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value})

    assert result["skill_context"]["phase"] == "SCENE_DESIGN"
    assert {item["skillId"] for item in result["skill_context"]["skills"]} >= {
        "gdp-scene-design",
        "gdp-sql-source-design",
        "gdp-http-source-design",
    }
    assert result["skill_trace"][0]["nodeName"] == "scene_design"
    assert result["skill_trace"][0]["skillIds"]
    assert task_service.events[0]["eventType"] == "AGENT_SKILLS_SELECTED"
    assert task_service.events[0]["payload"]["skillIds"] == result["skill_context"]["skillIds"]


@pytest.mark.anyio
async def test_skill_context_wrapper_skips_duplicate_phase_event():
    task_service = _FakeTaskService()
    node = wrap_gdp_skill_context(
        node_name="source_config",
        node=_source_config_node,
        task_service=task_service,
        enabled=True,
    )
    existing_context = get_gdp_skill_context(DatagenTaskPhase.SOURCE_CONFIG)

    result = await node(
        {
            "task_run_id": "task_skill_2",
            "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
            "skill_context": existing_context,
        }
    )

    assert result["skill_context"]["phase"] == "SOURCE_CONFIG"
    assert task_service.events == []


@pytest.mark.anyio
async def test_skill_context_wrapper_handles_terminal_phase_without_event():
    task_service = _FakeTaskService()
    node = wrap_gdp_skill_context(
        node_name="failed",
        node=_failed_node,
        task_service=task_service,
        enabled=True,
    )

    result = await node({"task_run_id": "task_skill_3", "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value})

    assert result["skill_context"]["phase"] == "FAILED"
    assert result["skill_context"]["skillIds"] == []
    assert result["skill_trace"][0]["skillIds"] == []
    assert task_service.events == []
