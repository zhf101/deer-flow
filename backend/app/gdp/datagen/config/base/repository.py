"""Persistence repository for datagen base configuration."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    DatasourceResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
    SysConfig,
    SysConfigResponse,
)
from app.gdp.datagen.config.common.models import ConfigStatus
from deerflow.persistence.base import Base


class DataFactorySystemRow(Base):
    __tablename__ = "df_system"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sys_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    sys_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataFactoryEnvironmentRow(Base):
    __tablename__ = "df_environment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    env_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataFactoryServiceEndpointRow(Base):
    __tablename__ = "df_service_endpoint"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sys_code: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("env_code", "sys_code", name="uq_df_service_endpoint"),)


class DataFactoryDatasourceRow(Base):
    __tablename__ = "df_datasource"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    env_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sys_code: Mapped[str] = mapped_column(String(64), nullable=False)
    datasource_code: Mapped[str] = mapped_column(String(128), nullable=False)
    datasource_name: Mapped[str] = mapped_column(String(256), nullable=False)
    db_type: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(String(256), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(256), nullable=False)
    username: Mapped[str | None] = mapped_column(String(512))
    password: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("env_code", "sys_code", "datasource_code", name="uq_df_datasource"),)


class DataFactoryConfigAuditRow(Base):
    __tablename__ = "df_config_audit"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str | None] = mapped_column(String(128))
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BaseConfigNotFoundError(LookupError):
    """Requested base configuration entity does not exist."""


class BaseConfigConflictError(RuntimeError):
    """Base configuration entity violates a uniqueness constraint."""


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class BaseConfigRepository:
    """Repository for systems, environments, service endpoints, and datasources."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_systems(self) -> list[SysConfigResponse]:
        stmt = select(DataFactorySystemRow).order_by(DataFactorySystemRow.sys_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._system_response(row) for row in rows]

    async def get_system(self, sys_code: str) -> SysConfigResponse:
        async with self._sf() as session:
            row = await self._require_system_row(session, sys_code)
            return self._system_response(row)

    async def upsert_system(self, config: SysConfig, *, operator: str | None = None) -> SysConfigResponse:
        async with self._sf() as session:
            row = await self._get_system_row(session, config.sysCode)
            now = _now()
            if row is None:
                row = DataFactorySystemRow(
                    id=_new_id(),
                    sys_code=config.sysCode,
                    sys_name=config.sysName,
                    status=config.status.value,
                    remark=config.remark,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                action = "CREATE_SYSTEM"
            else:
                row.sys_name = config.sysName
                row.status = config.status.value
                row.remark = config.remark
                row.updated_at = now
                action = "UPDATE_SYSTEM"
            self._add_audit(session, "SYSTEM", row.id, action, operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._system_response(row)

    async def delete_system(self, sys_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_system_row(session, sys_code)
            endpoint_ref = await self._has_row(session, select(DataFactoryServiceEndpointRow.id).where(DataFactoryServiceEndpointRow.sys_code == sys_code))
            datasource_ref = await self._has_row(session, select(DataFactoryDatasourceRow.id).where(DataFactoryDatasourceRow.sys_code == sys_code))
            if endpoint_ref or datasource_ref:
                raise BaseConfigConflictError(f"system is still referenced: {sys_code}")
            self._add_audit(session, "SYSTEM", row.id, "DELETE_SYSTEM", operator, {"sysCode": sys_code})
            await session.delete(row)
            await self._commit(session)
            return True

    async def list_environments(self) -> list[EnvironmentResponse]:
        stmt = select(DataFactoryEnvironmentRow).order_by(DataFactoryEnvironmentRow.env_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._env_response(row) for row in rows]

    async def get_environment(self, env_code: str) -> EnvironmentResponse:
        async with self._sf() as session:
            row = await self._require_environment_row(session, env_code)
            return self._env_response(row)

    async def upsert_environment(self, config: EnvironmentConfig, *, operator: str | None = None) -> EnvironmentResponse:
        async with self._sf() as session:
            row = await self._get_environment_row(session, config.envCode)
            now = _now()
            if row is None:
                row = DataFactoryEnvironmentRow(
                    id=_new_id(),
                    env_code=config.envCode,
                    env_name=config.envName,
                    status=config.status.value,
                    remark=config.remark,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                action = "CREATE_ENVIRONMENT"
            else:
                row.env_name = config.envName
                row.status = config.status.value
                row.remark = config.remark
                row.updated_at = now
                action = "UPDATE_ENVIRONMENT"
            self._add_audit(session, "ENVIRONMENT", row.id, action, operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._env_response(row)

    async def delete_environment(self, env_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_environment_row(session, env_code)
            endpoint_ref = await self._has_row(session, select(DataFactoryServiceEndpointRow.id).where(DataFactoryServiceEndpointRow.env_code == env_code))
            datasource_ref = await self._has_row(session, select(DataFactoryDatasourceRow.id).where(DataFactoryDatasourceRow.env_code == env_code))
            if endpoint_ref or datasource_ref:
                raise BaseConfigConflictError(f"environment is still referenced: {env_code}")
            self._add_audit(session, "ENVIRONMENT", row.id, "DELETE_ENVIRONMENT", operator, {"envCode": env_code})
            await session.delete(row)
            await self._commit(session)
            return True

    async def list_service_endpoints(
        self,
        *,
        env_code: str | None = None,
        sys_code: str | None = None,
    ) -> list[ServiceEndpointResponse]:
        stmt = select(DataFactoryServiceEndpointRow)
        if env_code:
            stmt = stmt.where(DataFactoryServiceEndpointRow.env_code == env_code)
        if sys_code:
            stmt = stmt.where(DataFactoryServiceEndpointRow.sys_code == sys_code)
        stmt = stmt.order_by(DataFactoryServiceEndpointRow.env_code.asc(), DataFactoryServiceEndpointRow.sys_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._endpoint_response(row) for row in rows]

    async def create_service_endpoint(self, config: ServiceEndpointConfig, *, operator: str | None = None) -> ServiceEndpointResponse:
        async with self._sf() as session:
            await self._require_environment_row(session, config.envCode)
            await self._require_system_row(session, config.sysCode)
            now = _now()
            row = DataFactoryServiceEndpointRow(
                id=_new_id(),
                env_code=config.envCode,
                sys_code=config.sysCode,
                base_url=config.baseUrl,
                status=config.status.value,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            self._add_audit(session, "SERVICE_ENDPOINT", row.id, "CREATE_SERVICE_ENDPOINT", operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._endpoint_response(row)

    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig, *, operator: str | None = None) -> ServiceEndpointResponse:
        async with self._sf() as session:
            await self._require_environment_row(session, config.envCode)
            await self._require_system_row(session, config.sysCode)
            row = await self._require_endpoint_by_id(session, endpoint_id)
            row.env_code = config.envCode
            row.sys_code = config.sysCode
            row.base_url = config.baseUrl
            row.status = config.status.value
            row.updated_at = _now()
            self._add_audit(session, "SERVICE_ENDPOINT", row.id, "UPDATE_SERVICE_ENDPOINT", operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._endpoint_response(row)

    async def delete_service_endpoint(self, endpoint_id: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_endpoint_by_id(session, endpoint_id)
            self._add_audit(session, "SERVICE_ENDPOINT", row.id, "DELETE_SERVICE_ENDPOINT", operator, {"id": endpoint_id})
            await session.delete(row)
            await self._commit(session)
            return True

    async def get_enabled_service_endpoint(
        self,
        *,
        env_code: str | None = None,
        sys_code: str,
    ) -> ServiceEndpointResponse:
        stmt = select(DataFactoryServiceEndpointRow).where(
            DataFactoryServiceEndpointRow.sys_code == sys_code,
            DataFactoryServiceEndpointRow.status == ConfigStatus.ENABLED.value,
        )
        if env_code:
            stmt = stmt.where(DataFactoryServiceEndpointRow.env_code == env_code)
        async with self._sf() as session:
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                label = f"{env_code}/{sys_code}" if env_code else sys_code
                raise BaseConfigNotFoundError(f"enabled service endpoint not found: {label}")
            return self._endpoint_response(row)

    async def list_datasources(
        self,
        *,
        env_code: str | None = None,
        sys_code: str | None = None,
    ) -> list[DatasourceResponse]:
        stmt = select(DataFactoryDatasourceRow)
        if env_code:
            stmt = stmt.where(DataFactoryDatasourceRow.env_code == env_code)
        if sys_code:
            stmt = stmt.where(DataFactoryDatasourceRow.sys_code == sys_code)
        stmt = stmt.order_by(
            DataFactoryDatasourceRow.env_code.asc(),
            DataFactoryDatasourceRow.sys_code.asc(),
            DataFactoryDatasourceRow.datasource_code.asc(),
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._datasource_response(row) for row in rows]

    async def create_datasource(self, config: DatasourceConfig, *, operator: str | None = None) -> DatasourceResponse:
        async with self._sf() as session:
            await self._require_environment_row(session, config.envCode)
            await self._require_system_row(session, config.sysCode)
            now = _now()
            row = DataFactoryDatasourceRow(
                id=_new_id(),
                env_code=config.envCode,
                sys_code=config.sysCode,
                datasource_code=config.datasourceCode,
                datasource_name=config.datasourceName,
                db_type=config.dbType,
                host=config.host,
                port=config.port,
                database_name=config.databaseName,
                username=config.username,
                password=config.password,
                status=config.status.value,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            self._add_audit(session, "DATASOURCE", row.id, "CREATE_DATASOURCE", operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._datasource_response(row)

    async def update_datasource(self, datasource_id: str, config: DatasourceConfig, *, operator: str | None = None) -> DatasourceResponse:
        async with self._sf() as session:
            await self._require_environment_row(session, config.envCode)
            await self._require_system_row(session, config.sysCode)
            row = await self._require_datasource_by_id(session, datasource_id)
            row.env_code = config.envCode
            row.sys_code = config.sysCode
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
            self._add_audit(session, "DATASOURCE", row.id, "UPDATE_DATASOURCE", operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._datasource_response(row)

    async def delete_datasource(self, datasource_id: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_datasource_by_id(session, datasource_id)
            self._add_audit(session, "DATASOURCE", row.id, "DELETE_DATASOURCE", operator, {"id": datasource_id})
            await session.delete(row)
            await self._commit(session)
            return True

    async def get_enabled_datasource(
        self,
        *,
        env_code: str | None = None,
        sys_code: str,
        datasource_code: str,
    ) -> DatasourceResponse:
        stmt = select(DataFactoryDatasourceRow).where(
            DataFactoryDatasourceRow.sys_code == sys_code,
            DataFactoryDatasourceRow.datasource_code == datasource_code,
            DataFactoryDatasourceRow.status == ConfigStatus.ENABLED.value,
        )
        if env_code:
            stmt = stmt.where(DataFactoryDatasourceRow.env_code == env_code)
        async with self._sf() as session:
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                label = f"{env_code}/{sys_code}/{datasource_code}" if env_code else f"{sys_code}/{datasource_code}"
                raise BaseConfigNotFoundError(f"enabled datasource not found: {label}")
            return self._datasource_response(row)

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise BaseConfigConflictError("unique constraint violation") from exc

    @staticmethod
    async def _has_row(session: AsyncSession, stmt: Any) -> bool:
        return (await session.execute(stmt.limit(1))).first() is not None

    @staticmethod
    async def _get_system_row(session: AsyncSession, sys_code: str) -> DataFactorySystemRow | None:
        stmt = select(DataFactorySystemRow).where(DataFactorySystemRow.sys_code == sys_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_system_row(self, session: AsyncSession, sys_code: str) -> DataFactorySystemRow:
        row = await self._get_system_row(session, sys_code)
        if row is None:
            raise BaseConfigNotFoundError(f"system not found: {sys_code}")
        return row

    @staticmethod
    async def _get_environment_row(session: AsyncSession, env_code: str) -> DataFactoryEnvironmentRow | None:
        stmt = select(DataFactoryEnvironmentRow).where(DataFactoryEnvironmentRow.env_code == env_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_environment_row(self, session: AsyncSession, env_code: str) -> DataFactoryEnvironmentRow:
        row = await self._get_environment_row(session, env_code)
        if row is None:
            raise BaseConfigNotFoundError(f"environment not found: {env_code}")
        return row

    @staticmethod
    async def _require_endpoint_by_id(session: AsyncSession, endpoint_id: str) -> DataFactoryServiceEndpointRow:
        row = await session.get(DataFactoryServiceEndpointRow, endpoint_id)
        if row is None:
            raise BaseConfigNotFoundError(f"service endpoint not found: {endpoint_id}")
        return row

    @staticmethod
    async def _require_datasource_by_id(session: AsyncSession, datasource_id: str) -> DataFactoryDatasourceRow:
        row = await session.get(DataFactoryDatasourceRow, datasource_id)
        if row is None:
            raise BaseConfigNotFoundError(f"datasource not found: {datasource_id}")
        return row

    @staticmethod
    def _add_audit(session: AsyncSession, target_type: str, target_id: str, action: str, operator: str | None, after: Any) -> None:
        session.add(
            DataFactoryConfigAuditRow(
                id=_new_id(),
                target_type=target_type,
                target_id=target_id,
                action=action,
                operator=operator,
                before_json=None,
                after_json=_dumps(after),
                created_at=_now(),
            )
        )

    @staticmethod
    def _system_response(row: DataFactorySystemRow) -> SysConfigResponse:
        return SysConfigResponse(
            id=row.id,
            sysCode=row.sys_code,
            sysName=row.sys_name,
            status=row.status,
            remark=row.remark,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    @staticmethod
    def _env_response(row: DataFactoryEnvironmentRow) -> EnvironmentResponse:
        return EnvironmentResponse(
            id=row.id,
            envCode=row.env_code,
            envName=row.env_name,
            status=row.status,
            remark=row.remark,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    @staticmethod
    def _endpoint_response(row: DataFactoryServiceEndpointRow) -> ServiceEndpointResponse:
        return ServiceEndpointResponse(
            id=row.id,
            envCode=row.env_code,
            sysCode=row.sys_code,
            baseUrl=row.base_url,
            status=row.status,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    @staticmethod
    def _datasource_response(row: DataFactoryDatasourceRow) -> DatasourceResponse:
        return DatasourceResponse(
            id=row.id,
            envCode=row.env_code,
            sysCode=row.sys_code,
            datasourceCode=row.datasource_code,
            datasourceName=row.datasource_name,
            dbType=row.db_type,
            host=row.host,
            port=row.port,
            databaseName=row.database_name,
            username=row.username,
            password=row.password,
            status=row.status,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
