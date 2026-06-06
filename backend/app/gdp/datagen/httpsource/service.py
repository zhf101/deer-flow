"""HTTP 接口配置业务逻辑层。"""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.datagen.httpsource.models import DisableResponse, HttpSourceConfig, HttpSourceResponse
from app.gdp.datagen.httpsource.repository import (
    HttpSourceConflictError,
    HttpSourceNotFoundError,
    HttpSourceRepository,
)
from app.gdp.models import ConfigStatus


class HttpSourceService:
    def __init__(self, repository: HttpSourceRepository) -> None:
        self._repo = repository

    async def list_http_sources(self, *, status: ConfigStatus | None = None) -> list[HttpSourceResponse]:
        return await self._repo.list_http_sources(status=status)

    async def get_http_source(self, source_code: str) -> HttpSourceResponse:
        return await self._guard(lambda: self._repo.get_http_source(source_code))

    async def upsert_http_source(self, config: HttpSourceConfig, *, operator: str | None = None) -> HttpSourceResponse:
        return await self._guard(lambda: self._repo.upsert_http_source(config, operator=operator))

    async def disable_http_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_http_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def delete_http_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_http_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def _guard(self, call):
        try:
            return await call()
        except HttpSourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except HttpSourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
