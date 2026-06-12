"""GDP Agent Runtime 状态机专项测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import TaskRunStatus
from app.gdp.agent_runtime.transitions import IllegalTransition, transition_task_run


def test_task_run_cancel_allowed_before_terminal_and_rejected_after_terminal():
    """CREATED/RUNNING/WAITING_USER 可取消，终态不可回退。"""
    created = create_task_run("待取消任务", env_code="SIT1")
    assert transition_task_run(created, TaskRunStatus.CANCELLED).status == TaskRunStatus.CANCELLED

    running = create_task_run("运行中任务", env_code="SIT1")
    running = transition_task_run(running, TaskRunStatus.RUNNING)
    assert transition_task_run(running, TaskRunStatus.CANCELLED).status == TaskRunStatus.CANCELLED

    waiting = create_task_run("等待用户任务", env_code="SIT1")
    waiting = transition_task_run(waiting, TaskRunStatus.RUNNING)
    waiting.pending_question = "请确认。"
    waiting = transition_task_run(waiting, TaskRunStatus.WAITING_USER)
    assert transition_task_run(waiting, TaskRunStatus.CANCELLED).status == TaskRunStatus.CANCELLED

    failed = create_task_run("失败任务", env_code="SIT1")
    failed = transition_task_run(failed, TaskRunStatus.RUNNING)
    failed.failure_reason = "测试失败。"
    failed = transition_task_run(failed, TaskRunStatus.FAILED)
    with pytest.raises(IllegalTransition):
        transition_task_run(failed, TaskRunStatus.CANCELLED)

