"""造数任务仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gdp.datagen.task.models import (
    TaskDefinition,
    TaskSummary,
    TaskValidationResult,
    TaskVersion,
)
from app.gdp.models import SceneStatus, VersionStatus
from app.gdp.persistence.model import (
    DataFactoryConfigAuditRow,
    DataFactoryTaskRow,
    DataFactoryTaskVersionRow,
)


class TaskNotFoundError(LookupError):
    """请求的任务不存在。"""


class TaskConflictError(RuntimeError):
    """任务违反唯一约束。"""


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


class TaskRepository:
    """造数任务仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_tasks(
        self, *, keyword: str | None = None, status: SceneStatus | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[TaskSummary]:
        stmt = select(DataFactoryTaskRow)
        if status:
            stmt = stmt.where(DataFactoryTaskRow.status == status.value)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                DataFactoryTaskRow.task_code.like(pattern) | DataFactoryTaskRow.task_name.like(pattern)
            )
        stmt = stmt.order_by(DataFactoryTaskRow.updated_at.desc(), DataFactoryTaskRow.task_code.asc()).offset(offset).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._summary(row) for row in rows]

    async def create_task(self, definition: TaskDefinition, *, operator: str | None = None) -> TaskVersion:
        async with self._sf() as session:
            existing = await self._get_task_row(session, definition.taskCode)
            if existing is not None:
                raise TaskConflictError(f"taskCode already exists: {definition.taskCode}")
            now = _now()
            task = DataFactoryTaskRow(
                id=_new_id(), task_code=definition.taskCode, task_name=definition.taskName,
                task_remark=definition.taskRemark, status=SceneStatus.DRAFT.value,
                current_version_no=None, created_by=operator, updated_by=operator,
                created_at=now, updated_at=now,
            )
            session.add(task)
            version = self._make_version_row(task, definition, version_no=1, operator=operator)
            session.add(version)
            self._add_audit(session, "TASK", task.id, "CREATE", operator, None, definition.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(task)
            await session.refresh(version)
            return self._version(task, version)

    async def update_task(self, task_code: str, definition: TaskDefinition, *, operator: str | None = None) -> TaskVersion:
        if task_code != definition.taskCode:
            raise TaskConflictError("path taskCode must match request taskCode")
        async with self._sf() as session:
            task = await self._require_task_row(session, task_code)
            before = self._task_payload(task)
            task.task_name = definition.taskName
            task.task_remark = definition.taskRemark
            task.status = SceneStatus.DRAFT.value
            task.updated_by = operator
            task.updated_at = _now()
            version_no = await self._next_version_no(session, task.id)
            version = self._make_version_row(task, definition, version_no=version_no, operator=operator)
            session.add(version)
            self._add_audit(session, "TASK", task.id, "UPDATE_DRAFT", operator, before, definition.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(task)
            await session.refresh(version)
            return self._version(task, version)

    async def get_task_definition(self, task_code: str) -> TaskDefinition:
        async with self._sf() as session:
            task = await self._require_task_row(session, task_code)
            version = await self._require_latest_version(session, task.id)
            return self._definition_from_rows(task, version)

    async def publish_task(self, task_code: str, validation_result: TaskValidationResult, *, operator: str | None = None) -> TaskVersion:
        async with self._sf() as session:
            task = await self._require_task_row(session, task_code)
            version = await self._require_latest_version(session, task.id)
            if version.version_status == VersionStatus.PUBLISHED.value:
                return self._version(task, version)
            before = self._task_payload(task)
            now = _now()
            version.version_status = VersionStatus.PUBLISHED.value
            version.validation_result_json = _dumps(validation_result.model_dump(mode="json"))
            version.published_by = operator
            version.published_at = now
            task.status = SceneStatus.PUBLISHED.value
            task.current_version_no = version.version_no
            task.updated_by = operator
            task.updated_at = now
            self._add_audit(session, "TASK", task.id, "PUBLISH", operator, before, {"taskCode": task_code, "versionNo": version.version_no})
            await self._commit(session)
            await session.refresh(task)
            await session.refresh(version)
            return self._version(task, version)

    async def disable_task(self, task_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            task = await self._require_task_row(session, task_code)
            before = self._task_payload(task)
            task.status = SceneStatus.DISABLED.value
            task.updated_by = operator
            task.updated_at = _now()
            self._add_audit(session, "TASK", task.id, "DISABLE", operator, before, self._task_payload(task))
            await self._commit(session)
            return True

    async def delete_task(self, task_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            task = await self._require_task_row(session, task_code)
            before = self._task_payload(task)
            stmt_versions = select(DataFactoryTaskVersionRow).where(DataFactoryTaskVersionRow.task_id == task.id)
            versions = (await session.execute(stmt_versions)).scalars().all()
            for v in versions:
                await session.delete(v)
            await session.delete(task)
            self._add_audit(session, "TASK", task.id, "DELETE", operator, before, None)
            await self._commit(session)
            return True

    async def list_task_versions(self, task_code: str) -> list[TaskVersion]:
        async with self._sf() as session:
            task = await self._require_task_row(session, task_code)
            stmt = (
                select(DataFactoryTaskVersionRow)
                .where(DataFactoryTaskVersionRow.task_id == task.id)
                .order_by(DataFactoryTaskVersionRow.version_no.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._version(task, row) for row in rows]

    # ========================= 内部辅助 =========================

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise TaskConflictError("unique constraint violation") from exc

    async def _get_task_row(self, session: AsyncSession, task_code: str) -> DataFactoryTaskRow | None:
        stmt = select(DataFactoryTaskRow).where(DataFactoryTaskRow.task_code == task_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_task_row(self, session: AsyncSession, task_code: str) -> DataFactoryTaskRow:
        row = await self._get_task_row(session, task_code)
        if row is None:
            raise TaskNotFoundError(f"task not found: {task_code}")
        return row

    async def _next_version_no(self, session: AsyncSession, task_id: str) -> int:
        stmt = select(func.coalesce(func.max(DataFactoryTaskVersionRow.version_no), 0)).where(
            DataFactoryTaskVersionRow.task_id == task_id
        )
        return int((await session.execute(stmt)).scalar_one()) + 1

    async def _require_latest_version(self, session: AsyncSession, task_id: str) -> DataFactoryTaskVersionRow:
        stmt = (
            select(DataFactoryTaskVersionRow)
            .where(DataFactoryTaskVersionRow.task_id == task_id)
            .order_by(DataFactoryTaskVersionRow.version_no.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise TaskNotFoundError("task version not found")
        return row

    @staticmethod
    def _make_version_row(task: DataFactoryTaskRow, definition: TaskDefinition, *, version_no: int, operator: str | None) -> DataFactoryTaskVersionRow:
        return DataFactoryTaskVersionRow(
            id=_new_id(), task_id=task.id, task_code=task.task_code,
            version_no=version_no, version_status=VersionStatus.DRAFT.value,
            input_schema_json=_dumps([f.model_dump(mode="json") for f in definition.inputSchema]),
            steps_json=_dumps([s.model_dump(mode="json") for s in definition.steps]),
            result_mapping_json=_dumps(definition.resultMapping),
            validation_result_json=None,
            created_by=operator, created_at=_now(),
        )

    @staticmethod
    def _definition_from_rows(task: DataFactoryTaskRow, version: DataFactoryTaskVersionRow) -> TaskDefinition:
        return TaskDefinition(
            taskCode=task.task_code, taskName=task.task_name, taskRemark=task.task_remark,
            inputSchema=_loads(version.input_schema_json, []),
            steps=_loads(version.steps_json, []),
            resultMapping=_loads(version.result_mapping_json, {}),
            status=task.status,
        )

    @staticmethod
    def _summary(row: DataFactoryTaskRow) -> TaskSummary:
        return TaskSummary(
            id=row.id, taskCode=row.task_code, taskName=row.task_name,
            taskRemark=row.task_remark, status=row.status,
            currentVersionNo=row.current_version_no,
            createdBy=row.created_by, updatedBy=row.updated_by,
            createdAt=row.created_at, updatedAt=row.updated_at,
        )

    @staticmethod
    def _version(task: DataFactoryTaskRow, version: DataFactoryTaskVersionRow) -> TaskVersion:
        return TaskVersion(
            id=version.id, taskCode=version.task_code,
            versionNo=version.version_no, versionStatus=version.version_status,
            definition=TaskRepository._definition_from_rows(task, version),
            validationResult=_loads(version.validation_result_json, None),
            createdBy=version.created_by, createdAt=version.created_at,
            publishedBy=version.published_by, publishedAt=version.published_at,
        )

    @staticmethod
    def _task_payload(row: DataFactoryTaskRow) -> dict[str, Any]:
        return {"taskCode": row.task_code, "taskName": row.task_name, "status": row.status, "currentVersionNo": row.current_version_no}

    @staticmethod
    def _add_audit(session: AsyncSession, target_type: str, target_id: str, action: str, operator: str | None, before: Any, after: Any) -> None:
        session.add(DataFactoryConfigAuditRow(
            id=_new_id(), target_type=target_type, target_id=target_id,
            action=action, operator=operator,
            before_json=_dumps(before) if before is not None else None,
            after_json=_dumps(after) if after is not None else None,
            created_at=_now(),
        ))
