"""GDP Agent 中断中间件测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.gdp.agent.middlewares.interrupt import wrap_gdp_interrupt
from app.gdp.datagen.config.task.models import (
    DatagenTaskEnvSource,
    DatagenTaskPhase,
    DatagenTaskRunResponse,
    DatagenTaskStatus,
)


class _FakeTaskService:
    """记录中断规范化审计的轻量任务服务。"""

    def __init__(self, task_run: DatagenTaskRunResponse) -> None:
        self.task_run = task_run
        self.events: list[dict] = []

    async def get_task_run(self, task_run_id: str) -> DatagenTaskRunResponse:
        if task_run_id != self.task_run.taskRunId:
            raise RuntimeError("测试任务不存在。")
        return self.task_run

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


@pytest.mark.anyio
async def test_interrupt_wrapper_repairs_waiting_checkpoint_from_task_run():
    pending = {
        "questionType": "SOURCE_CONFIG_REQUIRED",
        "question": "请补充 Source。",
        "details": {"envCode": "DEV"},
    }
    task_service = _FakeTaskService(_task_run(pending_interrupts=pending))

    async def node(state, config):
        return {
            "task_run_id": state["task_run_id"],
            "current_phase": DatagenTaskPhase.WAITING_USER.value,
            "pending_confirmation": {"questionType": "SOURCE_CONFIG_REQUIRED", "question": "请补充 Source。"},
            "task_context": {"phase": "SOURCE_CONFIG"},
            "nodeValue": 1,
        }

    wrapped = wrap_gdp_interrupt(
        node_name="source_config",
        node=node,
        task_service=task_service,
    )
    result = await wrapped(
        {
            "task_run_id": "task_interrupt_1",
            "current_phase": DatagenTaskPhase.SOURCE_CONFIG.value,
        },
        {},
    )

    assert result["nodeValue"] == 1
    assert result["current_phase"] == "WAITING_USER"
    assert result["pending_confirmation"] == {
        "taskRunId": "task_interrupt_1",
        "phase": "SOURCE_CONFIG",
        "questionType": "SOURCE_CONFIG_REQUIRED",
        "question": "请补充 Source。",
        "details": {},
    }
    assert result["task_context"] == {
        "task_run_id": "task_interrupt_1",
        "status": "WAITING_USER",
        "phase": "WAITING_USER",
        "env_code": "DEV",
        "deerflow_thread_id": "thread-1",
        "deerflow_run_id": "run-1",
        "last_checkpoint_id": "checkpoint-1",
    }
    assert task_service.events[0]["eventType"] == "AGENT_INTERRUPT_NORMALIZED"
    assert task_service.events[0]["payload"]["repairedFields"] == ["taskRunId", "phase", "details"]


@pytest.mark.anyio
async def test_interrupt_wrapper_restores_missing_pending_from_task_run_without_extra_audit():
    pending = {
        "taskRunId": "task_interrupt_1",
        "phase": "SCENE_DESIGN",
        "resumePhase": "SCENE_DESIGN",
        "questionType": "SOURCE_CANDIDATE_CONFIRM",
        "question": "请选择 Source。",
        "details": {"selectionKey": "selectedSourceCode"},
    }
    task_service = _FakeTaskService(_task_run(pending_interrupts=pending))

    async def node(state, config):
        return {
            "task_run_id": state["task_run_id"],
            "current_phase": DatagenTaskPhase.WAITING_USER.value,
        }

    wrapped = wrap_gdp_interrupt(
        node_name="scene_design",
        node=node,
        task_service=task_service,
    )
    result = await wrapped({"task_run_id": "task_interrupt_1"}, {})

    assert result["pending_confirmation"] == pending
    assert result["task_context"]["status"] == "WAITING_USER"
    assert result["task_context"]["phase"] == "WAITING_USER"
    assert task_service.events == []


@pytest.mark.anyio
async def test_interrupt_wrapper_ignores_non_waiting_result():
    task_service = _FakeTaskService(_task_run(pending_interrupts=None, status=DatagenTaskStatus.RUNNING))

    async def node(state, config):
        return {
            "task_run_id": state["task_run_id"],
            "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
        }

    wrapped = wrap_gdp_interrupt(
        node_name="scene_design",
        node=node,
        task_service=task_service,
    )
    result = await wrapped({"task_run_id": "task_interrupt_1"}, {})

    assert result == {
        "task_run_id": "task_interrupt_1",
        "current_phase": "SCENE_DESIGN",
    }
    assert task_service.events == []


def _task_run(
    *,
    pending_interrupts: dict | None,
    status: DatagenTaskStatus = DatagenTaskStatus.WAITING_USER,
) -> DatagenTaskRunResponse:
    now = datetime.now(UTC)
    return DatagenTaskRunResponse(
        id="db-task-interrupt-1",
        taskRunId="task_interrupt_1",
        deerflowThreadId="thread-1",
        deerflowRunId="run-1",
        lastCheckpointId="checkpoint-1",
        userIntent="帮我造一笔订单",
        normalizedGoal={"rawIntent": "帮我造一笔订单"},
        envCode="DEV",
        envSource=DatagenTaskEnvSource.SYSTEM_DEFAULT,
        status=status,
        phase=DatagenTaskPhase.WAITING_USER if status == DatagenTaskStatus.WAITING_USER else DatagenTaskPhase.SCENE_DESIGN,
        pendingInterrupts=pending_interrupts,
        goalStack=[],
        plan=None,
        visibleVariables=[],
        reflection=None,
        failureType=None,
        failureMessage=None,
        finalSummary=None,
        createdBy=None,
        createdAt=now,
        updatedAt=now,
        finishedAt=None,
    )
