"""Agent 能力目录 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.gdp.datagen.agent_catalog.models import (
    AgentInfraResolveRequest,
    AgentInfraResolveResponse,
    AgentSceneContract,
    AgentSceneSearchRequest,
    AgentSceneSearchResponse,
    AgentSourceSearchRequest,
    AgentSourceSearchResponse,
)
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-agent-catalog"])


def _get_service() -> AgentCatalogService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return AgentCatalogService(
        scene_repository=SceneRepository(sf),
        http_source_repository=HttpSourceRepository(sf),
        sql_source_repository=SqlSourceRepository(sf),
        base_repository=BaseConfigRepository(sf),
    )


@router.post("/agent/catalog/scenes/search", response_model=AgentSceneSearchResponse)
async def search_scene_contracts(
    body: AgentSceneSearchRequest,
    service: AgentCatalogService = Depends(_get_service),
) -> AgentSceneSearchResponse:
    return await service.search_scene_contracts(body)


@router.get("/agent/catalog/scenes/{sceneCode}/contract", response_model=AgentSceneContract)
async def get_scene_contract(
    sceneCode: str,
    service: AgentCatalogService = Depends(_get_service),
) -> AgentSceneContract:
    return await service.get_scene_contract(sceneCode)


@router.post("/agent/catalog/sources/search", response_model=AgentSourceSearchResponse)
async def search_source_contracts(
    body: AgentSourceSearchRequest,
    service: AgentCatalogService = Depends(_get_service),
) -> AgentSourceSearchResponse:
    return await service.search_source_contracts(body)


@router.post("/agent/catalog/infra/resolve", response_model=AgentInfraResolveResponse)
async def resolve_infra_basis(
    body: AgentInfraResolveRequest,
    service: AgentCatalogService = Depends(_get_service),
) -> AgentInfraResolveResponse:
    return await service.resolve_infra_basis(body)
