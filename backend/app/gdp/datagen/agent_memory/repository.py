"""GDP Agent 记忆持久化仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.agent_memory.models import (
    GDPAgentMemoryCategory,
    GDPAgentMemoryFactCreateRequest,
    GDPAgentMemoryFactResponse,
    GDPAgentMemoryFactUpdateRequest,
    GDPAgentMemoryScopeType,
    GDPAgentMemoryStatus,
)
from deerflow.persistence.base import Base


class DataFactoryGDPAgentMemoryFactRow(Base):
    """GDP Agent 记忆事实表。"""

    __tablename__ = "df_gdp_agent_memory_fact"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    fact_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="记忆事实业务 ID。")
    user_id: Mapped[str | None] = mapped_column(String(128), comment="用户 ID。")
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Agent 名称。")
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="作用域类型。")
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="作用域键。")
    category: Mapped[str] = mapped_column(String(64), nullable=False, comment="记忆分类。")
    memory_key: Mapped[str] = mapped_column(String(256), nullable=False, comment="记忆事实键。")
    value_json: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆结构化值 JSON。")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, comment="置信度。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="状态。")
    source_task_run_id: Mapped[str | None] = mapped_column(String(64), comment="来源任务 ID。")
    source_event_ids_json: Mapped[str] = mapped_column(Text, nullable=False, comment="来源事件 ID 列表 JSON。")
    evidence_summary: Mapped[str | None] = mapped_column(Text, comment="证据摘要。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近更新时间。")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近使用时间。")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="使用次数。")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="成功次数。")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="失败次数。")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="过期时间。")

    __table_args__ = (
        UniqueConstraint(
            "agent_name",
            "user_id",
            "scope_type",
            "scope_key",
            "category",
            "memory_key",
            name="uq_df_gdp_agent_memory_fact",
        ),
    )


class GDPAgentMemoryNotFoundError(LookupError):
    """请求的 GDP Agent 记忆事实不存在。"""


class GDPAgentMemoryConflictError(RuntimeError):
    """GDP Agent 记忆事实违反唯一性约束。"""


def _new_id(prefix: str = "") -> str:
    value = str(uuid.uuid4())
    return f"{prefix}{value}" if prefix else value


def _now() -> datetime:
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


class GDPAgentMemoryRepository:
    """GDP Agent 记忆事实仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create_fact(self, request: GDPAgentMemoryFactCreateRequest) -> GDPAgentMemoryFactResponse:
        now = _now()
        row = DataFactoryGDPAgentMemoryFactRow(
            id=_new_id(),
            fact_id=_new_id("mem_"),
            user_id=request.userId,
            agent_name=request.agentName,
            scope_type=request.scopeType.value,
            scope_key=request.scopeKey,
            category=request.category.value,
            memory_key=request.memoryKey,
            value_json=_dumps(request.value),
            confidence=request.confidence,
            status=GDPAgentMemoryStatus.ACTIVE.value,
            source_task_run_id=request.sourceTaskRunId,
            source_event_ids_json=_dumps(request.sourceEventIds),
            evidence_summary=request.evidenceSummary,
            created_at=now,
            updated_at=now,
            last_used_at=None,
            use_count=0,
            success_count=0,
            failure_count=0,
            expires_at=request.expiresAt,
        )
        async with self._sf() as session:
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def list_facts(
        self,
        *,
        user_id: str | None = None,
        agent_name: str | None = None,
        category: GDPAgentMemoryCategory | None = None,
        scope_type: GDPAgentMemoryScopeType | None = None,
        scope_key: str | None = None,
        status: GDPAgentMemoryStatus | None = None,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GDPAgentMemoryFactResponse]:
        stmt = select(DataFactoryGDPAgentMemoryFactRow)
        if user_id is not None:
            stmt = stmt.where(DataFactoryGDPAgentMemoryFactRow.user_id == user_id)
        if agent_name is not None:
            stmt = stmt.where(DataFactoryGDPAgentMemoryFactRow.agent_name == agent_name)
        if category is not None:
            stmt = stmt.where(DataFactoryGDPAgentMemoryFactRow.category == category.value)
        if scope_type is not None:
            stmt = stmt.where(DataFactoryGDPAgentMemoryFactRow.scope_type == scope_type.value)
        if scope_key is not None:
            stmt = stmt.where(DataFactoryGDPAgentMemoryFactRow.scope_key == scope_key)
        if status is not None:
            stmt = stmt.where(DataFactoryGDPAgentMemoryFactRow.status == status.value)
        if active_only:
            now = _now()
            stmt = stmt.where(
                DataFactoryGDPAgentMemoryFactRow.status == GDPAgentMemoryStatus.ACTIVE.value,
                or_(
                    DataFactoryGDPAgentMemoryFactRow.expires_at.is_(None),
                    DataFactoryGDPAgentMemoryFactRow.expires_at > now,
                ),
            )
        stmt = stmt.order_by(
            DataFactoryGDPAgentMemoryFactRow.confidence.desc(),
            DataFactoryGDPAgentMemoryFactRow.updated_at.desc(),
        ).limit(limit).offset(offset)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_response(row) for row in rows]

    async def update_fact(self, request: GDPAgentMemoryFactUpdateRequest) -> GDPAgentMemoryFactResponse:
        async with self._sf() as session:
            row = await self._require_row(session, request.factId)
            if request.value is not None:
                row.value_json = _dumps(request.value)
            if request.confidence is not None:
                row.confidence = request.confidence
            if request.status is not None:
                row.status = request.status.value
            if request.evidenceSummary is not None:
                row.evidence_summary = request.evidenceSummary
            if request.expiresAt is not None:
                row.expires_at = request.expiresAt
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def mark_used(self, fact_ids: list[str]) -> None:
        if not fact_ids:
            return
        async with self._sf() as session:
            stmt = select(DataFactoryGDPAgentMemoryFactRow).where(DataFactoryGDPAgentMemoryFactRow.fact_id.in_(fact_ids))
            rows = (await session.execute(stmt)).scalars().all()
            now = _now()
            for row in rows:
                row.last_used_at = now
                row.use_count += 1
                row.updated_at = now
            await self._commit(session)

    async def delete_fact(self, fact_id: str) -> None:
        async with self._sf() as session:
            await self._require_row(session, fact_id)
            await session.execute(delete(DataFactoryGDPAgentMemoryFactRow).where(DataFactoryGDPAgentMemoryFactRow.fact_id == fact_id))
            await self._commit(session)

    async def _require_row(self, session: AsyncSession, fact_id: str) -> DataFactoryGDPAgentMemoryFactRow:
        stmt = select(DataFactoryGDPAgentMemoryFactRow).where(DataFactoryGDPAgentMemoryFactRow.fact_id == fact_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise GDPAgentMemoryNotFoundError(f"gdp agent memory fact not found: {fact_id}")
        return row

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise GDPAgentMemoryConflictError("unique constraint violation") from exc

    @staticmethod
    def _to_response(row: DataFactoryGDPAgentMemoryFactRow) -> GDPAgentMemoryFactResponse:
        return GDPAgentMemoryFactResponse(
            id=row.id,
            factId=row.fact_id,
            userId=row.user_id,
            agentName=row.agent_name,
            scopeType=row.scope_type,
            scopeKey=row.scope_key,
            category=row.category,
            memoryKey=row.memory_key,
            value=_loads(row.value_json, {}),
            confidence=row.confidence,
            status=row.status,
            sourceTaskRunId=row.source_task_run_id,
            sourceEventIds=_loads(row.source_event_ids_json, []),
            evidenceSummary=row.evidence_summary,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
            lastUsedAt=row.last_used_at,
            useCount=row.use_count,
            successCount=row.success_count,
            failureCount=row.failure_count,
            expiresAt=row.expires_at,
        )
