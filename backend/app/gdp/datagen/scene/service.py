"""造数场景业务逻辑层。"""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.datagen.httpsource.models import HttpSourceConfig
from app.gdp.datagen.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.scene.models import (
    SceneDefinition,
    SceneSummary,
    SceneVersion,
    ValidationResult,
)
from app.gdp.datagen.scene.repository import (
    SceneConflictError,
    SceneNotFoundError,
    SceneRepository,
)
from app.gdp.datagen.scene.validation import validate_draft, validate_publish
from app.gdp.datagen.sqlsource.models import SqlSourceConfig
from app.gdp.datagen.sqlsource.repository import SqlSourceRepository
from app.gdp.models import ConfigStatus, SceneStatus


class SceneService:
    def __init__(
        self,
        scene_repo: SceneRepository,
        http_source_repo: HttpSourceRepository,
        sql_source_repo: SqlSourceRepository,
    ) -> None:
        self._scene_repo = scene_repo
        self._http_repo = http_source_repo
        self._sql_repo = sql_source_repo

    async def list_scenes(
        self, *, scene_type: str | None = None, status: SceneStatus | None = None,
        keyword: str | None = None, limit: int = 100, offset: int = 0,
    ) -> list[SceneSummary]:
        return await self._scene_repo.list_scenes(
            scene_type=scene_type, status=status, keyword=keyword, limit=limit, offset=offset
        )

    async def create_scene(self, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        result = validate_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._scene_repo.create_scene(definition, operator=operator))

    async def get_scene(self, scene_code: str) -> SceneDefinition:
        return await self._guard(lambda: self._scene_repo.get_scene_definition(scene_code))

    async def update_scene(self, scene_code: str, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        result = validate_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._scene_repo.update_scene(scene_code, definition, operator=operator))

    async def validate_scene(self, scene_code: str) -> ValidationResult:
        scene = await self._guard(lambda: self._scene_repo.get_scene_definition(scene_code))
        http_sources = await self._enabled_http_sources()
        sql_sources = await self._enabled_sql_sources()
        return validate_publish(scene, http_sources_by_code=http_sources, sql_sources_by_code=sql_sources)

    async def publish_scene(self, scene_code: str, *, operator: str | None = None) -> SceneVersion:
        scene = await self._guard(lambda: self._scene_repo.get_scene_definition(scene_code))
        http_sources = await self._enabled_http_sources()
        sql_sources = await self._enabled_sql_sources()
        result = validate_publish(scene, http_sources_by_code=http_sources, sql_sources_by_code=sql_sources)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._scene_repo.publish_scene(scene_code, result, operator=operator))

    async def run_scene(self, scene_code: str, request: "ExecutionRequest") -> "ExecutionResult":
        from app.gdp.engine.executor import SceneExecutor
        from app.gdp.engine.models import ExecutionRequest, ExecutionResult

        executor = SceneExecutor(self._scene_repo._sf)
        return await executor.execute(scene_code, request)

    async def disable_scene(self, scene_code: str, *, operator: str | None = None) -> bool:
        return await self._guard(lambda: self._scene_repo.disable_scene(scene_code, operator=operator))

    async def delete_scene(self, scene_code: str, *, operator: str | None = None) -> bool:
        return await self._guard(lambda: self._scene_repo.delete_scene(scene_code, operator=operator))

    async def copy_scene(self, scene_code: str, target_scene_code: str, *, operator: str | None = None) -> SceneVersion:
        return await self._guard(lambda: self._scene_repo.copy_scene(scene_code, target_scene_code, operator=operator))

    async def list_scene_versions(self, scene_code: str) -> list[SceneVersion]:
        return await self._guard(lambda: self._scene_repo.list_scene_versions(scene_code))

    async def get_scene_version(self, scene_code: str, version_no: int) -> SceneVersion:
        return await self._guard(lambda: self._scene_repo.get_scene_version(scene_code, version_no))

    # ---------- 内部辅助 ----------

    async def _enabled_http_sources(self) -> dict[str, HttpSourceConfig]:
        sources = await self._http_repo.list_http_sources(status=ConfigStatus.ENABLED)
        return {s.sourceCode: HttpSourceConfig.model_validate(s.model_dump(mode="json")) for s in sources}

    async def _enabled_sql_sources(self) -> dict[str, SqlSourceConfig]:
        sources = await self._sql_repo.list_sql_sources(status=ConfigStatus.ENABLED)
        return {s.sourceCode: SqlSourceConfig.model_validate(s.model_dump(mode="json")) for s in sources}

    async def _guard(self, call):
        try:
            return await call()
        except SceneNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SceneConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
