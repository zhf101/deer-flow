"""HTTP 接口配置仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gdp.datagen.httpsource.models import HttpSourceConfig, HttpSourceResponse
from app.gdp.models import ConfigStatus
from app.gdp.persistence.model import DataFactoryConfigAuditRow, DataFactoryHttpSourceRow


class HttpSourceNotFoundError(LookupError):
    """请求的 HTTP 接口配置不存在。"""


class HttpSourceConflictError(RuntimeError):
    """HTTP 接口配置违反唯一约束。"""


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


class HttpSourceRepository:
    """HTTP 接口配置仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_http_sources(self, *, status: ConfigStatus | None = None) -> list[HttpSourceResponse]:
        stmt = select(DataFactoryHttpSourceRow)
        if status:
            stmt = stmt.where(DataFactoryHttpSourceRow.status == status.value)
        stmt = stmt.order_by(DataFactoryHttpSourceRow.updated_at.desc(), DataFactoryHttpSourceRow.source_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_response(row) for row in rows]

    async def get_http_source(self, source_code: str) -> HttpSourceResponse:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            return self._to_response(row)

    async def upsert_http_source(self, config: HttpSourceConfig, *, operator: str | None = None) -> HttpSourceResponse:
        async with self._sf() as session:
            row = await self._get_row(session, config.sourceCode)
            now = _now()
            if row is None:
                row = DataFactoryHttpSourceRow(
                    id=_new_id(),
                    source_code=config.sourceCode,
                    source_name=config.sourceName,
                    service_code=config.serviceCode,
                    path=config.path,
                    method=config.method.value,
                    request_mapping_json=_dumps(config.requestMapping),
                    body_schema_json=_dumps(config.bodySchema) if config.bodySchema else None,
                    response_handling_json=_dumps(config.responseHandling.model_dump(mode="json")) if config.responseHandling else None,
                    error_mapping_json=_dumps(config.errorMapping.model_dump(mode="json")) if config.errorMapping else None,
                    output_mapping_json=_dumps(config.outputMapping),
                    output_meta_json=_dumps(config.outputMeta) if config.outputMeta else None,
                    retry_policy_json=_dumps(config.retryPolicy.model_dump(mode="json")) if config.retryPolicy else None,
                    status=config.status.value,
                    created_by=operator,
                    updated_by=operator,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                action = "CREATE_HTTP_SOURCE"
            else:
                row.source_name = config.sourceName
                row.service_code = config.serviceCode
                row.path = config.path
                row.method = config.method.value
                row.request_mapping_json = _dumps(config.requestMapping)
                row.body_schema_json = _dumps(config.bodySchema) if config.bodySchema else None
                row.response_handling_json = _dumps(config.responseHandling.model_dump(mode="json")) if config.responseHandling else None
                row.error_mapping_json = _dumps(config.errorMapping.model_dump(mode="json")) if config.errorMapping else None
                row.output_mapping_json = _dumps(config.outputMapping)
                row.output_meta_json = _dumps(config.outputMeta) if config.outputMeta else None
                row.retry_policy_json = _dumps(config.retryPolicy.model_dump(mode="json")) if config.retryPolicy else None
                row.status = config.status.value
                row.updated_by = operator
                row.updated_at = now
                action = "UPDATE_HTTP_SOURCE"
            self._add_audit(session, "HTTP_SOURCE", row.id, action, operator, None, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def disable_http_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            row.status = ConfigStatus.DISABLED.value
            row.updated_by = operator
            row.updated_at = _now()
            self._add_audit(session, "HTTP_SOURCE", row.id, "DISABLE_HTTP_SOURCE", operator, None, {"sourceCode": source_code})
            await self._commit(session)
            return True

    async def delete_http_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            before = {"sourceCode": source_code}
            await session.delete(row)
            self._add_audit(session, "HTTP_SOURCE", row.id, "DELETE_HTTP_SOURCE", operator, before, None)
            await self._commit(session)
            return True

    # ========================= 内部辅助 =========================

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HttpSourceConflictError("unique constraint violation") from exc

    async def _get_row(self, session: AsyncSession, source_code: str) -> DataFactoryHttpSourceRow | None:
        stmt = select(DataFactoryHttpSourceRow).where(DataFactoryHttpSourceRow.source_code == source_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_row(self, session: AsyncSession, source_code: str) -> DataFactoryHttpSourceRow:
        row = await self._get_row(session, source_code)
        if row is None:
            raise HttpSourceNotFoundError(f"HTTP source not found: {source_code}")
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
    def _to_response(row: DataFactoryHttpSourceRow) -> HttpSourceResponse:
        return HttpSourceResponse(
            id=row.id,
            sourceCode=row.source_code,
            sourceName=row.source_name,
            serviceCode=row.service_code,
            path=row.path,
            method=row.method,
            requestMapping=_loads(row.request_mapping_json, {}),
            bodySchema=_loads(row.body_schema_json, None),
            responseHandling=_loads(row.response_handling_json, None),
            errorMapping=_loads(row.error_mapping_json, None),
            outputMapping=_loads(row.output_mapping_json, {}),
            outputMeta=_loads(row.output_meta_json, None),
            retryPolicy=_loads(row.retry_policy_json, None),
            status=row.status,
            createdBy=row.created_by,
            updatedBy=row.updated_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
