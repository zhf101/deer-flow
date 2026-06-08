"""HTTP 源业务服务层：CRUD + 测试委托。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.httpsource.executor import execute_http_test
from app.gdp.datagen.config.httpsource.models import (
    DisableResponse,
    HttpSourceConfig,
    HttpSourceResponse,
    HttpSourceTestRequest,
    HttpSourceTestResponse,
)
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

    async def test_http_source(self, request: HttpSourceTestRequest) -> HttpSourceTestResponse:
        """真实执行一次 HTTP 接口配置测试请求，委托给 executor 模块。"""
        config = request.config

        # 解析 Base URL
        try:
            endpoint = await self._base_repo.get_enabled_service_endpoint(
                env_code=request.envCode, sys_code=config.sysCode
            )
        except BaseConfigNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"当前选择的环境「{request.envCode}」还没有为系统「{config.sysCode}」"
                    "配置启用的服务端点。请先到「基础配置 > 服务端点」新增或启用对应配置后再测试接口。"
                ),
            ) from exc

        return await execute_http_test(config, endpoint.baseUrl, config.timeoutConfig)

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
