"""GDP Agent 子任务中间件工具。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskSubagentType,
    DatagenTaskSubtaskCreateRequest,
    DatagenTaskSubtaskIdRequest,
    DatagenTaskSubtaskUpdateRequest,
)
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService


async def create_gdp_subtask(
    subtask_service: DatagenTaskSubtaskService,
    *,
    task_run_id: str,
    phase: DatagenTaskPhase,
    subagent_type: DatagenTaskSubagentType,
    goal: str,
    input_snapshot: dict[str, Any] | None = None,
    parent_step_id: str | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """创建 GDP 子任务并返回轻量引用。"""

    subtask = await subtask_service.create_subtask(
        task_run_id,
        DatagenTaskSubtaskCreateRequest(
            parentStepId=parent_step_id,
            phase=phase,
            subagentType=subagent_type,
            goal=goal,
            operationId=operation_id,
            inputSnapshot=input_snapshot or {},
        ),
    )
    return _subtask_ref(subtask.model_dump(mode="json"))


async def start_gdp_subtask(
    subtask_service: DatagenTaskSubtaskService,
    *,
    task_run_id: str,
    subtask_id: str,
) -> dict[str, Any]:
    """标记 GDP 子任务开始执行。"""

    subtask = await subtask_service.start_subtask(task_run_id, DatagenTaskSubtaskIdRequest(subtaskId=subtask_id))
    return _subtask_ref(subtask.model_dump(mode="json"))


async def complete_gdp_subtask(
    subtask_service: DatagenTaskSubtaskService,
    *,
    task_run_id: str,
    subtask_id: str,
    result_summary: dict[str, Any],
    result_payload: dict[str, Any] | None = None,
    result_ref: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """完成 GDP 子任务并返回可归并到父任务的轻量引用。"""

    subtask = await subtask_service.complete_subtask(
        task_run_id,
        DatagenTaskSubtaskUpdateRequest(
            subtaskId=subtask_id,
            resultSummary=result_summary,
            resultPayload=result_payload,
            resultRef=result_ref,
            tokenUsage=token_usage,
        ),
    )
    return _subtask_ref(subtask.model_dump(mode="json"))


async def fail_gdp_subtask(
    subtask_service: DatagenTaskSubtaskService,
    *,
    task_run_id: str,
    subtask_id: str,
    error_type: str,
    error_message: str,
    result_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """标记 GDP 子任务失败并返回轻量引用。"""

    subtask = await subtask_service.fail_subtask(
        task_run_id,
        DatagenTaskSubtaskUpdateRequest(
            subtaskId=subtask_id,
            errorType=error_type,
            errorMessage=error_message,
            resultRef=result_ref,
        ),
    )
    return _subtask_ref(subtask.model_dump(mode="json"))


def _subtask_ref(subtask: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_type": "SUBTASK",
        "task_run_id": subtask["taskRunId"],
        "subtask_id": subtask["subtaskId"],
        "phase": subtask["phase"],
        "subagent_type": subtask["subagentType"],
        "status": subtask["status"],
        "summary": {
            "goal": subtask["goal"],
            "operationId": subtask.get("operationId"),
            "resultSummary": subtask.get("resultSummary"),
            "resultRef": subtask.get("resultRef"),
            "errorType": subtask.get("errorType"),
        },
    }
