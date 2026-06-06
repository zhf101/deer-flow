"""造数场景 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.scene.models import (
    SceneDefinition,
    SceneSummary,
    SceneVersion,
    ValidationResult,
)
from app.gdp.datagen.scene.repository import SceneRepository
from app.gdp.datagen.scene.service import SceneService
from app.gdp.datagen.sqlsource.repository import SqlSourceRepository
from app.gdp.engine.models import ExecutionRequest, ExecutionResult
from app.gdp.models import SceneStatus
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-scene"])


def _get_service() -> SceneService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return SceneService(SceneRepository(sf), HttpSourceRepository(sf), SqlSourceRepository(sf))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user
    return await get_current_user(request)


@router.get("/scenes", response_model=list[SceneSummary])
async def list_scenes(
    scene_type: str | None = Query(default=None, alias="sceneType"),
    status: SceneStatus | None = None,
    keyword: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: SceneService = Depends(_get_service),
) -> list[SceneSummary]:
    return await service.list_scenes(scene_type=scene_type, status=status, keyword=keyword, limit=limit, offset=offset)


@router.post("/scenes", response_model=SceneVersion)
async def create_scene(
    body: SceneDefinition,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.create_scene(body, operator=operator)


@router.get("/scenes/{sceneCode}", response_model=SceneDefinition)
async def get_scene(sceneCode: str, service: SceneService = Depends(_get_service)) -> SceneDefinition:
    return await service.get_scene(sceneCode)


@router.put("/scenes/{sceneCode}", response_model=SceneVersion)
async def update_scene(
    sceneCode: str,
    body: SceneDefinition,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.update_scene(sceneCode, body, operator=operator)


@router.post("/scenes/{sceneCode}/validate", response_model=ValidationResult)
async def validate_scene(sceneCode: str, service: SceneService = Depends(_get_service)) -> ValidationResult:
    return await service.validate_scene(sceneCode)


@router.post("/scenes/{sceneCode}/publish", response_model=SceneVersion)
async def publish_scene(
    sceneCode: str,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.publish_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/run")
async def run_scene(sceneCode: str, body: ExecutionRequest, service: SceneService = Depends(_get_service)) -> ExecutionResult:
    return await service.run_scene(sceneCode, body)


@router.post("/scenes/{sceneCode}/disable", response_model=bool)
async def disable_scene(
    sceneCode: str,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> bool:
    return await service.disable_scene(sceneCode, operator=operator)


@router.delete("/scenes/{sceneCode}", response_model=bool)
async def delete_scene(
    sceneCode: str,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> bool:
    return await service.delete_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/delete", response_model=bool)
async def delete_scene_post(
    sceneCode: str,
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> bool:
    return await service.delete_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/copy", response_model=SceneVersion)
async def copy_scene(
    sceneCode: str,
    targetSceneCode: str = Query(..., alias="targetSceneCode"),
    operator: str | None = Depends(_get_operator),
    service: SceneService = Depends(_get_service),
) -> SceneVersion:
    return await service.copy_scene(sceneCode, targetSceneCode, operator=operator)


@router.get("/scenes/{sceneCode}/versions", response_model=list[SceneVersion])
async def list_scene_versions(sceneCode: str, service: SceneService = Depends(_get_service)) -> list[SceneVersion]:
    return await service.list_scene_versions(sceneCode)


@router.get("/scenes/{sceneCode}/versions/{versionNo}", response_model=SceneVersion)
async def get_scene_version(sceneCode: str, versionNo: int, service: SceneService = Depends(_get_service)) -> SceneVersion:
    return await service.get_scene_version(sceneCode, versionNo)
