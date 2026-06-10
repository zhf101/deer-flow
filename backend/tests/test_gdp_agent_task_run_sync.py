"""GDP Agent TaskRun 同步中间件测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.gdp.agent.middlewares.task_run_sync import build_gdp_task_context, wrap_gdp_task_run_sync
from app.gdp.datagen.config.task.models import (
    DatagenTaskEnvSource,
    DatagenTaskPhase,
    DatagenTaskRunResponse,
    DatagenTaskStatus,
)


class _FakeTaskService:
    """记录 TaskRun 读取和 DeerFlow 绑定同步的轻量任务服务。"""

    def __init__(self, task_run: DatagenTaskRunResponse) -> None:
        self.task_run = task_run
        self.get_calls: list[str] = []
        self.bind_calls: list[dict] = []

    async def get_task_run(self, task_run_id: str) -> DatagenTaskRunResponse:
        self.get_calls.append(task_run_id)
        if task_run_id != self.task_run.taskRunId:
            raise RuntimeError("测试任务不存在。")
        return self.task_run

    async def bind_deerflow_run(
        self,
        task_run_id: str,
        *,
        deerflow_thread_id: str | None = None,
        deerflow_run_id: str | None = None,
        last_checkpoint_id: str | None = None,
    ) -> DatagenTaskRunResponse:
        self.bind_calls.append(
            {
                "taskRunId": task_run_id,
                "deerflowThreadId": deerflow_thread_id,
                "deerflowRunId": deerflow_run_id,
                "lastCheckpointId": last_checkpoint_id,
            }
        )
        updates = {
            "deerflowThreadId": deerflow_thread_id or self.task_run.deerflowThreadId,
            "deerflowRunId": deerflow_run_id or self.task_run.deerflowRunId,
            "lastCheckpointId": last_checkpoint_id or self.task_run.lastCheckpointId,
        }
        self.task_run = self.task_run.model_copy(update=updates)
        return self.task_run


class _FailingTaskService:
    """模拟中间件刷新失败，但节点主流程仍可返回。"""

    async def get_task_run(self, task_run_id: str) -> DatagenTaskRunResponse:
        raise RuntimeError("测试刷新失败。")

    async def bind_deerflow_run(
        self,
        task_run_id: str,
        *,
        deerflow_thread_id: str | None = None,
        deerflow_run_id: str | None = None,
        last_checkpoint_id: str | None = None,
    ) -> DatagenTaskRunResponse:
        raise RuntimeError("测试绑定失败。")


def test_build_gdp_task_context_uses_state_field_contract():
    task_run = _task_run(
        phase=DatagenTaskPhase.SCENE_FULFILLMENT,
        status=DatagenTaskStatus.RUNNING,
        deerflow_thread_id="thread-1",
        deerflow_run_id="run-1",
        last_checkpoint_id="checkpoint-1",
    )

    assert build_gdp_task_context(task_run) == {
        "task_run_id": "task_sync_1",
        "status": "RUNNING",
        "phase": "SCENE_FULFILLMENT",
        "env_code": "DEV",
        "deerflow_thread_id": "thread-1",
        "deerflow_run_id": "run-1",
        "last_checkpoint_id": "checkpoint-1",
    }


@pytest.mark.anyio
async def test_task_run_sync_wrapper_refreshes_task_context_before_and_after_node():
    task_service = _FakeTaskService(
        _task_run(
            phase=DatagenTaskPhase.SCENE_FULFILLMENT,
            status=DatagenTaskStatus.RUNNING,
        )
    )

    async def node(state, config):
        assert state["task_context"]["phase"] == "SCENE_FULFILLMENT"
        assert state["task_context"]["env_code"] == "DEV"
        task_service.task_run = task_service.task_run.model_copy(update={"phase": DatagenTaskPhase.SOURCE_CONFIG})
        return {
            "task_run_id": state["task_run_id"],
            "current_phase": "STALE_PHASE",
            "task_context": {"custom": "kept", "phase": "STALE_PHASE"},
            "nodeValue": 1,
        }

    wrapped = wrap_gdp_task_run_sync(node=node, task_service=task_service)
    result = await wrapped(
        {
            "task_run_id": "task_sync_1",
            "task_context": {"phase": "STALE_BEFORE"},
        },
        {
            "configurable": {"thread_id": "thread-from-config"},
            "metadata": {"run_id": "run-from-metadata", "checkpoint_id": "checkpoint-from-metadata"},
        },
    )

    assert result["nodeValue"] == 1
    assert result["current_phase"] == "SOURCE_CONFIG"
    assert result["task_context"] == {
        "custom": "kept",
        "task_run_id": "task_sync_1",
        "status": "RUNNING",
        "phase": "SOURCE_CONFIG",
        "env_code": "DEV",
        "deerflow_thread_id": "thread-from-config",
        "deerflow_run_id": "run-from-metadata",
        "last_checkpoint_id": "checkpoint-from-metadata",
    }
    assert task_service.get_calls == ["task_sync_1", "task_sync_1"]
    assert task_service.bind_calls == [
        {
            "taskRunId": "task_sync_1",
            "deerflowThreadId": "thread-from-config",
            "deerflowRunId": "run-from-metadata",
            "lastCheckpointId": "checkpoint-from-metadata",
        }
    ]


@pytest.mark.anyio
async def test_task_run_sync_wrapper_fails_open_when_refresh_layer_fails():
    async def node(state, config):
        return {
            "task_run_id": state["task_run_id"],
            "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
        }

    wrapped = wrap_gdp_task_run_sync(node=node, task_service=_FailingTaskService())
    result = await wrapped({"task_run_id": "task_missing"}, {"configurable": {"thread_id": "thread-1"}})

    assert result == {
        "task_run_id": "task_missing",
        "current_phase": "SCENE_DESIGN",
    }


def _task_run(
    *,
    phase: DatagenTaskPhase,
    status: DatagenTaskStatus,
    deerflow_thread_id: str | None = None,
    deerflow_run_id: str | None = None,
    last_checkpoint_id: str | None = None,
) -> DatagenTaskRunResponse:
    now = datetime.now(UTC)
    return DatagenTaskRunResponse(
        id="db-task-sync-1",
        taskRunId="task_sync_1",
        deerflowThreadId=deerflow_thread_id,
        deerflowRunId=deerflow_run_id,
        lastCheckpointId=last_checkpoint_id,
        userIntent="帮我造一笔订单",
        normalizedGoal={"rawIntent": "帮我造一笔订单"},
        envCode="DEV",
        envSource=DatagenTaskEnvSource.SYSTEM_DEFAULT,
        status=status,
        phase=phase,
        pendingInterrupts=None,
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
