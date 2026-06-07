"""SQL 配置持久化仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.base.repository import DataFactoryConfigAuditRow
from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig, SqlSourceResponse
from deerflow.persistence.base import Base


class DataFactorySqlSourceRow(Base):
    """SQL 配置持久化表。

    该表保存可复用 SQL 定义、参数定义和安全策略。数据源本身不在这里保存连接
    信息，而是通过 ``sys_code + datasource_code`` 关联基础配置里的数据源。
    """

    __tablename__ = "df_sql_source"

    # 主键与业务编码
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    source_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="SQL 配置唯一编码。")
    source_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="SQL 配置名称。")

    # 所属系统与数据源引用
    sys_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属系统编码，关联 df_system.sys_code。")
    datasource_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="数据源编码，关联 df_datasource.datasource_code。")

    # SQL 执行定义
    operation: Mapped[str] = mapped_column(String(32), nullable=False, comment="SQL 操作类型。")
    sql_text: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 文本。")
    normalized_sql: Mapped[str] = mapped_column(Text, nullable=False, comment="解析后的规范 SQL，保留命名参数占位符。")
    tables_json: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 操作表元数据 JSON。")
    result_fields_json: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 查询结果字段元数据 JSON。")
    condition_fields_json: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 条件字段元数据 JSON。")
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 参数定义 JSON。")
    safety_json: Mapped[str] = mapped_column(Text, nullable=False, comment="SQL 执行安全策略 JSON。")

    # 状态与审计字段
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="配置状态。")
    created_by: Mapped[str | None] = mapped_column(String(128), comment="创建人标识。")
    updated_by: Mapped[str | None] = mapped_column(String(128), comment="最近更新人标识。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近更新时间。")


class SqlSourceNotFoundError(LookupError):
    """请求的 SQL 配置不存在。"""


class SqlSourceConflictError(RuntimeError):
    """SQL 配置违反唯一性约束。"""


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


class SqlSourceRepository:
    """可复用 SQL 配置持久化仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_sql_sources(
        self,
        *,
        sys_code: str | None = None,
        status: ConfigStatus | None = None,
    ) -> list[SqlSourceResponse]:
        stmt = select(DataFactorySqlSourceRow)
        if sys_code:
            stmt = stmt.where(DataFactorySqlSourceRow.sys_code == sys_code)
        if status:
            stmt = stmt.where(DataFactorySqlSourceRow.status == status.value)
        stmt = stmt.order_by(DataFactorySqlSourceRow.updated_at.desc(), DataFactorySqlSourceRow.source_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_response(row) for row in rows]

    async def get_sql_source(self, source_code: str) -> SqlSourceResponse:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            return self._to_response(row)

    async def upsert_sql_source(self, config: SqlSourceConfig, *, operator: str | None = None) -> SqlSourceResponse:
        async with self._sf() as session:
            row = await self._get_row(session, config.sourceCode)
            now = _now()
            if row is None:
                row = DataFactorySqlSourceRow(
                    id=_new_id(),
                    source_code=config.sourceCode,
                    source_name=config.sourceName,
                    sys_code=config.sysCode,
                    datasource_code=config.datasourceCode,
                    operation=config.operation.value,
                    sql_text=config.sqlText,
                    normalized_sql=config.normalizedSql,
                    tables_json=_dumps([item.model_dump(mode="json") for item in config.tables]),
                    result_fields_json=_dumps([item.model_dump(mode="json") for item in config.resultFields]),
                    condition_fields_json=_dumps([item.model_dump(mode="json") for item in config.conditionFields]),
                    parameters_json=_dumps([p.model_dump(mode="json") for p in config.parameters]),
                    safety_json=_dumps(config.safety.model_dump(mode="json")),
                    status=config.status.value,
                    created_by=operator,
                    updated_by=operator,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                action = "CREATE_SQL_SOURCE"
            else:
                row.source_name = config.sourceName
                row.sys_code = config.sysCode
                row.datasource_code = config.datasourceCode
                row.operation = config.operation.value
                row.sql_text = config.sqlText
                row.normalized_sql = config.normalizedSql
                row.tables_json = _dumps([item.model_dump(mode="json") for item in config.tables])
                row.result_fields_json = _dumps([item.model_dump(mode="json") for item in config.resultFields])
                row.condition_fields_json = _dumps([item.model_dump(mode="json") for item in config.conditionFields])
                row.parameters_json = _dumps([p.model_dump(mode="json") for p in config.parameters])
                row.safety_json = _dumps(config.safety.model_dump(mode="json"))
                row.status = config.status.value
                row.updated_by = operator
                row.updated_at = now
                action = "UPDATE_SQL_SOURCE"
            self._add_audit(session, "SQL_SOURCE", row.id, action, operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def disable_sql_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            row.status = ConfigStatus.DISABLED.value
            row.updated_by = operator
            row.updated_at = _now()
            self._add_audit(session, "SQL_SOURCE", row.id, "DISABLE_SQL_SOURCE", operator, {"sourceCode": source_code})
            await self._commit(session)
            return True

    async def delete_sql_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            self._add_audit(session, "SQL_SOURCE", row.id, "DELETE_SQL_SOURCE", operator, {"sourceCode": source_code})
            await session.delete(row)
            await self._commit(session)
            return True

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise SqlSourceConflictError("unique constraint violation") from exc

    async def _get_row(self, session: AsyncSession, source_code: str) -> DataFactorySqlSourceRow | None:
        stmt = select(DataFactorySqlSourceRow).where(DataFactorySqlSourceRow.source_code == source_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_row(self, session: AsyncSession, source_code: str) -> DataFactorySqlSourceRow:
        row = await self._get_row(session, source_code)
        if row is None:
            raise SqlSourceNotFoundError(f"SQL source not found: {source_code}")
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
    def _to_response(row: DataFactorySqlSourceRow) -> SqlSourceResponse:
        return SqlSourceResponse(
            id=row.id,
            sourceCode=row.source_code,
            sourceName=row.source_name,
            sysCode=row.sys_code,
            datasourceCode=row.datasource_code,
            operation=row.operation,
            sqlText=row.sql_text,
            normalizedSql=row.normalized_sql,
            tables=_loads(row.tables_json, []),
            resultFields=_loads(row.result_fields_json, []),
            conditionFields=_loads(row.condition_fields_json, []),
            parameters=_loads(row.parameters_json, []),
            safety=_loads(row.safety_json, {}),
            status=row.status,
            createdBy=row.created_by,
            updatedBy=row.updated_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
