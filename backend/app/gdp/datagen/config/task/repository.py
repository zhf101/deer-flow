"""造数任务控制面持久化仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.task.models import (
    DatagenTaskEnvSource,
    DatagenTaskEventResponse,
    DatagenTaskPhase,
    DatagenTaskPlan,
    DatagenTaskRunResponse,
    DatagenTaskStatus,
    DatagenTaskStepResponse,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
    GoalStackItem,
    VisibleVariable,
)
from deerflow.persistence.base import Base


class DataFactoryDatagenTaskRunRow(Base):
    """用户级造数任务运行表。"""

    __tablename__ = "df_datagen_task_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="任务运行业务 ID。")
    deerflow_thread_id: Mapped[str | None] = mapped_column(String(128), comment="绑定的 DeerFlow thread ID。")
    deerflow_run_id: Mapped[str | None] = mapped_column(String(128), comment="最近一次 DeerFlow run ID。")
    last_checkpoint_id: Mapped[str | None] = mapped_column(String(128), comment="最近一次 checkpoint ID。")
    user_intent: Mapped[str] = mapped_column(Text, nullable=False, comment="用户原始自然语言目标。")
    normalized_goal_json: Mapped[str] = mapped_column(Text, nullable=False, comment="结构化任务目标 JSON。")
    env_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="任务目标环境编码。")
    env_source: Mapped[str] = mapped_column(String(32), nullable=False, comment="任务环境来源。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="任务状态。")
    phase: Mapped[str] = mapped_column(String(64), nullable=False, comment="任务当前阶段。")
    pending_interrupts_json: Mapped[str | None] = mapped_column(Text, comment="等待用户输入的中断上下文 JSON。")
    goal_stack_json: Mapped[str] = mapped_column(Text, nullable=False, comment="递归目标栈 JSON。")
    plan_json: Mapped[str | None] = mapped_column(Text, comment="任务计划 JSON。")
    visible_variables_json: Mapped[str] = mapped_column(Text, nullable=False, comment="变量栈 JSON。")
    reflection_json: Mapped[str | None] = mapped_column(Text, comment="任务反思 JSON。")
    failure_type: Mapped[str | None] = mapped_column(String(128), comment="失败类型。")
    failure_message: Mapped[str | None] = mapped_column(Text, comment="失败说明。")
    final_summary: Mapped[str | None] = mapped_column(Text, comment="最终总结。")
    created_by: Mapped[str | None] = mapped_column(String(128), comment="创建人标识。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近更新时间。")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="任务结束时间。")


class DataFactoryDatagenTaskStepRow(Base):
    """用户级造数任务步骤表。"""

    __tablename__ = "df_datagen_task_step"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属任务运行 ID。")
    task_step_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="任务步骤业务 ID。")
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤序号。")
    phase: Mapped[str] = mapped_column(String(64), nullable=False, comment="步骤所在阶段。")
    step_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="步骤类型。")
    goal: Mapped[str] = mapped_column(Text, nullable=False, comment="步骤目标。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="步骤状态。")
    selected_resource_json: Mapped[str | None] = mapped_column(Text, comment="选中资源 JSON。")
    input_binding_json: Mapped[str | None] = mapped_column(Text, comment="入参绑定 JSON。")
    output_json: Mapped[str | None] = mapped_column(Text, comment="步骤输出 JSON。")
    scene_run_id: Mapped[str | None] = mapped_column(String(64), comment="关联场景运行 ID。")
    error_type: Mapped[str | None] = mapped_column(String(128), comment="错误类型。")
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误说明。")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="开始时间。")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间。")


class DataFactoryDatagenTaskEventRow(Base):
    """用户级造数任务事件表。"""

    __tablename__ = "df_datagen_task_event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属任务运行 ID。")
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="事件业务 ID。")
    event_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="任务内事件序号。")
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="事件类型。")
    phase: Mapped[str] = mapped_column(String(64), nullable=False, comment="事件发生阶段。")
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="事件说明。")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, comment="事件详情 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="事件发生时间。")


class DatagenTaskNotFoundError(LookupError):
    """请求的造数任务不存在。"""


class DatagenTaskConflictError(RuntimeError):
    """造数任务违反唯一性约束。"""


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


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    return value


class DatagenTaskRepository:
    """造数任务控制面持久化仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create_task_run(
        self,
        *,
        user_intent: str,
        env_code: str,
        env_source: DatagenTaskEnvSource,
        normalized_goal: dict[str, Any],
        goal_stack: list[GoalStackItem],
        plan: DatagenTaskPlan | None,
        visible_variables: list[VisibleVariable],
        operator: str | None = None,
        deerflow_thread_id: str | None = None,
    ) -> DatagenTaskRunResponse:
        now = _now()
        row = DataFactoryDatagenTaskRunRow(
            id=_new_id(),
            task_run_id=_new_id("task_"),
            deerflow_thread_id=deerflow_thread_id,
            deerflow_run_id=None,
            last_checkpoint_id=None,
            user_intent=user_intent,
            normalized_goal_json=_dumps(normalized_goal),
            env_code=env_code,
            env_source=env_source.value,
            status=DatagenTaskStatus.PLANNING.value,
            phase=DatagenTaskPhase.INTAKE.value,
            pending_interrupts_json=None,
            goal_stack_json=_dumps(_model_dump(goal_stack)),
            plan_json=_dumps(_model_dump(plan)) if plan is not None else None,
            visible_variables_json=_dumps(_model_dump(visible_variables)),
            reflection_json=None,
            failure_type=None,
            failure_message=None,
            final_summary=None,
            created_by=operator,
            created_at=now,
            updated_at=now,
            finished_at=None,
        )
        async with self._sf() as session:
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._to_run_response(row)

    async def list_task_runs(
        self,
        *,
        status: DatagenTaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DatagenTaskRunResponse]:
        stmt = select(DataFactoryDatagenTaskRunRow).order_by(DataFactoryDatagenTaskRunRow.updated_at.desc())
        if status:
            stmt = stmt.where(DataFactoryDatagenTaskRunRow.status == status.value)
        stmt = stmt.limit(limit).offset(offset)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_run_response(row) for row in rows]

    async def get_task_run(self, task_run_id: str) -> DatagenTaskRunResponse:
        async with self._sf() as session:
            row = await self._require_run_row(session, task_run_id)
            return self._to_run_response(row)

    async def update_status(
        self,
        task_run_id: str,
        *,
        status: DatagenTaskStatus,
        phase: DatagenTaskPhase | None = None,
        pending_interrupts: dict[str, Any] | None = None,
        final_summary: str | None = None,
        failure_type: str | None = None,
        failure_message: str | None = None,
    ) -> DatagenTaskRunResponse:
        async with self._sf() as session:
            row = await self._require_run_row(session, task_run_id)
            row.status = status.value
            if phase is not None:
                row.phase = phase.value
            if pending_interrupts is not None:
                row.pending_interrupts_json = _dumps(pending_interrupts)
            elif status != DatagenTaskStatus.WAITING_USER:
                row.pending_interrupts_json = None
            row.final_summary = final_summary if final_summary is not None else row.final_summary
            row.failure_type = failure_type if failure_type is not None else row.failure_type
            row.failure_message = failure_message if failure_message is not None else row.failure_message
            row.updated_at = _now()
            if status in {DatagenTaskStatus.COMPLETED, DatagenTaskStatus.FAILED, DatagenTaskStatus.CANCELLED}:
                row.finished_at = row.updated_at
            await self._commit(session)
            await session.refresh(row)
            return self._to_run_response(row)

    async def update_visible_variables(
        self,
        task_run_id: str,
        *,
        visible_variables: list[VisibleVariable],
    ) -> DatagenTaskRunResponse:
        """更新任务变量栈。"""

        async with self._sf() as session:
            row = await self._require_run_row(session, task_run_id)
            row.visible_variables_json = _dumps(_model_dump(visible_variables))
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._to_run_response(row)

    async def update_deerflow_binding(
        self,
        task_run_id: str,
        *,
        deerflow_thread_id: str | None = None,
        deerflow_run_id: str | None = None,
        last_checkpoint_id: str | None = None,
    ) -> DatagenTaskRunResponse:
        """更新任务和 DeerFlow Runtime 的绑定信息。"""

        async with self._sf() as session:
            row = await self._require_run_row(session, task_run_id)
            if deerflow_thread_id is not None:
                row.deerflow_thread_id = deerflow_thread_id
            if deerflow_run_id is not None:
                row.deerflow_run_id = deerflow_run_id
            if last_checkpoint_id is not None:
                row.last_checkpoint_id = last_checkpoint_id
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._to_run_response(row)

    async def create_step(
        self,
        *,
        task_run_id: str,
        step_no: int,
        phase: DatagenTaskPhase,
        step_type: DatagenTaskStepType,
        goal: str,
        status: DatagenTaskStepStatus = DatagenTaskStepStatus.PENDING,
        selected_resource: dict[str, Any] | None = None,
        input_binding: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        scene_run_id: str | None = None,
    ) -> DatagenTaskStepResponse:
        row = DataFactoryDatagenTaskStepRow(
            id=_new_id(),
            task_run_id=task_run_id,
            task_step_id=_new_id("step_"),
            step_no=step_no,
            phase=phase.value,
            step_type=step_type.value,
            goal=goal,
            status=status.value,
            selected_resource_json=_dumps(selected_resource) if selected_resource is not None else None,
            input_binding_json=_dumps(input_binding) if input_binding is not None else None,
            output_json=_dumps(output) if output is not None else None,
            scene_run_id=scene_run_id,
            error_type=None,
            error_message=None,
            started_at=None,
            finished_at=None,
        )
        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._to_step_response(row)

    async def list_steps(self, task_run_id: str) -> list[DatagenTaskStepResponse]:
        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            stmt = (
                select(DataFactoryDatagenTaskStepRow)
                .where(DataFactoryDatagenTaskStepRow.task_run_id == task_run_id)
                .order_by(DataFactoryDatagenTaskStepRow.step_no.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_step_response(row) for row in rows]

    async def update_step_status(
        self,
        task_run_id: str,
        task_step_id: str,
        *,
        status: DatagenTaskStepStatus,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> DatagenTaskStepResponse:
        """更新任务步骤状态，用于服务重启后的非终态步骤恢复。"""

        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            stmt = select(DataFactoryDatagenTaskStepRow).where(
                DataFactoryDatagenTaskStepRow.task_run_id == task_run_id,
                DataFactoryDatagenTaskStepRow.task_step_id == task_step_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise DatagenTaskNotFoundError(f"datagen task step not found: {task_step_id}")
            row.status = status.value
            row.error_type = error_type if error_type is not None else row.error_type
            row.error_message = error_message if error_message is not None else row.error_message
            if status in {DatagenTaskStepStatus.SUCCESS, DatagenTaskStepStatus.FAILED, DatagenTaskStepStatus.SKIPPED}:
                row.finished_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._to_step_response(row)

    async def record_event(
        self,
        *,
        task_run_id: str,
        event_type: str,
        phase: DatagenTaskPhase,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> DatagenTaskEventResponse:
        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            event_no = await self._next_event_no(session, task_run_id)
            row = DataFactoryDatagenTaskEventRow(
                id=_new_id(),
                task_run_id=task_run_id,
                event_id=_new_id("event_"),
                event_no=event_no,
                event_type=event_type,
                phase=phase.value,
                message=message,
                payload_json=_dumps(payload or {}),
                created_at=_now(),
            )
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._to_event_response(row)

    async def list_events(self, task_run_id: str) -> list[DatagenTaskEventResponse]:
        async with self._sf() as session:
            await self._require_run_row(session, task_run_id)
            stmt = (
                select(DataFactoryDatagenTaskEventRow)
                .where(DataFactoryDatagenTaskEventRow.task_run_id == task_run_id)
                .order_by(DataFactoryDatagenTaskEventRow.event_no.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_event_response(row) for row in rows]

    async def _next_event_no(self, session: AsyncSession, task_run_id: str) -> int:
        stmt = select(func.max(DataFactoryDatagenTaskEventRow.event_no)).where(
            DataFactoryDatagenTaskEventRow.task_run_id == task_run_id
        )
        current = (await session.execute(stmt)).scalar_one()
        return int(current or 0) + 1

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DatagenTaskConflictError("unique constraint violation") from exc

    async def _require_run_row(self, session: AsyncSession, task_run_id: str) -> DataFactoryDatagenTaskRunRow:
        stmt = select(DataFactoryDatagenTaskRunRow).where(DataFactoryDatagenTaskRunRow.task_run_id == task_run_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise DatagenTaskNotFoundError(f"datagen task run not found: {task_run_id}")
        return row

    @staticmethod
    def _to_run_response(row: DataFactoryDatagenTaskRunRow) -> DatagenTaskRunResponse:
        return DatagenTaskRunResponse(
            id=row.id,
            taskRunId=row.task_run_id,
            deerflowThreadId=row.deerflow_thread_id,
            deerflowRunId=row.deerflow_run_id,
            lastCheckpointId=row.last_checkpoint_id,
            userIntent=row.user_intent,
            normalizedGoal=_loads(row.normalized_goal_json, {}),
            envCode=row.env_code,
            envSource=row.env_source,
            status=row.status,
            phase=row.phase,
            pendingInterrupts=_loads(row.pending_interrupts_json, None),
            goalStack=_loads(row.goal_stack_json, []),
            plan=_loads(row.plan_json, None),
            visibleVariables=_loads(row.visible_variables_json, []),
            reflection=_loads(row.reflection_json, None),
            failureType=row.failure_type,
            failureMessage=row.failure_message,
            finalSummary=row.final_summary,
            createdBy=row.created_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
            finishedAt=row.finished_at,
        )

    @staticmethod
    def _to_step_response(row: DataFactoryDatagenTaskStepRow) -> DatagenTaskStepResponse:
        return DatagenTaskStepResponse(
            id=row.id,
            taskRunId=row.task_run_id,
            taskStepId=row.task_step_id,
            stepNo=row.step_no,
            phase=row.phase,
            stepType=row.step_type,
            goal=row.goal,
            status=row.status,
            selectedResource=_loads(row.selected_resource_json, None),
            inputBinding=_loads(row.input_binding_json, None),
            output=_loads(row.output_json, None),
            sceneRunId=row.scene_run_id,
            errorType=row.error_type,
            errorMessage=row.error_message,
            startedAt=row.started_at,
            finishedAt=row.finished_at,
        )

    @staticmethod
    def _to_event_response(row: DataFactoryDatagenTaskEventRow) -> DatagenTaskEventResponse:
        return DatagenTaskEventResponse(
            id=row.id,
            taskRunId=row.task_run_id,
            eventId=row.event_id,
            eventNo=row.event_no,
            eventType=row.event_type,
            phase=row.phase,
            message=row.message,
            payload=_loads(row.payload_json, {}),
            createdAt=row.created_at,
        )
