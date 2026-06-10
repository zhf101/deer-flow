"""造数子任务业务服务层。

命名澄清：本模块（及 ``DatagenTaskSubagentType`` 枚举）是**子任务控制面/记录系统**，
用于任务分解、进度记录和审计载体——**不是通用子智能体调度系统**。
``SOURCE_ANALYSIS_AGENT`` / ``SCENE_VALIDATION_AGENT`` 等类型只是子任务的语义分类，
不会启动真实的子 Agent（没有 ``SubagentExecutor`` / ``task_tool`` 调用，也没有
父子 run、token 统计、取消、超时等执行协议）。若未来需要真实异步子智能体调度，
需另行设计完整协议，不应在本控制面上隐式扩展。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskSubtaskCreateRequest,
    DatagenTaskSubtaskIdRequest,
    DatagenTaskSubtaskResponse,
    DatagenTaskSubtaskStatus,
    DatagenTaskSubtaskUpdateRequest,
)
from app.gdp.datagen.config.task.repository import DatagenTaskConflictError, DatagenTaskNotFoundError
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_repository import (
    DatagenTaskSubtaskConflictError,
    DatagenTaskSubtaskRepository,
)

T = TypeVar("T")


class DatagenTaskSubtaskService:
    """造数子任务服务。"""

    def __init__(
        self,
        repository: DatagenTaskSubtaskRepository,
        task_service: DatagenTaskService,
    ) -> None:
        self._repo = repository
        self._task_service = task_service

    async def create_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskCreateRequest,
    ) -> DatagenTaskSubtaskResponse:
        subtask = await self._guard(lambda: self._repo.create_subtask(task_run_id, request))
        await self._task_service.record_event(
            task_run_id,
            event_type="SUBTASK_CREATED",
            phase=request.phase,
            message=f"已创建子任务 {subtask.subtaskId}。",
            payload=_subtask_event_payload(subtask),
        )
        return subtask

    async def list_subtasks(self, task_run_id: str) -> list[DatagenTaskSubtaskResponse]:
        return await self._guard(lambda: self._repo.list_subtasks(task_run_id))

    async def get_subtask(self, task_run_id: str, subtask_id: str) -> DatagenTaskSubtaskResponse:
        return await self._guard(lambda: self._repo.get_subtask(task_run_id, subtask_id))

    async def start_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskIdRequest,
    ) -> DatagenTaskSubtaskResponse:
        subtask = await self.update_subtask(
            task_run_id,
            DatagenTaskSubtaskUpdateRequest(
                subtaskId=request.subtaskId,
                status=DatagenTaskSubtaskStatus.RUNNING,
            ),
            event_type="SUBTASK_STARTED",
            message="子任务已开始执行。",
        )
        return subtask

    async def complete_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskUpdateRequest,
    ) -> DatagenTaskSubtaskResponse:
        request = request.model_copy(update={"status": DatagenTaskSubtaskStatus.SUCCESS})
        return await self.update_subtask(
            task_run_id,
            request,
            event_type="SUBTASK_COMPLETED",
            message="子任务已完成。",
        )

    async def fail_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskUpdateRequest,
    ) -> DatagenTaskSubtaskResponse:
        request = request.model_copy(update={"status": DatagenTaskSubtaskStatus.FAILED})
        return await self.update_subtask(
            task_run_id,
            request,
            event_type="SUBTASK_FAILED",
            message="子任务执行失败。",
        )

    async def cancel_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskIdRequest,
    ) -> DatagenTaskSubtaskResponse:
        return await self.update_subtask(
            task_run_id,
            DatagenTaskSubtaskUpdateRequest(
                subtaskId=request.subtaskId,
                status=DatagenTaskSubtaskStatus.CANCELLED,
            ),
            event_type="SUBTASK_CANCELLED",
            message="子任务已取消。",
        )

    async def update_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskUpdateRequest,
        *,
        event_type: str = "SUBTASK_UPDATED",
        message: str = "子任务已更新。",
    ) -> DatagenTaskSubtaskResponse:
        subtask = await self._guard(lambda: self._repo.update_subtask(task_run_id, request))
        await self._task_service.record_event(
            task_run_id,
            event_type=event_type,
            phase=subtask.phase,
            message=message,
            payload=_subtask_event_payload(subtask),
        )
        return subtask

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except DatagenTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (DatagenTaskConflictError, DatagenTaskSubtaskConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def _subtask_event_payload(subtask: DatagenTaskSubtaskResponse) -> dict:
    return {
        "subtaskId": subtask.subtaskId,
        "parentStepId": subtask.parentStepId,
        "phase": subtask.phase.value if isinstance(subtask.phase, DatagenTaskPhase) else str(subtask.phase),
        "subagentType": subtask.subagentType.value,
        "goal": subtask.goal,
        "operationId": subtask.operationId,
        "status": subtask.status.value,
        "resultSummary": subtask.resultSummary,
        "resultRef": subtask.resultRef,
        "errorType": subtask.errorType,
    }
