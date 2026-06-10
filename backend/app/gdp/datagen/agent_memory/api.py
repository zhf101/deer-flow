"""GDP Agent 记忆 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.agent_memory.models import (
    GDPAgentMemoryCategory,
    GDPAgentMemoryFactCreateRequest,
    GDPAgentMemoryFactIdRequest,
    GDPAgentMemoryFactResponse,
    GDPAgentMemoryFactUpdateRequest,
    GDPAgentMemoryReloadResponse,
    GDPAgentMemoryScopeType,
    GDPAgentMemoryStatus,
)
from app.gdp.datagen.agent_memory.repository import GDPAgentMemoryRepository
from app.gdp.datagen.agent_memory.service import GDPAgentMemoryService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-agent-memory"])


def _get_service() -> GDPAgentMemoryService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return GDPAgentMemoryService(GDPAgentMemoryRepository(sf))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/agent-memory/facts", response_model=list[GDPAgentMemoryFactResponse])
async def list_memory_facts(
    user_id: str | None = Query(default=None, alias="userId"),
    agent_name: str | None = Query(default="gdp_agent", alias="agentName"),
    category: GDPAgentMemoryCategory | None = Query(default=None),
    scope_type: GDPAgentMemoryScopeType | None = Query(default=None, alias="scopeType"),
    scope_key: str | None = Query(default=None, alias="scopeKey"),
    status: GDPAgentMemoryStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: GDPAgentMemoryService = Depends(_get_service),
) -> list[GDPAgentMemoryFactResponse]:
    return await service.list_facts(
        user_id=user_id,
        agent_name=agent_name,
        category=category,
        scope_type=scope_type,
        scope_key=scope_key,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/agent-memory/facts/create", response_model=GDPAgentMemoryFactResponse)
async def create_memory_fact(
    body: GDPAgentMemoryFactCreateRequest,
    operator: str | None = Depends(_get_operator),
    service: GDPAgentMemoryService = Depends(_get_service),
) -> GDPAgentMemoryFactResponse:
    if operator and body.userId is None and body.scopeType == GDPAgentMemoryScopeType.USER:
        body = body.model_copy(update={"userId": operator, "scopeKey": operator})
    return await service.create_fact(body)


@router.post("/agent-memory/facts/update", response_model=GDPAgentMemoryFactResponse)
async def update_memory_fact(
    body: GDPAgentMemoryFactUpdateRequest,
    service: GDPAgentMemoryService = Depends(_get_service),
) -> GDPAgentMemoryFactResponse:
    return await service.update_fact(body)


@router.post("/agent-memory/facts/disable", response_model=GDPAgentMemoryFactResponse)
async def disable_memory_fact(
    body: GDPAgentMemoryFactIdRequest,
    service: GDPAgentMemoryService = Depends(_get_service),
) -> GDPAgentMemoryFactResponse:
    return await service.disable_fact(body)


@router.post("/agent-memory/facts/delete", response_model=GDPAgentMemoryReloadResponse)
async def delete_memory_fact(
    body: GDPAgentMemoryFactIdRequest,
    service: GDPAgentMemoryService = Depends(_get_service),
) -> GDPAgentMemoryReloadResponse:
    return await service.delete_fact(body)


@router.post("/agent-memory/reload", response_model=GDPAgentMemoryReloadResponse)
async def reload_memory(
    service: GDPAgentMemoryService = Depends(_get_service),
) -> GDPAgentMemoryReloadResponse:
    return await service.reload()
