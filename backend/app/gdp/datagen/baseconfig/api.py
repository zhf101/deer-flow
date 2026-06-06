"""基础配置 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.baseconfig.models import (
    DatasourceConfig,
    DatasourceResponse,
    DisableResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
)
from app.gdp.datagen.baseconfig.repository import BaseConfigRepository
from app.gdp.datagen.baseconfig.service import BaseConfigService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-baseconfig"])


def _get_service() -> BaseConfigService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return BaseConfigService(BaseConfigRepository(sf))


# ── 环境 ──────────────────────────────────────────────────────────────


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(service: BaseConfigService = Depends(_get_service)) -> list[EnvironmentResponse]:
    return await service.list_environments()


@router.post("/environments", response_model=EnvironmentResponse)
async def create_environment(body: EnvironmentConfig, service: BaseConfigService = Depends(_get_service)) -> EnvironmentResponse:
    return await service.upsert_environment(body)


@router.put("/environments/{envCode}", response_model=EnvironmentResponse)
async def update_environment(envCode: str, body: EnvironmentConfig, service: BaseConfigService = Depends(_get_service)) -> EnvironmentResponse:
    if envCode != body.envCode:
        raise HTTPException(status_code=409, detail="path envCode must match request envCode")
    return await service.upsert_environment(body)


@router.delete("/environments/{envCode}", response_model=DisableResponse)
async def delete_environment(envCode: str, service: BaseConfigService = Depends(_get_service)) -> DisableResponse:
    return await service.delete_environment(envCode)


# ── 服务端点 ──────────────────────────────────────────────────────────


@router.get("/service-endpoints", response_model=list[ServiceEndpointResponse])
async def list_service_endpoints(
    env_code: str | None = Query(default=None, alias="envCode"),
    service: BaseConfigService = Depends(_get_service),
) -> list[ServiceEndpointResponse]:
    return await service.list_service_endpoints(env_code=env_code)


@router.post("/service-endpoints", response_model=ServiceEndpointResponse)
async def create_service_endpoint(body: ServiceEndpointConfig, service: BaseConfigService = Depends(_get_service)) -> ServiceEndpointResponse:
    return await service.create_service_endpoint(body)


@router.put("/service-endpoints/{endpointId}", response_model=ServiceEndpointResponse)
async def update_service_endpoint(endpointId: str, body: ServiceEndpointConfig, service: BaseConfigService = Depends(_get_service)) -> ServiceEndpointResponse:
    return await service.update_service_endpoint(endpointId, body)


@router.delete("/service-endpoints/{endpointId}", response_model=DisableResponse)
async def delete_service_endpoint(endpointId: str, service: BaseConfigService = Depends(_get_service)) -> DisableResponse:
    return await service.delete_service_endpoint(endpointId)


# ── 数据源 ────────────────────────────────────────────────────────────


@router.get("/datasources", response_model=list[DatasourceResponse])
async def list_datasources(
    env_code: str | None = Query(default=None, alias="envCode"),
    service: BaseConfigService = Depends(_get_service),
) -> list[DatasourceResponse]:
    return await service.list_datasources(env_code=env_code)


@router.post("/datasources", response_model=DatasourceResponse)
async def create_datasource(body: DatasourceConfig, service: BaseConfigService = Depends(_get_service)) -> DatasourceResponse:
    return await service.create_datasource(body)


@router.put("/datasources/{datasourceId}", response_model=DatasourceResponse)
async def update_datasource(datasourceId: str, body: DatasourceConfig, service: BaseConfigService = Depends(_get_service)) -> DatasourceResponse:
    return await service.update_datasource(datasourceId, body)


@router.delete("/datasources/{datasourceId}", response_model=DisableResponse)
async def delete_datasource(datasourceId: str, service: BaseConfigService = Depends(_get_service)) -> DisableResponse:
    return await service.delete_datasource(datasourceId)
