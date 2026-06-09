"""场景编排业务服务层。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.common.models import SceneStatus
from app.gdp.datagen.config.scene.executor import SceneExecutor
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
from app.gdp.datagen.config.scene.repository import (
    SceneConflictError,
    SceneNotFoundError,
    SceneRepository,
    SceneVersionConflictError,
)
from app.gdp.datagen.config.scene.validation import validate_scene_draft, validate_scene_publish

T = TypeVar("T")


class SceneService:
    """场景配置服务。"""

    def __init__(self, repository: SceneRepository, executor: SceneExecutor | None = None) -> None:
        self._repo = repository
        self._executor = executor

    async def list_scenes(
        self,
        *,
        keyword: str = "",
        status: SceneStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SceneSummary]:
        return await self._repo.list_scenes(keyword=keyword, status=status, limit=limit, offset=offset)

    async def create_scene(self, scene: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        self._raise_if_invalid(validate_scene_draft(scene))
        return await self._guard(lambda: self._repo.create_scene(scene, operator=operator))

    async def get_scene(self, scene_code: str, *, version_no: int | None = None) -> SceneDefinition:
        version = await self._guard(lambda: self._repo.get_scene(scene_code, version_no=version_no))
        return version.definition

    async def get_scene_version(self, scene_code: str, *, version_no: int | None = None) -> SceneVersion:
        return await self._guard(lambda: self._repo.get_scene(scene_code, version_no=version_no))

    async def update_scene(self, scene_code: str, scene: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        self._raise_if_invalid(validate_scene_draft(scene))
        return await self._guard(lambda: self._repo.update_scene(scene_code, scene, operator=operator))

    async def validate_scene(self, scene_code: str) -> ValidationResult:
        version = await self._guard(lambda: self._repo.get_scene(scene_code))
        return validate_scene_publish(version.definition)

    async def publish_scene(self, scene_code: str, *, operator: str | None = None) -> SceneVersion:
        version = await self._guard(lambda: self._repo.get_scene(scene_code))
        validation_result = validate_scene_publish(version.definition)
        self._raise_if_invalid(validation_result)
        return await self._guard(lambda: self._repo.publish_scene(scene_code, validation_result, operator=operator))

    async def delete_scene(self, scene_code: str, *, operator: str | None = None) -> DisableResponse:
        # 预留接口语义，当前无物理删除实现，避免误删已发布快照。
        raise HTTPException(status_code=501, detail=f"scene delete is not implemented: {scene_code}")

    async def run_scene(self, request: SceneRunRequest) -> SceneExecutionResult:
        if self._executor is None:
            raise HTTPException(status_code=503, detail="Scene executor not available")
        version = await self._guard(lambda: self._repo.get_published_scene(request.sceneCode))
        result = await self._executor.run(version, request)
        return await self._guard(lambda: self._repo.save_scene_run(result))

    async def get_scene_run(self, run_id: str) -> SceneExecutionResult:
        return await self._guard(lambda: self._repo.get_scene_run(run_id))

    async def list_scene_runs(
        self,
        *,
        scene_code: str = "",
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SceneRunSummary]:
        return await self._repo.list_scene_runs(scene_code=scene_code, status=status, limit=limit, offset=offset)

    @staticmethod
    def _raise_if_invalid(result: ValidationResult) -> None:
        if result.valid:
            return
        raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except SceneNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SceneConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SceneVersionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
