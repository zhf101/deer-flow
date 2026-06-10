"""GDP Agent 任务步骤恢复中间件测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent.middlewares.recovery import RECOVERY_REASON, recover_task_steps_once, wrap_gdp_task_recovery
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStatus, DatagenTaskStepStatus, DatagenTaskStepType


class _FakeTaskService:
    """记录非终态步骤恢复调用的轻量任务服务。"""

    def __init__(self, *, status: DatagenTaskStatus, recovered_steps: list[SimpleNamespace] | None = None) -> None:
        self.task_run = SimpleNamespace(taskRunId="task_recovery_1", status=status)
        self.recovered_steps = recovered_steps or []
        self.get_calls: list[str] = []
        self.recover_calls: list[dict] = []

    async def get_task_run(self, task_run_id: str):
        self.get_calls.append(task_run_id)
        return self.task_run

    async def recover_non_terminal_steps(self, task_run_id: str, *, reason: str):
        self.recover_calls.append({"taskRunId": task_run_id, "reason": reason})
        return self.recovered_steps


@pytest.mark.anyio
async def test_task_recovery_wrapper_recovers_non_terminal_steps_once_per_run():
    task_service = _FakeTaskService(
        status=DatagenTaskStatus.RUNNING,
        recovered_steps=[
            SimpleNamespace(
                taskStepId="step-running",
                stepNo=1,
                phase=DatagenTaskPhase.SCENE_EXECUTING,
                stepType=DatagenTaskStepType.RUN_SCENE,
                status=DatagenTaskStepStatus.FAILED,
            )
        ],
    )

    async def node(state, config):
        recovery = state["decision_context"]["taskStepRecovery"]
        assert recovery["recoveredStepCount"] == 1
        assert recovery["recoveredSteps"][0]["taskStepId"] == "step-running"
        return {
            "task_run_id": state["task_run_id"],
            "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
        }

    wrapped = wrap_gdp_task_recovery(
        node_name="intake",
        node=node,
        task_service=task_service,
        enabled=True,
    )
    result = await wrapped(
        {"task_run_id": "task_recovery_1"},
        {"configurable": {"thread_id": "thread-1"}, "metadata": {"run_id": "run-1"}},
    )

    assert result["decision_context"]["taskStepRecovery"] == {
        "taskRunId": "task_recovery_1",
        "runKey": "run-1",
        "nodeName": "intake",
        "recoveredStepCount": 1,
        "recoveredSteps": [
            {
                "taskStepId": "step-running",
                "stepNo": 1,
                "phase": "SCENE_EXECUTING",
                "stepType": "RUN_SCENE",
                "status": "FAILED",
            }
        ],
        "skipped": False,
        "reason": RECOVERY_REASON,
    }
    assert task_service.recover_calls == [{"taskRunId": "task_recovery_1", "reason": RECOVERY_REASON}]


@pytest.mark.anyio
async def test_recover_task_steps_once_skips_when_run_key_already_recovered():
    task_service = _FakeTaskService(status=DatagenTaskStatus.RUNNING)

    result = await recover_task_steps_once(
        task_service,
        {
            "task_run_id": "task_recovery_1",
            "decision_context": {"taskStepRecovery": {"runKey": "run-1"}},
        },
        {"metadata": {"run_id": "run-1"}},
        node_name="scene_fulfillment",
    )

    assert result is None
    assert task_service.get_calls == []
    assert task_service.recover_calls == []


@pytest.mark.anyio
async def test_recover_task_steps_once_skips_waiting_user_task_without_step_recovery():
    task_service = _FakeTaskService(status=DatagenTaskStatus.WAITING_USER)

    result = await recover_task_steps_once(
        task_service,
        {"task_run_id": "task_recovery_1"},
        {"configurable": {"thread_id": "thread-waiting"}},
        node_name="human_confirm",
    )

    assert result == {
        "taskRunId": "task_recovery_1",
        "runKey": "thread-waiting",
        "nodeName": "human_confirm",
        "recoveredStepCount": 0,
        "recoveredSteps": [],
        "skipped": True,
        "reason": RECOVERY_REASON,
    }
    assert task_service.get_calls == ["task_recovery_1"]
    assert task_service.recover_calls == []
