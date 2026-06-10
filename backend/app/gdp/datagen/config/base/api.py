"""造数基础配置 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    DatasourceResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    OperationResponse,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
    SysConfig,
    SysConfigResponse,
)
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.base.service import BaseConfigService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-base"])


class SysCodeRequest(BaseModel):
    """按系统编码执行操作的请求体。"""

    sysCode: str = Field(..., min_length=1, max_length=64, description="系统编码，用于定位要删除或操作的系统配置。")


class EnvCodeRequest(BaseModel):
    """按环境编码执行操作的请求体。"""

    envCode: str = Field(..., min_length=1, max_length=64, description="环境编码，用于定位要删除或操作的环境配置。")


class ServiceEndpointIdRequest(BaseModel):
    """按服务端点 ID 执行操作的请求体。"""

    endpointId: str = Field(..., min_length=1, max_length=64, description="服务端点数据库 ID，用于更新或删除指定服务端点。")


class ServiceEndpointUpdateRequest(ServiceEndpointIdRequest):
    """更新服务端点配置请求。"""

    config: ServiceEndpointConfig = Field(..., description="新的服务端点配置内容。")


class DatasourceIdRequest(BaseModel):
    """按数据源 ID 执行操作的请求体。"""

    datasourceId: str = Field(..., min_length=1, max_length=64, description="数据源数据库 ID，用于更新或删除指定数据源。")


class DatasourceUpdateRequest(DatasourceIdRequest):
    """更新数据源配置请求。"""

    config: DatasourceConfig = Field(..., description="新的数据源配置内容。")


def _get_service() -> BaseConfigService:
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return BaseConfigService(BaseConfigRepository(session_factory))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/systems", response_model=list[SysConfigResponse])
async def list_systems(service: BaseConfigService = Depends(_get_service)) -> list[SysConfigResponse]:
    return await service.list_systems()


@router.get("/systems/{sysCode}", response_model=SysConfigResponse)
async def get_system(
    sysCode: str,
    service: BaseConfigService = Depends(_get_service),
) -> SysConfigResponse:
    return await service.get_system(sysCode)


@router.post("/systems", response_model=SysConfigResponse)
async def save_system(
    body: SysConfig,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> SysConfigResponse:
    return await service.upsert_system(body, operator=operator)


@router.post("/systems/delete", response_model=OperationResponse)
async def delete_system(
    body: SysCodeRequest,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> OperationResponse:
    return await service.delete_system(body.sysCode, operator=operator)


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(service: BaseConfigService = Depends(_get_service)) -> list[EnvironmentResponse]:
    return await service.list_environments()


@router.get("/environments/{envCode}", response_model=EnvironmentResponse)
async def get_environment(
    envCode: str,
    service: BaseConfigService = Depends(_get_service),
) -> EnvironmentResponse:
    return await service.get_environment(envCode)


@router.post("/environments", response_model=EnvironmentResponse)
async def save_environment(
    body: EnvironmentConfig,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> EnvironmentResponse:
    return await service.upsert_environment(body, operator=operator)


@router.post("/environments/delete", response_model=OperationResponse)
async def delete_environment(
    body: EnvCodeRequest,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> OperationResponse:
    return await service.delete_environment(body.envCode, operator=operator)


@router.get("/service-endpoints", response_model=list[ServiceEndpointResponse])
async def list_service_endpoints(
    env_code: str | None = Query(default=None, alias="envCode"),
    sys_code: str | None = Query(default=None, alias="sysCode"),
    service: BaseConfigService = Depends(_get_service),
) -> list[ServiceEndpointResponse]:
    return await service.list_service_endpoints(env_code=env_code, sys_code=sys_code)


@router.post("/service-endpoints", response_model=ServiceEndpointResponse)
async def create_service_endpoint(
    body: ServiceEndpointConfig,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> ServiceEndpointResponse:
    return await service.create_service_endpoint(body, operator=operator)


@router.post("/service-endpoints/update", response_model=ServiceEndpointResponse)
async def update_service_endpoint(
    body: ServiceEndpointUpdateRequest,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> ServiceEndpointResponse:
    return await service.update_service_endpoint(body.endpointId, body.config, operator=operator)


@router.post("/service-endpoints/delete", response_model=OperationResponse)
async def delete_service_endpoint(
    body: ServiceEndpointIdRequest,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> OperationResponse:
    return await service.delete_service_endpoint(body.endpointId, operator=operator)


@router.get("/datasources", response_model=list[DatasourceResponse])
async def list_datasources(
    env_code: str | None = Query(default=None, alias="envCode"),
    sys_code: str | None = Query(default=None, alias="sysCode"),
    service: BaseConfigService = Depends(_get_service),
) -> list[DatasourceResponse]:
    return await service.list_datasources(env_code=env_code, sys_code=sys_code)


@router.post("/datasources", response_model=DatasourceResponse)
async def create_datasource(
    body: DatasourceConfig,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> DatasourceResponse:
    return await service.create_datasource(body, operator=operator)


@router.post("/datasources/update", response_model=DatasourceResponse)
async def update_datasource(
    body: DatasourceUpdateRequest,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> DatasourceResponse:
    return await service.update_datasource(body.datasourceId, body.config, operator=operator)


@router.post("/datasources/delete", response_model=OperationResponse)
async def delete_datasource(
    body: DatasourceIdRequest,
    operator: str | None = Depends(_get_operator),
    service: BaseConfigService = Depends(_get_service),
) -> OperationResponse:
    return await service.delete_datasource(body.datasourceId, operator=operator)
