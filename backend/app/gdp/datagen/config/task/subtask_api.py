"""造数子任务 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.gdp.datagen.config.task.models import (
    DatagenTaskSubtaskCreateRequest,
    DatagenTaskSubtaskIdRequest,
    DatagenTaskSubtaskResponse,
    DatagenTaskSubtaskUpdateRequest,
)
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_repository import DatagenTaskSubtaskRepository
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-task-subtask"])


def _get_service() -> DatagenTaskSubtaskService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    task_service = DatagenTaskService(DatagenTaskRepository(sf))
    return DatagenTaskSubtaskService(DatagenTaskSubtaskRepository(sf), task_service)


@router.get("/tasks/runs/{taskRunId}/subtasks", response_model=list[DatagenTaskSubtaskResponse])
async def list_task_subtasks(
    taskRunId: str,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> list[DatagenTaskSubtaskResponse]:
    return await service.list_subtasks(taskRunId)


@router.get("/tasks/runs/{taskRunId}/subtasks/{subtaskId}", response_model=DatagenTaskSubtaskResponse)
async def get_task_subtask(
    taskRunId: str,
    subtaskId: str,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.get_subtask(taskRunId, subtaskId)


@router.post("/tasks/runs/{taskRunId}/subtasks", response_model=DatagenTaskSubtaskResponse)
async def create_task_subtask(
    taskRunId: str,
    body: DatagenTaskSubtaskCreateRequest,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.create_subtask(taskRunId, body)


@router.post("/tasks/runs/{taskRunId}/subtasks/start", response_model=DatagenTaskSubtaskResponse)
async def start_task_subtask(
    taskRunId: str,
    body: DatagenTaskSubtaskIdRequest,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.start_subtask(taskRunId, body)


@router.post("/tasks/runs/{taskRunId}/subtasks/update", response_model=DatagenTaskSubtaskResponse)
async def update_task_subtask(
    taskRunId: str,
    body: DatagenTaskSubtaskUpdateRequest,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.update_subtask(taskRunId, body)


@router.post("/tasks/runs/{taskRunId}/subtasks/complete", response_model=DatagenTaskSubtaskResponse)
async def complete_task_subtask(
    taskRunId: str,
    body: DatagenTaskSubtaskUpdateRequest,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.complete_subtask(taskRunId, body)


@router.post("/tasks/runs/{taskRunId}/subtasks/fail", response_model=DatagenTaskSubtaskResponse)
async def fail_task_subtask(
    taskRunId: str,
    body: DatagenTaskSubtaskUpdateRequest,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.fail_subtask(taskRunId, body)


@router.post("/tasks/runs/{taskRunId}/subtasks/cancel", response_model=DatagenTaskSubtaskResponse)
async def cancel_task_subtask(
    taskRunId: str,
    body: DatagenTaskSubtaskIdRequest,
    service: DatagenTaskSubtaskService = Depends(_get_service),
) -> DatagenTaskSubtaskResponse:
    return await service.cancel_subtask(taskRunId, body)
