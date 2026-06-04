"""Service layer for GDP data-factory management APIs."""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.models import (
    ConfigStatus,
    DatasourceConfig,
    DatasourceResponse,
    DisableResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    SceneDefinition,
    SceneStatus,
    SceneSummary,
    SceneVersion,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
    SqlTemplateConfig,
    SqlTemplateResponse,
    ValidationResult,
)
from app.gdp.persistence.repository import (
    DataFactoryConflictError,
    DataFactoryNotFoundError,
    DataFactoryRepository,
)
from app.gdp.validation import validate_draft, validate_publish


class DataFactoryService:
    def __init__(self, repository: DataFactoryRepository) -> None:
        self._repo = repository

    async def list_scenes(
        self,
        *,
        scene_type: str | None = None,
        status: SceneStatus | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SceneSummary]:
        return await self._repo.list_scenes(scene_type=scene_type, status=status, keyword=keyword, limit=limit, offset=offset)

    async def create_scene(self, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        result = validate_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._repo.create_scene(definition, operator=operator))

    async def update_scene(self, scene_code: str, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        result = validate_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._repo.update_scene(scene_code, definition, operator=operator))

    async def get_scene(self, scene_code: str) -> SceneDefinition:
        return await self._guard(lambda: self._repo.get_scene_definition(scene_code))

    async def validate_scene(self, scene_code: str) -> ValidationResult:
        scene = await self._guard(lambda: self._repo.validate_scene_saved(scene_code))
        templates = await self._enabled_templates_by_code()
        return validate_publish(scene, sql_templates_by_code=templates)

    async def publish_scene(self, scene_code: str, *, operator: str | None = None) -> SceneVersion:
        scene = await self._guard(lambda: self._repo.get_scene_definition(scene_code))
        templates = await self._enabled_templates_by_code()
        result = validate_publish(scene, sql_templates_by_code=templates)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._repo.publish_scene(scene_code, result, operator=operator))

    async def disable_scene(self, scene_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_scene(scene_code, operator=operator))
        return DisableResponse(success=True)

    async def delete_scene(self, scene_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_scene(scene_code, operator=operator))
        return DisableResponse(success=True)

    async def copy_scene(self, scene_code: str, target_scene_code: str, *, operator: str | None = None) -> SceneVersion:
        return await self._guard(lambda: self._repo.copy_scene(scene_code, target_scene_code, operator=operator))

    async def list_scene_versions(self, scene_code: str) -> list[SceneVersion]:
        return await self._guard(lambda: self._repo.list_scene_versions(scene_code))

    async def get_scene_version(self, scene_code: str, version_no: int) -> SceneVersion:
        return await self._guard(lambda: self._repo.get_scene_version(scene_code, version_no))

    async def list_environments(self) -> list[EnvironmentResponse]:
        return await self._repo.list_environments()

    async def upsert_environment(self, config: EnvironmentConfig) -> EnvironmentResponse:
        return await self._guard(lambda: self._repo.upsert_environment(config))

    async def list_service_endpoints(self, *, env_code: str | None = None) -> list[ServiceEndpointResponse]:
        return await self._repo.list_service_endpoints(env_code=env_code)

    async def create_service_endpoint(self, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.create_service_endpoint(config))

    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.update_service_endpoint(endpoint_id, config))

    async def list_datasources(self, *, env_code: str | None = None) -> list[DatasourceResponse]:
        return await self._repo.list_datasources(env_code=env_code)

    async def create_datasource(self, config: DatasourceConfig) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.create_datasource(config))

    async def update_datasource(self, datasource_id: str, config: DatasourceConfig) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.update_datasource(datasource_id, config))

    async def delete_environment(self, env_code: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_environment(env_code))
        return DisableResponse(success=True)

    async def delete_service_endpoint(self, endpoint_id: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_service_endpoint(endpoint_id))
        return DisableResponse(success=True)

    async def delete_datasource(self, datasource_id: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_datasource(datasource_id))
        return DisableResponse(success=True)

    async def list_sql_templates(self) -> list[SqlTemplateResponse]:
        return await self._repo.list_sql_templates()

    async def create_sql_template(self, template: SqlTemplateConfig, *, operator: str | None = None) -> SqlTemplateResponse:
        return await self._guard(lambda: self._repo.upsert_sql_template(template, operator=operator))

    async def get_sql_template(self, template_code: str) -> SqlTemplateResponse:
        return await self._guard(lambda: self._repo.get_sql_template(template_code))

    async def update_sql_template(
        self,
        template_code: str,
        template: SqlTemplateConfig,
        *,
        operator: str | None = None,
    ) -> SqlTemplateResponse:
        if template_code != template.templateCode:
            raise HTTPException(status_code=409, detail="path templateCode must match request templateCode")
        return await self._guard(lambda: self._repo.upsert_sql_template(template, operator=operator))

    async def disable_sql_template(self, template_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_sql_template(template_code, operator=operator))
        return DisableResponse(success=True)

    async def _enabled_templates_by_code(self) -> dict[str, SqlTemplateConfig]:
        templates = await self._repo.list_sql_templates(status=ConfigStatus.ENABLED)
        return {
            template.templateCode: SqlTemplateConfig.model_validate(template.model_dump(mode="json"))
            for template in templates
        }

    async def _guard(self, call):
        try:
            return await call()
        except DataFactoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DataFactoryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
