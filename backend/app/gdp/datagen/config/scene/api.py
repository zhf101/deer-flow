"""场景编排接口路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gdp.datagen.config.common.models import SceneStatus
from app.gdp.datagen.config.scene.factory import build_scene_service
from app.gdp.datagen.config.scene.models import (
    DisableResponse,
    SceneDefinition,
    SceneExecutionResult,
    SceneRunRequest,
    SceneRunSummary,
    SceneSummary,
    SceneVersion,
    ValidationResult,
)
from app.gdp.datagen.config.scene.service import SceneService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-scene"])


class SceneCodeRequest(BaseModel):
    """按场景编码执行操作的请求体。"""

    sceneCode: str = Field(..., min_length=1, max_length=128, description="场景唯一编码，用于定位要更新、删除或发布的场景。")


class SceneUpdateRequest(SceneCodeRequest):
    """更新场景定义请求。"""

    definition: SceneDefinition = Field(..., description="新的完整场景定义。")


def _get_service() -> SceneService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return build_scene_service(sf)


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/scenes", response_model=list[SceneSummary])
async def list_scenes(
    keyword: str = Query(default=""),
    status: SceneStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: SceneService = Depends(_get_service),
) -> list[SceneSummary]:
    return await service.list_scenes(keyword=keyword, status=status, limit=limit, offset=offset)


@router.post("/scenes", response_model=SceneVersion)
async def create_scene(
    body: SceneDefinition,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.create_scene(body, operator=operator)


@router.post("/scenes/run", response_model=SceneExecutionResult)
async def run_scene(
    body: SceneRunRequest,
    service: SceneService = Depends(_get_service),
) -> SceneExecutionResult:
    return await service.run_scene(body)


@router.get("/scenes/runs", response_model=list[SceneRunSummary])
async def list_scene_runs(
    sceneCode: str = Query(default=""),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: SceneService = Depends(_get_service),
) -> list[SceneRunSummary]:
    return await service.list_scene_runs(scene_code=sceneCode, status=status, limit=limit, offset=offset)


@router.get("/scenes/runs/{runId}", response_model=SceneExecutionResult)
async def get_scene_run(
    runId: str,
    service: SceneService = Depends(_get_service),
) -> SceneExecutionResult:
    return await service.get_scene_run(runId)


@router.get("/scenes/{sceneCode}", response_model=SceneDefinition)
async def get_scene(
    sceneCode: str,
    version_no: int | None = Query(default=None, alias="versionNo"),
    service: SceneService = Depends(_get_service),
) -> SceneDefinition:
    return await service.get_scene(sceneCode, version_no=version_no)


@router.get("/scenes/{sceneCode}/versions/current", response_model=SceneVersion)
async def get_current_scene_version(
    sceneCode: str,
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.get_scene_version(sceneCode)


@router.post("/scenes/update", response_model=SceneVersion)
async def update_scene(
    body: SceneUpdateRequest,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.update_scene(body.sceneCode, body.definition, operator=operator)


@router.post("/scenes/{sceneCode}/validate", response_model=ValidationResult)
async def validate_scene(
    sceneCode: str,
    service: SceneService = Depends(_get_service),
) -> ValidationResult:
    return await service.validate_scene(sceneCode)


@router.post("/scenes/{sceneCode}/publish", response_model=SceneVersion)
async def publish_scene(
    sceneCode: str,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.publish_scene(sceneCode, operator=operator)


@router.post("/scenes/delete", response_model=DisableResponse)
async def delete_scene(
    body: SceneCodeRequest,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> DisableResponse:
    return await service.delete_scene(body.sceneCode, operator=operator)
