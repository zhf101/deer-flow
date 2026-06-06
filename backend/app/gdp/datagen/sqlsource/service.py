"""SQL 配置业务逻辑层。"""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.datagen.sqlsource.models import DisableResponse, SqlSourceConfig, SqlSourceResponse
from app.gdp.datagen.sqlsource.repository import (
    SqlSourceConflictError,
    SqlSourceNotFoundError,
    SqlSourceRepository,
)
from app.gdp.models import ConfigStatus


class SqlSourceService:
    def __init__(self, repository: SqlSourceRepository) -> None:
        self._repo = repository

    async def list_sql_sources(self, *, status: ConfigStatus | None = None) -> list[SqlSourceResponse]:
        return await self._repo.list_sql_sources(status=status)

    async def get_sql_source(self, source_code: str) -> SqlSourceResponse:
        return await self._guard(lambda: self._repo.get_sql_source(source_code))

    async def upsert_sql_source(self, config: SqlSourceConfig, *, operator: str | None = None) -> SqlSourceResponse:
        return await self._guard(lambda: self._repo.upsert_sql_source(config, operator=operator))

    async def disable_sql_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_sql_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def _guard(self, call):
        try:
            return await call()
        except SqlSourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SqlSourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
