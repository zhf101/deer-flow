"""HTTP 接口配置持久化仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig, HttpSourceResponse
from app.gdp.datagen.config.base.repository import DataFactoryConfigAuditRow
from deerflow.persistence.base import Base


class DataFactoryHttpSourceRow(Base):
    """HTTP 接口配置持久化表。

    该表保存可复用 HTTP 接口定义本身，不保存环境维度 Base URL。运行时通过
    ``sys_code`` 找到所属系统，再结合调用入参里的环境编码解析服务端点前缀。
    JSON 字段用于保存前端可视化配置，避免把复杂请求/响应结构拆成过多子表。
    """

    __tablename__ = "df_http_source"

    # 主键与业务编码
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    source_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="HTTP 接口配置唯一编码。")
    source_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="HTTP 接口配置名称。")

    # 所属系统与请求地址
    sys_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属系统编码，关联 df_system.sys_code。")
    path: Mapped[str] = mapped_column(String(1024), nullable=False, comment="接口相对路径，不包含环境 Base URL。")
    method: Mapped[str] = mapped_column(String(16), nullable=False, comment="HTTP 请求方法。")

    # 请求构造配置
    request_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="请求映射配置 JSON。")
    body_schema_json: Mapped[str | None] = mapped_column(Text, comment="请求 Body 字段结构 JSON。")

    # 响应结构与结果提取配置
    response_schema_json: Mapped[str | None] = mapped_column(Text, comment="响应 Body 字段结构 JSON。")
    response_headers_schema_json: Mapped[str | None] = mapped_column(Text, comment="响应 Header 字段结构 JSON。")
    response_cookies_schema_json: Mapped[str | None] = mapped_column(Text, comment="响应 Cookie 字段结构 JSON。")
    response_handling_json: Mapped[str | None] = mapped_column(Text, comment="响应判定规则 JSON。")
    error_mapping_json: Mapped[str | None] = mapped_column(Text, comment="错误信息映射规则 JSON。")
    output_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="输出变量映射 JSON。")
    output_meta_json: Mapped[str | None] = mapped_column(Text, comment="输出变量展示元信息 JSON。")
    retry_policy_json: Mapped[str | None] = mapped_column(Text, comment="HTTP 重试策略 JSON。")

    # 状态与审计字段
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="配置状态。")
    created_by: Mapped[str | None] = mapped_column(String(128), comment="创建人标识。")
    updated_by: Mapped[str | None] = mapped_column(String(128), comment="最近更新人标识。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近更新时间。")


class HttpSourceNotFoundError(LookupError):
    """请求的 HTTP 配置不存在。"""


class HttpSourceConflictError(RuntimeError):
    """HTTP 配置违反唯一性约束。"""


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


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


class HttpSourceRepository:
    """可复用 HTTP 配置持久化仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_http_sources(
        self,
        *,
        sys_code: str | None = None,
        status: ConfigStatus | None = None,
    ) -> list[HttpSourceResponse]:
        stmt = select(DataFactoryHttpSourceRow)
        if sys_code:
            stmt = stmt.where(DataFactoryHttpSourceRow.sys_code == sys_code)
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
                    sys_code=config.sysCode,
                    path=config.path,
                    method=config.method.value,
                    request_mapping_json=_dumps(config.requestMapping),
                    body_schema_json=_dumps(_model_dump(config.bodySchema)) if config.bodySchema else None,
                    response_schema_json=_dumps(_model_dump(config.responseSchema)) if config.responseSchema else None,
                    response_headers_schema_json=_dumps(_model_dump(config.responseHeadersSchema)) if config.responseHeadersSchema else None,
                    response_cookies_schema_json=_dumps(_model_dump(config.responseCookiesSchema)) if config.responseCookiesSchema else None,
                    response_handling_json=_dumps(_model_dump(config.responseHandling)) if config.responseHandling else None,
                    error_mapping_json=_dumps(_model_dump(config.errorMapping)) if config.errorMapping else None,
                    output_mapping_json=_dumps(config.outputMapping),
                    output_meta_json=_dumps(config.outputMeta) if config.outputMeta else None,
                    retry_policy_json=_dumps(_model_dump(config.retryPolicy)) if config.retryPolicy else None,
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
                row.sys_code = config.sysCode
                row.path = config.path
                row.method = config.method.value
                row.request_mapping_json = _dumps(config.requestMapping)
                row.body_schema_json = _dumps(_model_dump(config.bodySchema)) if config.bodySchema else None
                row.response_schema_json = _dumps(_model_dump(config.responseSchema)) if config.responseSchema else None
                row.response_headers_schema_json = _dumps(_model_dump(config.responseHeadersSchema)) if config.responseHeadersSchema else None
                row.response_cookies_schema_json = _dumps(_model_dump(config.responseCookiesSchema)) if config.responseCookiesSchema else None
                row.response_handling_json = _dumps(_model_dump(config.responseHandling)) if config.responseHandling else None
                row.error_mapping_json = _dumps(_model_dump(config.errorMapping)) if config.errorMapping else None
                row.output_mapping_json = _dumps(config.outputMapping)
                row.output_meta_json = _dumps(config.outputMeta) if config.outputMeta else None
                row.retry_policy_json = _dumps(_model_dump(config.retryPolicy)) if config.retryPolicy else None
                row.status = config.status.value
                row.updated_by = operator
                row.updated_at = now
                action = "UPDATE_HTTP_SOURCE"
            self._add_audit(session, "HTTP_SOURCE", row.id, action, operator, config.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def disable_http_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            row.status = ConfigStatus.DISABLED.value
            row.updated_by = operator
            row.updated_at = _now()
            self._add_audit(session, "HTTP_SOURCE", row.id, "DISABLE_HTTP_SOURCE", operator, {"sourceCode": source_code})
            await self._commit(session)
            return True

    async def delete_http_source(self, source_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_row(session, source_code)
            self._add_audit(session, "HTTP_SOURCE", row.id, "DELETE_HTTP_SOURCE", operator, {"sourceCode": source_code})
            await session.delete(row)
            await self._commit(session)
            return True

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
    def _to_response(row: DataFactoryHttpSourceRow) -> HttpSourceResponse:
        return HttpSourceResponse(
            id=row.id,
            sourceCode=row.source_code,
            sourceName=row.source_name,
            sysCode=row.sys_code,
            path=row.path,
            method=row.method,
            requestMapping=_loads(row.request_mapping_json, {}),
            bodySchema=_loads(row.body_schema_json, None),
            responseSchema=_loads(row.response_schema_json, None),
            responseHeadersSchema=_loads(row.response_headers_schema_json, None),
            responseCookiesSchema=_loads(row.response_cookies_schema_json, None),
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
