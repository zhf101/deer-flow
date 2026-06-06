"""SQL 配置仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gdp.datagen.sqlsource.models import SqlSourceConfig, SqlSourceResponse
from app.gdp.models import ConfigStatus
from app.gdp.persistence.model import DataFactoryConfigAuditRow, DataFactorySqlTemplateRow


class SqlSourceNotFoundError(LookupError):
    """请求的 SQL 配置不存在。"""


class SqlSourceConflictError(RuntimeError):
    """SQL 配置违反唯一约束。"""


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
    """SQL 配置仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_sql_sources(self, *, status: ConfigStatus | None = None) -> list[SqlSourceResponse]:
        stmt = select(DataFactorySqlTemplateRow)
        if status:
            stmt = stmt.where(DataFactorySqlTemplateRow.status == status.value)
        stmt = stmt.order_by(DataFactorySqlTemplateRow.updated_at.desc(), DataFactorySqlTemplateRow.template_code.asc())
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
                row = DataFactorySqlTemplateRow(
                    id=_new_id(),
                    template_code=config.sourceCode,
                    template_name=config.sourceName,
                    datasource_code=config.datasourceCode,
                    operation=config.operation.value,
                    datasource_type="",  # 通过 datasourceCode 查询 dbType
                    sql_text=config.sqlText,
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
                row.template_name = config.sourceName
                row.datasource_code = config.datasourceCode
                row.operation = config.operation.value
                row.sql_text = config.sqlText
                row.parameters_json = _dumps([p.model_dump(mode="json") for p in config.parameters])
                row.safety_json = _dumps(config.safety.model_dump(mode="json"))
                row.status = config.status.value
                row.updated_by = operator
                row.updated_at = now
                action = "UPDATE_SQL_SOURCE"
            self._add_audit(session, "SQL_SOURCE", row.id, action, operator, None, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def disable_sql_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            row.status = ConfigStatus.DISABLED.value
            row.updated_by = operator
            row.updated_at = _now()
            self._add_audit(session, "SQL_SOURCE", row.id, "DISABLE_SQL_SOURCE", operator, None, {"sourceCode": source_code})
            await self._commit(session)
            return True

    # ========================= 内部辅助 =========================

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise SqlSourceConflictError("unique constraint violation") from exc

    async def _get_row(self, session: AsyncSession, source_code: str) -> DataFactorySqlTemplateRow | None:
        stmt = select(DataFactorySqlTemplateRow).where(DataFactorySqlTemplateRow.template_code == source_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_row(self, session: AsyncSession, source_code: str) -> DataFactorySqlTemplateRow:
        row = await self._get_row(session, source_code)
        if row is None:
            raise SqlSourceNotFoundError(f"SQL source not found: {source_code}")
        return row

    @staticmethod
    def _add_audit(session: AsyncSession, target_type: str, target_id: str, action: str, operator: str | None, before: Any, after: Any) -> None:
        session.add(DataFactoryConfigAuditRow(
            id=_new_id(), target_type=target_type, target_id=target_id,
            action=action, operator=operator,
            before_json=_dumps(before) if before is not None else None,
            after_json=_dumps(after) if after is not None else None,
            created_at=_now(),
        ))

    @staticmethod
    def _to_response(row: DataFactorySqlTemplateRow) -> SqlSourceResponse:
        return SqlSourceResponse(
            id=row.id,
            sourceCode=row.template_code,
            sourceName=row.template_name,
            datasourceCode=row.datasource_code,
            operation=row.operation,
            sqlText=row.sql_text,
            parameters=_loads(row.parameters_json, []),
            safety=_loads(row.safety_json, {}),
            status=row.status,
            createdBy=row.created_by,
            updatedBy=row.updated_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
