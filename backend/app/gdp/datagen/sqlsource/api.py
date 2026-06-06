"""SQL 配置 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.gdp.datagen.sqlsource.models import (
    DisableResponse,
    SqlSourceConfig,
    SqlSourceParseRequest,
    SqlSourceParseResponse,
    SqlSourceResponse,
)
from app.gdp.datagen.sqlsource.parser import parse_sql_source
from app.gdp.datagen.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.sqlsource.service import SqlSourceService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-sqlsource"])


def _get_service() -> SqlSourceService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return SqlSourceService(SqlSourceRepository(sf))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user
    return await get_current_user(request)


@router.get("/sql-sources", response_model=list[SqlSourceResponse])
async def list_sql_sources(service: SqlSourceService = Depends(_get_service)) -> list[SqlSourceResponse]:
    return await service.list_sql_sources()


@router.post("/sql-sources/parse", response_model=SqlSourceParseResponse)
async def parse_sql_source_config(body: SqlSourceParseRequest) -> SqlSourceParseResponse:
    return parse_sql_source(body.sqlText, body.parameters)


@router.post("/sql-sources", response_model=SqlSourceResponse)
async def create_sql_source(
    body: SqlSourceConfig,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> SqlSourceResponse:
    return await service.upsert_sql_source(body, operator=operator)


@router.get("/sql-sources/{sourceCode}", response_model=SqlSourceResponse)
async def get_sql_source(sourceCode: str, service: SqlSourceService = Depends(_get_service)) -> SqlSourceResponse:
    return await service.get_sql_source(sourceCode)


@router.put("/sql-sources/{sourceCode}", response_model=SqlSourceResponse)
async def update_sql_source(
    sourceCode: str,
    body: SqlSourceConfig,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> SqlSourceResponse:
    if sourceCode != body.sourceCode:
        raise HTTPException(status_code=409, detail="path sourceCode must match request sourceCode")
    return await service.upsert_sql_source(body, operator=operator)


@router.post("/sql-sources/{sourceCode}/disable", response_model=DisableResponse)
async def disable_sql_source(
    sourceCode: str,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> DisableResponse:
    return await service.disable_sql_source(sourceCode, operator=operator)
