"""FastAPI router for GDP data-factory management APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.models import (
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
from app.gdp.persistence.repository import DataFactoryRepository
from app.gdp.service import DataFactoryService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(prefix="/api/v1/data-factory", tags=["data-factory"])


def get_data_factory_service() -> DataFactoryService:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Data factory persistence not available")
    return DataFactoryService(DataFactoryRepository(session_factory))


async def get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/scenes", response_model=list[SceneSummary])
async def list_scenes(
    scene_type: str | None = Query(default=None, alias="sceneType"),
    status: SceneStatus | None = None,
    keyword: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[SceneSummary]:
    return await service.list_scenes(scene_type=scene_type, status=status, keyword=keyword, limit=limit, offset=offset)


@router.post("/scenes", response_model=SceneVersion)
async def create_scene(
    body: SceneDefinition,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    return await service.create_scene(body, operator=operator)


@router.get("/scenes/{sceneCode}", response_model=SceneDefinition)
async def get_scene(
    sceneCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneDefinition:
    return await service.get_scene(sceneCode)


@router.put("/scenes/{sceneCode}", response_model=SceneVersion)
async def update_scene(
    sceneCode: str,
    body: SceneDefinition,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    return await service.update_scene(sceneCode, body, operator=operator)


@router.post("/scenes/{sceneCode}/validate", response_model=ValidationResult)
async def validate_scene(
    sceneCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ValidationResult:
    return await service.validate_scene(sceneCode)


@router.post("/scenes/{sceneCode}/publish", response_model=SceneVersion)
async def publish_scene(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    return await service.publish_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/disable", response_model=DisableResponse)
async def disable_scene(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.disable_scene(sceneCode, operator=operator)


@router.delete("/scenes/{sceneCode}", response_model=DisableResponse)
async def delete_scene(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.delete_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/delete", response_model=DisableResponse)
async def delete_scene_post(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.delete_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/copy", response_model=SceneVersion)
async def copy_scene(
    sceneCode: str,
    targetSceneCode: str = Query(..., alias="targetSceneCode"),
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    return await service.copy_scene(sceneCode, targetSceneCode, operator=operator)


@router.get("/scenes/{sceneCode}/versions", response_model=list[SceneVersion])
async def list_scene_versions(
    sceneCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[SceneVersion]:
    return await service.list_scene_versions(sceneCode)


@router.get("/scenes/{sceneCode}/versions/{versionNo}", response_model=SceneVersion)
async def get_scene_version(
    sceneCode: str,
    versionNo: int,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    return await service.get_scene_version(sceneCode, versionNo)


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[EnvironmentResponse]:
    return await service.list_environments()


@router.post("/environments", response_model=EnvironmentResponse)
async def create_environment(
    body: EnvironmentConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> EnvironmentResponse:
    return await service.upsert_environment(body)


@router.put("/environments/{envCode}", response_model=EnvironmentResponse)
async def update_environment(
    envCode: str,
    body: EnvironmentConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> EnvironmentResponse:
    if envCode != body.envCode:
        raise HTTPException(status_code=409, detail="path envCode must match request envCode")
    return await service.upsert_environment(body)


@router.delete("/environments/{envCode}", response_model=DisableResponse)
async def delete_environment(
    envCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.delete_environment(envCode)


@router.get("/service-endpoints", response_model=list[ServiceEndpointResponse])
async def list_service_endpoints(
    env_code: str | None = Query(default=None, alias="envCode"),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[ServiceEndpointResponse]:
    return await service.list_service_endpoints(env_code=env_code)


@router.post("/service-endpoints", response_model=ServiceEndpointResponse)
async def create_service_endpoint(
    body: ServiceEndpointConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ServiceEndpointResponse:
    return await service.create_service_endpoint(body)


@router.put("/service-endpoints/{endpointId}", response_model=ServiceEndpointResponse)
async def update_service_endpoint(
    endpointId: str,
    body: ServiceEndpointConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ServiceEndpointResponse:
    return await service.update_service_endpoint(endpointId, body)


@router.delete("/service-endpoints/{endpointId}", response_model=DisableResponse)
async def delete_service_endpoint(
    endpointId: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.delete_service_endpoint(endpointId)


@router.get("/datasources", response_model=list[DatasourceResponse])
async def list_datasources(
    env_code: str | None = Query(default=None, alias="envCode"),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[DatasourceResponse]:
    return await service.list_datasources(env_code=env_code)


@router.post("/datasources", response_model=DatasourceResponse)
async def create_datasource(
    body: DatasourceConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DatasourceResponse:
    return await service.create_datasource(body)


@router.put("/datasources/{datasourceId}", response_model=DatasourceResponse)
async def update_datasource(
    datasourceId: str,
    body: DatasourceConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DatasourceResponse:
    return await service.update_datasource(datasourceId, body)


@router.delete("/datasources/{datasourceId}", response_model=DisableResponse)
async def delete_datasource(
    datasourceId: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.delete_datasource(datasourceId)


@router.get("/sql-templates", response_model=list[SqlTemplateResponse])
async def list_sql_templates(
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[SqlTemplateResponse]:
    return await service.list_sql_templates()


@router.post("/sql-templates", response_model=SqlTemplateResponse)
async def create_sql_template(
    body: SqlTemplateConfig,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SqlTemplateResponse:
    return await service.create_sql_template(body, operator=operator)


@router.get("/sql-templates/{templateCode}", response_model=SqlTemplateResponse)
async def get_sql_template(
    templateCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SqlTemplateResponse:
    return await service.get_sql_template(templateCode)


@router.put("/sql-templates/{templateCode}", response_model=SqlTemplateResponse)
async def update_sql_template(
    templateCode: str,
    body: SqlTemplateConfig,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SqlTemplateResponse:
    return await service.update_sql_template(templateCode, body, operator=operator)


@router.post("/sql-templates/{templateCode}/disable", response_model=DisableResponse)
async def disable_sql_template(
    templateCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    return await service.disable_sql_template(templateCode, operator=operator)
