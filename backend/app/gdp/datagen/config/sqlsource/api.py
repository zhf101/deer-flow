"""SQL 源接口路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.sqlsource.models import (
    DisableResponse,
    SqlSourceConfig,
    SqlSourceParseRequest,
    SqlSourceParseResponse,
    SqlSourceResponse,
)
from app.gdp.datagen.config.sqlsource.parser import parse_sql_source
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.runtime.sql.models import (
    SqlExecutionRequest,
    SqlExecutionResult,
    SqlSourceTestRequest,
)
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService, status_code_for_error
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-sqlsource"])


def _get_service() -> SqlSourceService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return SqlSourceService(SqlSourceRepository(sf), BaseConfigRepository(sf))


def _get_execution_service() -> SqlExecutionService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return SqlExecutionService(
        base_repository=BaseConfigRepository(sf),
        sql_source_repository=SqlSourceRepository(sf),
        registry=SqlExecutorRegistry(),
    )


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/sql-sources", response_model=list[SqlSourceResponse])
async def list_sql_sources(
    sys_code: str | None = Query(default=None, alias="sysCode"),
    service: SqlSourceService = Depends(_get_service),
) -> list[SqlSourceResponse]:
    return await service.list_sql_sources(sys_code=sys_code)


@router.post("/sql-sources/parse", response_model=SqlSourceParseResponse)
async def parse_sql_source_config(body: SqlSourceParseRequest) -> SqlSourceParseResponse:
    return parse_sql_source(body.sqlText, body.parameters)


@router.post("/sql-sources/test", response_model=SqlExecutionResult)
async def test_sql_source(
    body: SqlSourceTestRequest,
    service: SqlExecutionService = Depends(_get_execution_service),
) -> SqlExecutionResult:
    try:
        return await service.execute_source(body)
    except Exception as exc:
        raise HTTPException(status_code=status_code_for_error(exc), detail=str(exc)) from exc


@router.post("/sql/execute", response_model=SqlExecutionResult)
async def execute_sql(
    body: SqlExecutionRequest,
    service: SqlExecutionService = Depends(_get_execution_service),
) -> SqlExecutionResult:
    try:
        return await service.execute(body)
    except Exception as exc:
        raise HTTPException(status_code=status_code_for_error(exc), detail=str(exc)) from exc


@router.post("/sql-sources", response_model=SqlSourceResponse)
async def create_sql_source(
    body: SqlSourceConfig,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> SqlSourceResponse:
    return await service.upsert_sql_source(body, operator=operator)


@router.get("/sql-sources/{sourceCode}", response_model=SqlSourceResponse)
async def get_sql_source(
    sourceCode: str,
    service: SqlSourceService = Depends(_get_service),
) -> SqlSourceResponse:
    return await service.get_sql_source(sourceCode)


@router.post("/sql-sources/update", response_model=SqlSourceResponse)
async def update_sql_source(
    body: SqlSourceConfig,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> SqlSourceResponse:
    return await service.upsert_sql_source(body, operator=operator)


@router.post("/sql-sources/{sourceCode}/disable", response_model=DisableResponse)
async def disable_sql_source(
    sourceCode: str,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> DisableResponse:
    return await service.disable_sql_source(sourceCode, operator=operator)


@router.post("/sql-sources/{sourceCode}/delete", response_model=DisableResponse)
async def delete_sql_source(
    sourceCode: str,
    operator: str | None = Depends(_get_operator),
    service: SqlSourceService = Depends(_get_service),
) -> DisableResponse:
    return await service.delete_sql_source(sourceCode, operator=operator)
