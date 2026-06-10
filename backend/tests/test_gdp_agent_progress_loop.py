"""GDP Agent 进度振荡检测测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.middlewares.progress_loop import wrap_gdp_progress_loop_detection
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


async def _scene_design_node(state, config=None):
    return {"current_phase": DatagenTaskPhase.SCENE_DESIGN.value}


async def _source_config_node(state, config=None):
    return {"current_phase": DatagenTaskPhase.SOURCE_CONFIG.value}


async def _source_config_node_with_inner_errors(state, config=None):
    return {
        "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
        "errors": [{"errorType": "GOAL_DRIFT_DETECTED", "nodeName": "source_config"}],
    }


@pytest.mark.anyio
async def test_progress_loop_records_phase_history_without_warning_before_threshold():
    task_service = _FakeTaskService()
    node = wrap_gdp_progress_loop_detection(
        node_name="scene_design",
        node=_scene_design_node,
        task_service=task_service,
        warn_threshold=3,
        window_size=6,
    )

    result = await node(
        {
            "task_run_id": "task_loop_1",
            "phase_history": [
                {"nodeName": "intake", "phase": "SCENE_FULFILLMENT", "visitNo": 1},
                {"nodeName": "source_config", "phase": "SCENE_DESIGN", "visitNo": 2},
            ],
        }
    )

    assert result["phase_history"][-1]["nodeName"] == "scene_design"
    assert result["phase_history"][-1]["phase"] == "SCENE_DESIGN"
    assert "errors" not in result
    assert task_service.events == []


@pytest.mark.anyio
async def test_progress_loop_detects_repeated_phase_in_recent_window():
    task_service = _FakeTaskService()
    node = wrap_gdp_progress_loop_detection(
        node_name="source_config",
        node=_source_config_node,
        task_service=task_service,
        warn_threshold=3,
        window_size=6,
    )

    result = await node(
        {
            "task_run_id": "task_loop_2",
            "phase_history": [
                {"nodeName": "scene_design", "phase": "SOURCE_CONFIG", "visitNo": 1},
                {"nodeName": "infra_config", "phase": "INFRA_CONFIG", "visitNo": 2},
                {"nodeName": "human_confirm", "phase": "SOURCE_CONFIG", "visitNo": 3},
            ],
        }
    )

    assert result["errors"][0]["errorType"] == "PROGRESS_LOOP_DETECTED"
    assert result["errors"][0]["phase"] == "SOURCE_CONFIG"
    assert result["errors"][0]["phaseCount"] == 3
    assert task_service.events[0]["eventType"] == "AGENT_PROGRESS_LOOP_DETECTED"
    assert task_service.events[0]["payload"]["phase"] == "SOURCE_CONFIG"


@pytest.mark.anyio
async def test_progress_loop_skips_duplicate_warning_for_same_phase():
    task_service = _FakeTaskService()
    node = wrap_gdp_progress_loop_detection(
        node_name="source_config",
        node=_source_config_node,
        task_service=task_service,
        warn_threshold=3,
        window_size=6,
    )

    result = await node(
        {
            "task_run_id": "task_loop_3",
            "phase_history": [
                {"nodeName": "scene_design", "phase": "SOURCE_CONFIG", "visitNo": 1},
                {"nodeName": "infra_config", "phase": "SOURCE_CONFIG", "visitNo": 2},
            ],
            "errors": [{"errorType": "PROGRESS_LOOP_DETECTED", "phase": "SOURCE_CONFIG"}],
        }
    )

    assert "errors" not in result
    assert task_service.events == []


@pytest.mark.anyio
async def test_progress_loop_preserves_inner_wrapper_errors_when_appending_warning():
    """wrapper 追加振荡告警时必须保留内层 wrapper 已写入 result["errors"] 的诊断。"""

    task_service = _FakeTaskService()
    node = wrap_gdp_progress_loop_detection(
        node_name="source_config",
        node=_source_config_node_with_inner_errors,
        task_service=task_service,
        warn_threshold=3,
        window_size=6,
    )

    result = await node(
        {
            "task_run_id": "task_loop_4",
            "phase_history": [
                {"nodeName": "scene_design", "phase": "SOURCE_CONFIG", "visitNo": 1},
                {"nodeName": "infra_config", "phase": "INFRA_CONFIG", "visitNo": 2},
                {"nodeName": "human_confirm", "phase": "SOURCE_CONFIG", "visitNo": 3},
            ],
        }
    )

    error_types = [item["errorType"] for item in result["errors"]]
    assert error_types == ["GOAL_DRIFT_DETECTED", "PROGRESS_LOOP_DETECTED"]
