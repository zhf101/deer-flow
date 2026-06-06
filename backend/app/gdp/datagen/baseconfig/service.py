"""基础配置业务逻辑层。"""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.datagen.baseconfig.models import (
    DatasourceConfig,
    DatasourceResponse,
    DisableResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
)
from app.gdp.datagen.baseconfig.repository import (
    BaseConfigConflictError,
    BaseConfigNotFoundError,
    BaseConfigRepository,
)


class BaseConfigService:
    def __init__(self, repository: BaseConfigRepository) -> None:
        self._repo = repository

    # ---------- 环境 ----------

    async def list_environments(self) -> list[EnvironmentResponse]:
        return await self._repo.list_environments()

    async def upsert_environment(self, config: EnvironmentConfig) -> EnvironmentResponse:
        return await self._guard(lambda: self._repo.upsert_environment(config))

    async def delete_environment(self, env_code: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_environment(env_code))
        return DisableResponse(success=True)

    # ---------- 服务端点 ----------

    async def list_service_endpoints(self, *, env_code: str | None = None) -> list[ServiceEndpointResponse]:
        return await self._repo.list_service_endpoints(env_code=env_code)

    async def create_service_endpoint(self, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.create_service_endpoint(config))

    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.update_service_endpoint(endpoint_id, config))

    async def delete_service_endpoint(self, endpoint_id: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_service_endpoint(endpoint_id))
        return DisableResponse(success=True)

    # ---------- 数据源 ----------

    async def list_datasources(self, *, env_code: str | None = None) -> list[DatasourceResponse]:
        return await self._repo.list_datasources(env_code=env_code)

    async def create_datasource(self, config: DatasourceConfig) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.create_datasource(config))

    async def update_datasource(self, datasource_id: str, config: DatasourceConfig) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.update_datasource(datasource_id, config))

    async def delete_datasource(self, datasource_id: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_datasource(datasource_id))
        return DisableResponse(success=True)

    # ---------- 异常守卫 ----------

    async def _guard(self, call):
        try:
            return await call()
        except BaseConfigNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BaseConfigConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
