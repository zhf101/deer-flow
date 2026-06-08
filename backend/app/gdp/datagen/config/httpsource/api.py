"""HTTP 源 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.httpsource.models import (
    DisableResponse,
    HttpSourceConfig,
    HttpSourceResponse,
    HttpSourceTestRequest,
    HttpSourceTestResponse,
)
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-httpsource"])


def _get_service() -> HttpSourceService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return HttpSourceService(HttpSourceRepository(sf), BaseConfigRepository(sf))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/http-sources", response_model=list[HttpSourceResponse])
async def list_http_sources(
    sys_code: str | None = Query(default=None, alias="sysCode"),
    service: HttpSourceService = Depends(_get_service),
) -> list[HttpSourceResponse]:
    return await service.list_http_sources(sys_code=sys_code)


@router.post("/http-sources", response_model=HttpSourceResponse)
async def create_http_source(
    body: HttpSourceConfig,
    operator: str | None = Depends(_get_operator),
    service: HttpSourceService = Depends(_get_service),
) -> HttpSourceResponse:
    return await service.upsert_http_source(body, operator=operator)


@router.post("/http-sources/test", response_model=HttpSourceTestResponse)
async def test_http_source(
    body: HttpSourceTestRequest,
    service: HttpSourceService = Depends(_get_service),
) -> HttpSourceTestResponse:
    return await service.test_http_source(body)


@router.get("/http-sources/{sourceCode}", response_model=HttpSourceResponse)
async def get_http_source(
    sourceCode: str,
    service: HttpSourceService = Depends(_get_service),
) -> HttpSourceResponse:
    return await service.get_http_source(sourceCode)


@router.post("/http-sources/update", response_model=HttpSourceResponse)
async def update_http_source(
    body: HttpSourceConfig,
    operator: str | None = Depends(_get_operator),
    service: HttpSourceService = Depends(_get_service),
) -> HttpSourceResponse:
    return await service.upsert_http_source(body, operator=operator)


@router.post("/http-sources/{sourceCode}/disable", response_model=DisableResponse)
async def disable_http_source(
    sourceCode: str,
    operator: str | None = Depends(_get_operator),
    service: HttpSourceService = Depends(_get_service),
) -> DisableResponse:
    return await service.disable_http_source(sourceCode, operator=operator)


@router.post("/http-sources/{sourceCode}/delete", response_model=DisableResponse)
async def delete_http_source(
    sourceCode: str,
    operator: str | None = Depends(_get_operator),
    service: HttpSourceService = Depends(_get_service),
) -> DisableResponse:
    return await service.delete_http_source(sourceCode, operator=operator)
