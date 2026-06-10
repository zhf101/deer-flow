"""造数子任务持久化仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskSubagentType,
    DatagenTaskSubtaskCreateRequest,
    DatagenTaskSubtaskResponse,
    DatagenTaskSubtaskStatus,
    DatagenTaskSubtaskUpdateRequest,
)
from app.gdp.datagen.config.task.repository import DataFactoryDatagenTaskRunRow, DatagenTaskNotFoundError
from deerflow.persistence.base import Base


class DataFactoryDatagenTaskSubtaskRow(Base):
    """用户级造数子任务表。"""

    __tablename__ = "df_datagen_task_subtask"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属任务运行 ID。")
    subtask_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="子任务业务 ID。")
    parent_step_id: Mapped[str | None] = mapped_column(String(64), comment="父任务步骤 ID。")
    phase: Mapped[str] = mapped_column(String(64), nullable=False, comment="子任务归属阶段。")
    subagent_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="子 Agent 类型。")
    goal: Mapped[str] = mapped_column(Text, nullable=False, comment="子任务目标。")
    operation_id: Mapped[str | None] = mapped_column(String(128), comment="外部执行或子 Agent 运行 ID。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="子任务状态。")
    input_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, comment="输入快照 JSON。")
    result_summary_json: Mapped[str | None] = mapped_column(Text, comment="结果摘要 JSON。")
    result_payload_json: Mapped[str | None] = mapped_column(Text, comment="完整结果 JSON。")
    result_ref_json: Mapped[str | None] = mapped_column(Text, comment="结果引用 JSON。")
    token_usage_json: Mapped[str | None] = mapped_column(Text, comment="模型成本 JSON。")
    error_type: Mapped[str | None] = mapped_column(String(128), comment="失败类型。")
    error_message: Mapped[str | None] = mapped_column(Text, comment="失败说明。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近更新时间。")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="开始时间。")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间。")


class DatagenTaskSubtaskConflictError(RuntimeError):
    """造数子任务违反唯一性约束。"""


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


class DatagenTaskSubtaskRepository:
    """造数子任务持久化仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskCreateRequest,
    ) -> DatagenTaskSubtaskResponse:
        now = _now()
        row = DataFactoryDatagenTaskSubtaskRow(
            id=_new_id(),
            task_run_id=task_run_id,
            subtask_id=_new_id("subtask_"),
            parent_step_id=request.parentStepId,
            phase=request.phase.value,
            subagent_type=request.subagentType.value,
            goal=request.goal,
            operation_id=request.operationId,
            status=DatagenTaskSubtaskStatus.PENDING.value,
            input_snapshot_json=_dumps(request.inputSnapshot),
            result_summary_json=None,
            result_payload_json=None,
            result_ref_json=None,
            token_usage_json=None,
            error_type=None,
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            finished_at=None,
        )
        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    async def list_subtasks(self, task_run_id: str) -> list[DatagenTaskSubtaskResponse]:
        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            stmt = (
                select(DataFactoryDatagenTaskSubtaskRow)
                .where(DataFactoryDatagenTaskSubtaskRow.task_run_id == task_run_id)
                .order_by(DataFactoryDatagenTaskSubtaskRow.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_response(row) for row in rows]

    async def get_subtask(self, task_run_id: str, subtask_id: str) -> DatagenTaskSubtaskResponse:
        async with self._sf() as session:
            row = await self._require_subtask_row(session, task_run_id, subtask_id)
            return self._to_response(row)

    async def update_subtask(
        self,
        task_run_id: str,
        request: DatagenTaskSubtaskUpdateRequest,
    ) -> DatagenTaskSubtaskResponse:
        async with self._sf() as session:
            row = await self._require_subtask_row(session, task_run_id, request.subtaskId)
            now = _now()
            if request.status is not None:
                row.status = request.status.value
                if request.status == DatagenTaskSubtaskStatus.RUNNING and row.started_at is None:
                    row.started_at = now
                if request.status in {
                    DatagenTaskSubtaskStatus.SUCCESS,
                    DatagenTaskSubtaskStatus.FAILED,
                    DatagenTaskSubtaskStatus.CANCELLED,
                }:
                    row.finished_at = now
            if request.operationId is not None:
                row.operation_id = request.operationId
            if request.resultSummary is not None:
                row.result_summary_json = _dumps(request.resultSummary)
            if request.resultPayload is not None:
                row.result_payload_json = _dumps(request.resultPayload)
            if request.resultRef is not None:
                row.result_ref_json = _dumps(request.resultRef)
            if request.tokenUsage is not None:
                row.token_usage_json = _dumps(request.tokenUsage)
            if request.errorType is not None:
                row.error_type = request.errorType
            if request.errorMessage is not None:
                row.error_message = request.errorMessage
            row.updated_at = now
            await self._commit(session)
            await session.refresh(row)
            return self._to_response(row)

    @staticmethod
    async def _require_run_row(session: AsyncSession, task_run_id: str) -> DataFactoryDatagenTaskRunRow:
        stmt = select(DataFactoryDatagenTaskRunRow).where(DataFactoryDatagenTaskRunRow.task_run_id == task_run_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise DatagenTaskNotFoundError(f"datagen task run not found: {task_run_id}")
        return row

    async def _require_subtask_row(
        self,
        session: AsyncSession,
        task_run_id: str,
        subtask_id: str,
    ) -> DataFactoryDatagenTaskSubtaskRow:
        await self._require_run_row(session, task_run_id)
        stmt = select(DataFactoryDatagenTaskSubtaskRow).where(
            DataFactoryDatagenTaskSubtaskRow.task_run_id == task_run_id,
            DataFactoryDatagenTaskSubtaskRow.subtask_id == subtask_id,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise DatagenTaskNotFoundError(f"datagen task subtask not found: {subtask_id}")
        return row

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DatagenTaskSubtaskConflictError("unique constraint violation") from exc

    @staticmethod
    def _to_response(row: DataFactoryDatagenTaskSubtaskRow) -> DatagenTaskSubtaskResponse:
        return DatagenTaskSubtaskResponse(
            id=row.id,
            taskRunId=row.task_run_id,
            subtaskId=row.subtask_id,
            parentStepId=row.parent_step_id,
            phase=row.phase,
            subagentType=row.subagent_type,
            goal=row.goal,
            operationId=row.operation_id,
            status=row.status,
            inputSnapshot=_loads(row.input_snapshot_json, {}),
            resultSummary=_loads(row.result_summary_json, None),
            resultPayload=_loads(row.result_payload_json, None),
            resultRef=_loads(row.result_ref_json, None),
            tokenUsage=_loads(row.token_usage_json, None),
            errorType=row.error_type,
            errorMessage=row.error_message,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
            startedAt=row.started_at,
            finishedAt=row.finished_at,
        )
