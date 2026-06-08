"""场景编排 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.config.common.models import SceneStatus
from app.gdp.datagen.config.scene.models import SceneDefinition, SceneSummary, SceneVersion, ValidationResult
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-scene"])


def _get_service() -> SceneService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return SceneService(SceneRepository(sf))


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


@router.put("/scenes/{sceneCode}", response_model=SceneVersion)
async def update_scene(
    sceneCode: str,
    body: SceneDefinition,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.update_scene(sceneCode, body, operator=operator)


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
