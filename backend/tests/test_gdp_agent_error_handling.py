"""GDP Agent 错误处理中间件测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.errors import GraphInterrupt

from app.gdp.agent.middlewares.error_handling import build_node_error_payload, wrap_gdp_error_handling
from app.gdp.datagen.config.task.models import DatagenTaskPhase


class _FakeTaskService:
    """记录节点失败事件和 TaskRun 失败更新的轻量任务服务。"""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.failed_tasks: list[dict] = []
        self.bind_calls: list[dict] = []

    async def bind_deerflow_run(
        self,
        task_run_id: str,
        *,
        deerflow_thread_id: str | None = None,
        deerflow_run_id: str | None = None,
        last_checkpoint_id: str | None = None,
    ):
        self.bind_calls.append(
            {
                "taskRunId": task_run_id,
                "deerflowThreadId": deerflow_thread_id,
                "deerflowRunId": deerflow_run_id,
                "lastCheckpointId": last_checkpoint_id,
            }
        )

    async def record_event(self, task_run_id: str, *, event_type, phase, message, payload):
        self.events.append(
            {
                "taskRunId": task_run_id,
                "eventType": event_type,
                "phase": phase.value,
                "message": message,
                "payload": payload,
            }
        )

    async def fail_task(self, task_run_id: str, *, failure_type: str, failure_message: str):
        self.failed_tasks.append(
            {
                "taskRunId": task_run_id,
                "failureType": failure_type,
                "failureMessage": failure_message,
            }
        )


def test_build_node_error_payload_uses_stable_failure_contract():
    payload = build_node_error_payload(
        "source_config",
        ValueError("Source 配置缺失。"),
        {"current_phase": DatagenTaskPhase.SOURCE_CONFIG.value},
        {"runtime": {"assistant_id": "gdp_agent"}},
    )

    assert payload == {
        "nodeName": "source_config",
        "errorType": "AGENT_NODE_ERROR:source_config",
        "errorClass": "ValueError",
        "errorMessage": "Source 配置缺失。",
        "currentPhase": "SOURCE_CONFIG",
        "runtime": {"assistant_id": "gdp_agent"},
    }


@pytest.mark.anyio
async def test_error_handling_marks_task_failed_and_reraises_original_exception():
    task_service = _FakeTaskService()

    async def failing_node(state, config):
        raise ValueError("Source 配置缺失。")

    wrapped = wrap_gdp_error_handling(
        node_name="source_config",
        node=failing_node,
        task_service=task_service,
        metadata=SimpleNamespace(assistant_id="gdp_agent"),
    )

    with pytest.raises(ValueError, match="Source 配置缺失"):
        await wrapped(
            {
                "task_run_id": "task_error_1",
                "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
            },
            {
                "configurable": {"thread_id": "thread-1"},
                "metadata": {"run_id": "run-1", "checkpoint_id": "checkpoint-1"},
            },
        )

    assert task_service.bind_calls == [
        {
            "taskRunId": "task_error_1",
            "deerflowThreadId": "thread-1",
            "deerflowRunId": "run-1",
            "lastCheckpointId": "checkpoint-1",
        }
    ]
    assert task_service.events[0]["eventType"] == "AGENT_NODE_FAILED"
    assert task_service.events[0]["phase"] == "SOURCE_CONFIG"
    assert task_service.events[0]["payload"]["nodeName"] == "source_config"
    assert task_service.events[0]["payload"]["errorClass"] == "ValueError"
    assert task_service.failed_tasks == [
        {
            "taskRunId": "task_error_1",
            "failureType": "AGENT_NODE_ERROR:source_config",
            "failureMessage": "Agent 节点 source_config 执行失败：Source 配置缺失。",
        }
    ]


@pytest.mark.anyio
async def test_error_handling_reraises_langgraph_interrupt_without_failure_side_effects():
    task_service = _FakeTaskService()

    async def interrupting_node(state, config):
        raise GraphInterrupt(())

    wrapped = wrap_gdp_error_handling(
        node_name="human_confirm",
        node=interrupting_node,
        task_service=task_service,
    )

    with pytest.raises(GraphInterrupt):
        await wrapped({"task_run_id": "task_error_1"}, {})

    assert task_service.bind_calls == []
    assert task_service.events == []
    assert task_service.failed_tasks == []
