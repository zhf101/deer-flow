"""造数任务 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.scene.repository import SceneRepository
from app.gdp.datagen.task.models import (
    DisableResponse,
    TaskDefinition,
    TaskSummary,
    TaskValidationResult,
    TaskVersion,
)
from app.gdp.datagen.task.repository import TaskRepository
from app.gdp.datagen.task.service import TaskService
from app.gdp.models import SceneStatus
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-task"])


def _get_service() -> TaskService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return TaskService(TaskRepository(sf), SceneRepository(sf))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user
    return await get_current_user(request)


@router.get("/tasks", response_model=list[TaskSummary])
async def list_tasks(
    keyword: str | None = None,
    status: SceneStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: TaskService = Depends(_get_service),
) -> list[TaskSummary]:
    return await service.list_tasks(keyword=keyword, status=status, limit=limit, offset=offset)


@router.post("/tasks", response_model=TaskVersion)
async def create_task(
    body: TaskDefinition,
    operator: str | None = Depends(_get_operator),
    service: TaskService = Depends(_get_service),
) -> TaskVersion:
    return await service.create_task(body, operator=operator)


@router.get("/tasks/{taskCode}", response_model=TaskDefinition)
async def get_task(taskCode: str, service: TaskService = Depends(_get_service)) -> TaskDefinition:
    return await service.get_task(taskCode)


@router.put("/tasks/{taskCode}", response_model=TaskVersion)
async def update_task(
    taskCode: str,
    body: TaskDefinition,
    operator: str | None = Depends(_get_operator),
    service: TaskService = Depends(_get_service),
) -> TaskVersion:
    return await service.update_task(taskCode, body, operator=operator)


@router.post("/tasks/{taskCode}/validate", response_model=TaskValidationResult)
async def validate_task(taskCode: str, service: TaskService = Depends(_get_service)) -> TaskValidationResult:
    return await service.validate_task(taskCode)


@router.post("/tasks/{taskCode}/publish", response_model=TaskVersion)
async def publish_task(
    taskCode: str,
    operator: str | None = Depends(_get_operator),
    service: TaskService = Depends(_get_service),
) -> TaskVersion:
    return await service.publish_task(taskCode, operator=operator)


@router.post("/tasks/{taskCode}/disable", response_model=DisableResponse)
async def disable_task(
    taskCode: str,
    operator: str | None = Depends(_get_operator),
    service: TaskService = Depends(_get_service),
) -> DisableResponse:
    await service.disable_task(taskCode, operator=operator)
    return DisableResponse(success=True)


@router.delete("/tasks/{taskCode}", response_model=DisableResponse)
async def delete_task(
    taskCode: str,
    operator: str | None = Depends(_get_operator),
    service: TaskService = Depends(_get_service),
) -> DisableResponse:
    await service.delete_task(taskCode, operator=operator)
    return DisableResponse(success=True)


@router.post("/tasks/{taskCode}/delete", response_model=DisableResponse)
async def delete_task_post(
    taskCode: str,
    operator: str | None = Depends(_get_operator),
    service: TaskService = Depends(_get_service),
) -> DisableResponse:
    await service.delete_task(taskCode, operator=operator)
    return DisableResponse(success=True)


@router.get("/tasks/{taskCode}/versions", response_model=list[TaskVersion])
async def list_task_versions(taskCode: str, service: TaskService = Depends(_get_service)) -> list[TaskVersion]:
    return await service.list_task_versions(taskCode)
