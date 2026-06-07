"""SQL 源业务服务层。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.sqlsource.models import DisableResponse, SqlSourceConfig, SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import (
    SqlSourceConflictError,
    SqlSourceNotFoundError,
    SqlSourceRepository,
)

T = TypeVar("T")


class SqlSourceService:
    def __init__(self, repository: SqlSourceRepository, base_repository: BaseConfigRepository) -> None:
        self._repo = repository
        self._base_repo = base_repository

    async def list_sql_sources(
        self,
        *,
        sys_code: str | None = None,
        status: ConfigStatus | None = None,
    ) -> list[SqlSourceResponse]:
        return await self._repo.list_sql_sources(sys_code=sys_code, status=status)

    async def get_sql_source(self, source_code: str) -> SqlSourceResponse:
        return await self._guard(lambda: self._repo.get_sql_source(source_code))

    async def upsert_sql_source(self, config: SqlSourceConfig, *, operator: str | None = None) -> SqlSourceResponse:
        await self._validate_enabled_system(config.sysCode)
        await self._validate_enabled_datasource(config.sysCode, config.datasourceCode)
        return await self._guard(lambda: self._repo.upsert_sql_source(config, operator=operator))

    async def disable_sql_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_sql_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def delete_sql_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_sql_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def _validate_enabled_system(self, sys_code: str) -> None:
        try:
            system = await self._base_repo.get_system(sys_code)
        except BaseConfigNotFoundError as exc:
            raise HTTPException(status_code=422, detail=f"enabled system not found: {sys_code}") from exc
        if system.status != ConfigStatus.ENABLED:
            raise HTTPException(status_code=422, detail=f"enabled system not found: {sys_code}")

    async def _validate_enabled_datasource(self, sys_code: str, datasource_code: str) -> None:
        try:
            await self._base_repo.get_enabled_datasource(sys_code=sys_code, datasource_code=datasource_code)
        except BaseConfigNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"enabled datasource not found: {sys_code}/{datasource_code}",
            ) from exc

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except SqlSourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SqlSourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
