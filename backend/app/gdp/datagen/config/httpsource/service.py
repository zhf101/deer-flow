"""HTTP source business service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.httpsource.models import DisableResponse, HttpSourceConfig, HttpSourceResponse
from app.gdp.datagen.config.httpsource.repository import (
    HttpSourceConflictError,
    HttpSourceNotFoundError,
    HttpSourceRepository,
)

T = TypeVar("T")


class HttpSourceService:
    def __init__(self, repository: HttpSourceRepository, base_repository: BaseConfigRepository) -> None:
        self._repo = repository
        self._base_repo = base_repository

    async def list_http_sources(
        self,
        *,
        sys_code: str | None = None,
        status: ConfigStatus | None = None,
    ) -> list[HttpSourceResponse]:
        return await self._repo.list_http_sources(sys_code=sys_code, status=status)

    async def get_http_source(self, source_code: str) -> HttpSourceResponse:
        return await self._guard(lambda: self._repo.get_http_source(source_code))

    async def upsert_http_source(self, config: HttpSourceConfig, *, operator: str | None = None) -> HttpSourceResponse:
        await self._validate_enabled_system(config.sysCode)
        return await self._guard(lambda: self._repo.upsert_http_source(config, operator=operator))

    async def disable_http_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_http_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def delete_http_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_http_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def _validate_enabled_system(self, sys_code: str) -> None:
        try:
            system = await self._base_repo.get_system(sys_code)
        except BaseConfigNotFoundError as exc:
            raise HTTPException(status_code=422, detail=f"enabled system not found: {sys_code}") from exc
        if system.status != ConfigStatus.ENABLED:
            raise HTTPException(status_code=422, detail=f"enabled system not found: {sys_code}")

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except HttpSourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except HttpSourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
