"""基础配置仓储——环境、服务端点、数据源的 CRUD 操作。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gdp.datagen.baseconfig.models import (
    DatasourceConfig,
    DatasourceResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
)
from app.gdp.persistence.model import (
    DataFactoryConfigAuditRow,
    DataFactoryDatasourceRow,
    DataFactoryEnvironmentRow,
    DataFactoryServiceEndpointRow,
)


class BaseConfigNotFoundError(LookupError):
    """请求的基础配置实体不存在。"""


class BaseConfigConflictError(RuntimeError):
    """基础配置实体违反唯一约束。"""


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class BaseConfigRepository:
    """基础配置仓储，封装环境、服务端点、数据源的数据库操作。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    # ========================= 环境 CRUD =========================

    async def list_environments(self) -> list[EnvironmentResponse]:
        async with self._sf() as session:
            rows = (await session.execute(
                select(DataFactoryEnvironmentRow).order_by(DataFactoryEnvironmentRow.env_code.asc())
            )).scalars().all()
            return [self._env_response(row) for row in rows]

    async def upsert_environment(self, config: EnvironmentConfig) -> EnvironmentResponse:
        async with self._sf() as session:
            stmt = select(DataFactoryEnvironmentRow).where(DataFactoryEnvironmentRow.env_code == config.envCode)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = _now()
            if row is None:
                row = DataFactoryEnvironmentRow(
                    id=_new_id(), env_code=config.envCode, env_name=config.envName,
                    status=config.status.value, remark=config.remark,
                    created_at=now, updated_at=now,
                )
                session.add(row)
            else:
                row.env_name = config.envName
                row.status = config.status.value
                row.remark = config.remark
                row.updated_at = now
            await self._commit(session)
            await session.refresh(row)
            return self._env_response(row)

    async def delete_environment(self, env_code: str) -> bool:
        async with self._sf() as session:
            stmt = select(DataFactoryEnvironmentRow).where(DataFactoryEnvironmentRow.env_code == env_code)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise BaseConfigNotFoundError(f"environment not found: {env_code}")
            await session.delete(row)
            await self._commit(session)
            return True

    # ========================= 服务端点 CRUD =========================

    async def list_service_endpoints(self, *, env_code: str | None = None) -> list[ServiceEndpointResponse]:
        stmt = select(DataFactoryServiceEndpointRow)
        if env_code:
            stmt = stmt.where(DataFactoryServiceEndpointRow.env_code == env_code)
        stmt = stmt.order_by(
            DataFactoryServiceEndpointRow.env_code.asc(),
            DataFactoryServiceEndpointRow.service_code.asc(),
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._endpoint_response(row) for row in rows]

    async def create_service_endpoint(self, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        row = DataFactoryServiceEndpointRow(
            id=_new_id(), env_code=config.envCode, service_code=config.serviceCode,
            service_name=config.serviceName, base_url=config.baseUrl,
            status=config.status.value, created_at=_now(), updated_at=_now(),
        )
        async with self._sf() as session:
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._endpoint_response(row)

    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryServiceEndpointRow, endpoint_id, "service endpoint")
            row.env_code = config.envCode
            row.service_code = config.serviceCode
            row.service_name = config.serviceName
            row.base_url = config.baseUrl
            row.status = config.status.value
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._endpoint_response(row)

    async def delete_service_endpoint(self, endpoint_id: str) -> bool:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryServiceEndpointRow, endpoint_id, "service endpoint")
            await session.delete(row)
            await self._commit(session)
            return True

    # ========================= 数据源 CRUD =========================

    async def list_datasources(self, *, env_code: str | None = None) -> list[DatasourceResponse]:
        stmt = select(DataFactoryDatasourceRow)
        if env_code:
            stmt = stmt.where(DataFactoryDatasourceRow.env_code == env_code)
        stmt = stmt.order_by(
            DataFactoryDatasourceRow.env_code.asc(),
            DataFactoryDatasourceRow.datasource_code.asc(),
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._ds_response(row) for row in rows]

    async def create_datasource(self, config: DatasourceConfig) -> DatasourceResponse:
        row = DataFactoryDatasourceRow(
            id=_new_id(), env_code=config.envCode, datasource_code=config.datasourceCode,
            datasource_name=config.datasourceName, db_type=config.dbType,
            host=config.host, port=config.port, database_name=config.databaseName,
            username=config.username, password=config.password,
            status=config.status.value, created_at=_now(), updated_at=_now(),
        )
        async with self._sf() as session:
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._ds_response(row)

    async def update_datasource(self, datasource_id: str, config: DatasourceConfig) -> DatasourceResponse:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryDatasourceRow, datasource_id, "datasource")
            row.env_code = config.envCode
            row.datasource_code = config.datasourceCode
            row.datasource_name = config.datasourceName
            row.db_type = config.dbType
            row.host = config.host
            row.port = config.port
            row.database_name = config.databaseName
            row.username = config.username
            row.password = config.password
            row.status = config.status.value
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._ds_response(row)

    async def delete_datasource(self, datasource_id: str) -> bool:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryDatasourceRow, datasource_id, "datasource")
            await session.delete(row)
            await self._commit(session)
            return True

    # ========================= 内部辅助 =========================

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise BaseConfigConflictError("unique constraint violation") from exc

    async def _require_by_id(self, session: AsyncSession, row_type: type, row_id: str, label: str):
        row = await session.get(row_type, row_id)
        if row is None:
            raise BaseConfigNotFoundError(f"{label} not found: {row_id}")
        return row

    @staticmethod
    def _env_response(row: DataFactoryEnvironmentRow) -> EnvironmentResponse:
        return EnvironmentResponse(
            id=row.id, envCode=row.env_code, envName=row.env_name,
            status=row.status, remark=row.remark,
            createdAt=row.created_at, updatedAt=row.updated_at,
        )

    @staticmethod
    def _endpoint_response(row: DataFactoryServiceEndpointRow) -> ServiceEndpointResponse:
        return ServiceEndpointResponse(
            id=row.id, envCode=row.env_code, serviceCode=row.service_code,
            serviceName=row.service_name, baseUrl=row.base_url,
            status=row.status, createdAt=row.created_at, updatedAt=row.updated_at,
        )

    @staticmethod
    def _ds_response(row: DataFactoryDatasourceRow) -> DatasourceResponse:
        return DatasourceResponse(
            id=row.id, envCode=row.env_code, datasourceCode=row.datasource_code,
            datasourceName=row.datasource_name, dbType=row.db_type,
            host=row.host, port=row.port, databaseName=row.database_name,
            username=row.username, password=row.password,
            status=row.status, createdAt=row.created_at, updatedAt=row.updated_at,
        )
