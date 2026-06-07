"""造数基础配置业务服务层。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    DatasourceResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    OperationResponse,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
    SysConfig,
    SysConfigResponse,
)
from app.gdp.datagen.config.base.repository import (
    BaseConfigConflictError,
    BaseConfigNotFoundError,
    BaseConfigRepository,
)

T = TypeVar("T")


class BaseConfigService:
    def __init__(self, repository: BaseConfigRepository) -> None:
        self._repo = repository

    async def list_systems(self) -> list[SysConfigResponse]:
        return await self._repo.list_systems()

    async def get_system(self, sys_code: str) -> SysConfigResponse:
        return await self._guard(lambda: self._repo.get_system(sys_code))

    async def upsert_system(self, config: SysConfig, *, operator: str | None = None) -> SysConfigResponse:
        return await self._guard(lambda: self._repo.upsert_system(config, operator=operator))

    async def delete_system(self, sys_code: str, *, operator: str | None = None) -> OperationResponse:
        await self._guard(lambda: self._repo.delete_system(sys_code, operator=operator))
        return OperationResponse(success=True)

    async def list_environments(self) -> list[EnvironmentResponse]:
        return await self._repo.list_environments()

    async def get_environment(self, env_code: str) -> EnvironmentResponse:
        return await self._guard(lambda: self._repo.get_environment(env_code))

    async def upsert_environment(self, config: EnvironmentConfig, *, operator: str | None = None) -> EnvironmentResponse:
        return await self._guard(lambda: self._repo.upsert_environment(config, operator=operator))

    async def delete_environment(self, env_code: str, *, operator: str | None = None) -> OperationResponse:
        await self._guard(lambda: self._repo.delete_environment(env_code, operator=operator))
        return OperationResponse(success=True)

    async def list_service_endpoints(
        self,
        *,
        env_code: str | None = None,
        sys_code: str | None = None,
    ) -> list[ServiceEndpointResponse]:
        return await self._repo.list_service_endpoints(env_code=env_code, sys_code=sys_code)

    async def create_service_endpoint(self, config: ServiceEndpointConfig, *, operator: str | None = None) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.create_service_endpoint(config, operator=operator))

    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig, *, operator: str | None = None) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.update_service_endpoint(endpoint_id, config, operator=operator))

    async def delete_service_endpoint(self, endpoint_id: str, *, operator: str | None = None) -> OperationResponse:
        await self._guard(lambda: self._repo.delete_service_endpoint(endpoint_id, operator=operator))
        return OperationResponse(success=True)

    async def list_datasources(
        self,
        *,
        env_code: str | None = None,
        sys_code: str | None = None,
    ) -> list[DatasourceResponse]:
        return await self._repo.list_datasources(env_code=env_code, sys_code=sys_code)

    async def create_datasource(self, config: DatasourceConfig, *, operator: str | None = None) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.create_datasource(config, operator=operator))

    async def update_datasource(self, datasource_id: str, config: DatasourceConfig, *, operator: str | None = None) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.update_datasource(datasource_id, config, operator=operator))

    async def delete_datasource(self, datasource_id: str, *, operator: str | None = None) -> OperationResponse:
        await self._guard(lambda: self._repo.delete_datasource(datasource_id, operator=operator))
        return OperationResponse(success=True)

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except BaseConfigNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BaseConfigConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
