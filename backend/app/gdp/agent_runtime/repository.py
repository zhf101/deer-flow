"""GDP Agent Runtime 数据库账本仓储。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base

from .models import (
    Action,
    ActionAttempt,
    DecisionRecord,
    Evidence,
    Observation,
    PlanStep,
    Requirement,
    RequirementProposal,
    TaskRun,
    TaskRunStatus,
    Variable,
    Verdict,
)
from .store import EntityNotFoundError, Store


class AgentRuntimeTaskRunRow(Base):
    """GDP Agent Runtime 任务运行账本主表。"""

    __tablename__ = "df_agent_runtime_task_run"

    task_run_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="任务运行 ID。")
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="所属对话线程 ID。")
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户 ID。")
    env_code: Mapped[str | None] = mapped_column(String(64), comment="目标环境编码。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="任务状态。")
    task_run_json: Mapped[str] = mapped_column(Text, nullable=False, comment="TaskRun 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间。")


class AgentRuntimeStepRow(Base):
    """GDP Agent Runtime 步骤账本表。"""

    __tablename__ = "df_agent_runtime_step"

    step_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="步骤 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤序号。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="步骤状态。")
    step_json: Mapped[str] = mapped_column(Text, nullable=False, comment="PlanStep 完整 JSON 快照。")


class AgentRuntimeActionRow(Base):
    """GDP Agent Runtime 动作账本表。"""

    __tablename__ = "df_agent_runtime_action"

    action_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="动作 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属步骤 ID。")
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="动作类型。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="动作状态。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="执行的场景编码。")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True, comment="幂等键。")
    action_json: Mapped[str] = mapped_column(Text, nullable=False, comment="Action 完整 JSON 快照。")


class AgentRuntimeAttemptRow(Base):
    """GDP Agent Runtime 动作执行尝试表。"""

    __tablename__ = "df_agent_runtime_attempt"

    attempt_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="执行尝试 ID。")
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属动作 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="尝试序号。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="尝试状态。")
    scene_run_id: Mapped[str | None] = mapped_column(String(64), comment="关联场景执行记录 ID。")
    attempt_json: Mapped[str] = mapped_column(Text, nullable=False, comment="ActionAttempt 完整 JSON 快照。")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开始时间。")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间。")


class AgentRuntimeObservationRow(Base):
    """GDP Agent Runtime 原始观察表。"""

    __tablename__ = "df_agent_runtime_observation"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="观察 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属动作 ID。")
    attempt_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属尝试 ID。")
    observation_json: Mapped[str] = mapped_column(Text, nullable=False, comment="Observation 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeEvidenceRow(Base):
    """GDP Agent Runtime 可判定证据表。"""

    __tablename__ = "df_agent_runtime_evidence"

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="证据 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属步骤 ID。")
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属动作 ID。")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, comment="Evidence 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeVerdictRow(Base):
    """GDP Agent Runtime 结果判定表。"""

    __tablename__ = "df_agent_runtime_verdict"

    verdict_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="判定 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属步骤 ID。")
    verdict_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="判定类型。")
    verdict_json: Mapped[str] = mapped_column(Text, nullable=False, comment="Verdict 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeVariableRow(Base):
    """GDP Agent Runtime 变量表。"""

    __tablename__ = "df_agent_runtime_variable"

    variable_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="变量 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="变量名。")
    variable_json: Mapped[str] = mapped_column(Text, nullable=False, comment="Variable 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeRequirementRow(Base):
    """GDP Agent Runtime 资源缺口表。"""

    __tablename__ = "df_agent_runtime_requirement"

    requirement_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="缺口 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属步骤 ID。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="缺口状态。")
    requirement_json: Mapped[str] = mapped_column(Text, nullable=False, comment="Requirement 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")


class AgentRuntimeProposalRow(Base):
    """GDP Agent Runtime 候选集表。"""

    __tablename__ = "df_agent_runtime_proposal"

    proposal_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="候选集 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属步骤 ID。")
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属缺口 ID。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="候选集状态。")
    proposal_json: Mapped[str] = mapped_column(Text, nullable=False, comment="RequirementProposal 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeApprovalRow(Base):
    """GDP Agent Runtime 审批事实表。"""

    __tablename__ = "df_agent_runtime_approval"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="审批事实 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="审批的场景编码。")
    approval_json: Mapped[str] = mapped_column(Text, nullable=False, comment="审批事实 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeDecisionRow(Base):
    """GDP Agent Runtime 决策审计表。"""

    __tablename__ = "df_agent_runtime_decision"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="决策记录 ID。")
    task_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属任务运行 ID。")
    step_id: Mapped[str | None] = mapped_column(String(64), comment="关联步骤 ID。")
    requirement_id: Mapped[str | None] = mapped_column(String(64), comment="关联缺口 ID。")
    proposal_id: Mapped[str | None] = mapped_column(String(64), comment="关联候选集 ID。")
    action_id: Mapped[str | None] = mapped_column(String(64), comment="关联动作 ID。")
    scene_run_id: Mapped[str | None] = mapped_column(String(64), comment="关联场景运行 ID。")
    decision_kind: Mapped[str] = mapped_column(String(64), nullable=False, comment="决策类型。")
    decision_source: Mapped[str] = mapped_column(String(32), nullable=False, comment="决策来源。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="决策记录状态。")
    target_type: Mapped[str | None] = mapped_column(String(64), comment="决策目标类型。")
    target_id: Mapped[str | None] = mapped_column(String(128), comment="决策目标 ID。")
    decision_json: Mapped[str] = mapped_column(Text, nullable=False, comment="DecisionRecord 完整 JSON 快照。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimePayloadRow(Base):
    """GDP Agent Runtime 完整载荷表。"""

    __tablename__ = "df_agent_runtime_payload"

    payload_ref: Mapped[str] = mapped_column(String(512), primary_key=True, comment="载荷引用。")
    task_run_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True, comment="所属任务运行 ID。")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, comment="完整载荷 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")


class AgentRuntimeRepository:
    """GDP Agent Runtime 数据库账本仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def persist_store(self, store: Store, task_run_id: str) -> None:
        """将内存 Store 中某个 TaskRun 的完整账本落库。"""
        snapshot = store.export_task_run(task_run_id)
        task_run = snapshot["task_run"]
        async with self._sf() as session:
            await self._upsert_task_run(session, task_run)
            for item in snapshot["steps"]:
                await self._upsert(session, AgentRuntimeStepRow, item["step_id"], _step_values(item))
            for item in snapshot["actions"]:
                await self._upsert(session, AgentRuntimeActionRow, item["action_id"], _action_values(item))
            actions_by_id = {item["action_id"]: item for item in snapshot["actions"]}
            for item in snapshot["attempts"]:
                action = actions_by_id.get(item["action_id"], {})
                await self._upsert(session, AgentRuntimeAttemptRow, item["attempt_id"], _attempt_values(item, action))
            for item in snapshot["observations"]:
                await self._upsert(session, AgentRuntimeObservationRow, item["observation_id"], _observation_values(item))
            for item in snapshot["evidences"]:
                await self._upsert(session, AgentRuntimeEvidenceRow, item["evidence_id"], _evidence_values(item))
            for item in snapshot["verdicts"]:
                await self._upsert(session, AgentRuntimeVerdictRow, item["verdict_id"], _verdict_values(item))
            for item in snapshot["variables"]:
                await self._upsert(session, AgentRuntimeVariableRow, item["variable_id"], _variable_values(item))
            for item in snapshot["requirements"]:
                await self._upsert(session, AgentRuntimeRequirementRow, item["requirement_id"], _requirement_values(item))
            for item in snapshot["proposals"]:
                await self._upsert(session, AgentRuntimeProposalRow, item["proposal_id"], _proposal_values(item))
            for item in snapshot["decisions"]:
                await self._upsert(session, AgentRuntimeDecisionRow, item["decision_id"], _decision_values(item))
            for item in snapshot["approval_records"]:
                await self._upsert(session, AgentRuntimeApprovalRow, _approval_id(item), _approval_values(item))
            for item in snapshot["payloads"]:
                await self._upsert_payload(
                    session,
                    {
                        "payload_ref": item["ref"],
                        "task_run_id": item["task_run_id"],
                        "payload_json": _dumps(item["payload"]),
                        "created_at": _now(),
                    },
                )
            await session.commit()

    async def hydrate_store(self, task_run_id: str) -> Store:
        """从数据库恢复单个 TaskRun 的内存 Store。"""
        async with self._sf() as session:
            task_row = await session.get(AgentRuntimeTaskRunRow, task_run_id)
            if task_row is None:
                raise EntityNotFoundError("TaskRun", task_run_id)

            store = Store()
            store.save_task_run(TaskRun.model_validate(_loads(task_row.task_run_json)))

            for row in await _rows(session, AgentRuntimeStepRow, task_run_id, AgentRuntimeStepRow.step_no):
                store.save_step(PlanStep.model_validate(_loads(row.step_json)))
            for row in await _rows(session, AgentRuntimeActionRow, task_run_id, AgentRuntimeActionRow.action_id):
                store.save_action(Action.model_validate(_loads(row.action_json)))
            for row in await _rows(session, AgentRuntimeAttemptRow, task_run_id, AgentRuntimeAttemptRow.attempt_no):
                store.save_attempt(ActionAttempt.model_validate(_loads(row.attempt_json)))
            for row in await _rows(session, AgentRuntimeObservationRow, task_run_id, AgentRuntimeObservationRow.created_at):
                store.save_observation(Observation.model_validate(_loads(row.observation_json)))
            for row in await _rows(session, AgentRuntimeEvidenceRow, task_run_id, AgentRuntimeEvidenceRow.created_at):
                store.save_evidence(Evidence.model_validate(_loads(row.evidence_json)))
            for row in await _rows(session, AgentRuntimeVerdictRow, task_run_id, AgentRuntimeVerdictRow.created_at):
                store.save_verdict(Verdict.model_validate(_loads(row.verdict_json)))
            for row in await _rows(session, AgentRuntimeVariableRow, task_run_id, AgentRuntimeVariableRow.created_at):
                store.save_variable(Variable.model_validate(_loads(row.variable_json)))
            for row in await _rows(session, AgentRuntimeRequirementRow, task_run_id, AgentRuntimeRequirementRow.created_at):
                store.save_requirement(Requirement.model_validate(_loads(row.requirement_json)))
            for row in await _rows(session, AgentRuntimeProposalRow, task_run_id, AgentRuntimeProposalRow.created_at):
                store.save_proposal(RequirementProposal.model_validate(_loads(row.proposal_json)))
            for row in await _rows(session, AgentRuntimeDecisionRow, task_run_id, AgentRuntimeDecisionRow.created_at):
                store.save_decision(DecisionRecord.model_validate(_loads(row.decision_json)))
            for row in await _rows(session, AgentRuntimeApprovalRow, task_run_id, AgentRuntimeApprovalRow.created_at):
                store.save_approval_record(_loads(row.approval_json))
            for row in await _rows(session, AgentRuntimePayloadRow, task_run_id, AgentRuntimePayloadRow.created_at):
                store.save_payload(task_run_id, row.payload_ref, _loads(row.payload_json))

            return store

    async def list_task_runs(
        self,
        *,
        status: TaskRunStatus | None = None,
        env_code: str | None = None,
        user_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TaskRun]:
        """分页查询历史 TaskRun。"""
        stmt = select(AgentRuntimeTaskRunRow).order_by(AgentRuntimeTaskRunRow.updated_at.desc())
        if status is not None:
            stmt = stmt.where(AgentRuntimeTaskRunRow.status == status.value)
        if env_code:
            stmt = stmt.where(AgentRuntimeTaskRunRow.env_code == env_code)
        if user_id:
            stmt = stmt.where(AgentRuntimeTaskRunRow.user_id == user_id)
        stmt = stmt.limit(limit).offset(offset)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [TaskRun.model_validate(_loads(row.task_run_json)) for row in rows]

    async def get_payload(self, task_run_id: str, ref: str) -> Any:
        """读取某个 TaskRun 的完整 payload。"""
        async with self._sf() as session:
            row = await session.get(AgentRuntimePayloadRow, (ref, task_run_id))
            if row is None:
                raise EntityNotFoundError("Payload", ref)
            return _loads(row.payload_json)

    async def _upsert_task_run(self, session: AsyncSession, item: dict[str, Any]) -> None:
        await self._upsert(
            session,
            AgentRuntimeTaskRunRow,
            item["task_run_id"],
            {
                "task_run_id": item["task_run_id"],
                "thread_id": item["thread_id"],
                "user_id": item["user_id"],
                "env_code": item.get("env_code"),
                "status": item["status"],
                "task_run_json": _dumps(item),
                "created_at": _dt(item["created_at"]),
                "updated_at": _dt(item["updated_at"]),
                "finished_at": _dt(item["finished_at"]) if item.get("finished_at") else None,
            },
        )

    @staticmethod
    async def _upsert(session: AsyncSession, row_cls: type, key: str, values: dict[str, Any]) -> None:
        row = await session.get(row_cls, key)
        if row is None:
            session.add(row_cls(**values))
            return
        for attr, value in values.items():
            setattr(row, attr, value)

    @staticmethod
    async def _upsert_payload(session: AsyncSession, values: dict[str, Any]) -> None:
        row = await session.get(AgentRuntimePayloadRow, (values["payload_ref"], values["task_run_id"]))
        if row is None:
            session.add(AgentRuntimePayloadRow(**values))
            return
        for attr, value in values.items():
            setattr(row, attr, value)


async def _rows(session: AsyncSession, row_cls: type, task_run_id: str, order_by: Any) -> list[Any]:
    stmt = select(row_cls).where(row_cls.task_run_id == task_run_id).order_by(order_by)
    return list((await session.execute(stmt)).scalars().all())


def _step_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": item["step_id"],
        "task_run_id": item["task_run_id"],
        "step_no": item["step_no"],
        "status": item["status"],
        "step_json": _dumps(item),
    }


def _action_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": item["action_id"],
        "task_run_id": item["task_run_id"],
        "step_id": item["step_id"],
        "action_type": item["action_type"],
        "status": item["status"],
        "scene_code": item["scene_code"],
        "idempotency_key": item["idempotency_key"],
        "action_json": _dumps(item),
    }


def _attempt_values(item: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": item["attempt_id"],
        "action_id": item["action_id"],
        "task_run_id": action.get("task_run_id", ""),
        "attempt_no": item["attempt_no"],
        "status": item["status"],
        "scene_run_id": item.get("scene_run_id"),
        "attempt_json": _dumps(item),
        "started_at": _dt(item["started_at"]),
        "finished_at": _dt(item["finished_at"]) if item.get("finished_at") else None,
    }


def _observation_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": item["observation_id"],
        "task_run_id": item["task_run_id"],
        "action_id": item["action_id"],
        "attempt_id": item["attempt_id"],
        "observation_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
    }


def _evidence_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": item["evidence_id"],
        "task_run_id": item["task_run_id"],
        "step_id": item["step_id"],
        "action_id": item["action_id"],
        "evidence_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
    }


def _verdict_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict_id": item["verdict_id"],
        "task_run_id": item["task_run_id"],
        "step_id": item["step_id"],
        "verdict_type": item["verdict_type"],
        "verdict_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
    }


def _variable_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "variable_id": item["variable_id"],
        "task_run_id": item["task_run_id"],
        "name": item["name"],
        "variable_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
    }


def _requirement_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item["requirement_id"],
        "task_run_id": item["task_run_id"],
        "step_id": item["step_id"],
        "status": item["status"],
        "requirement_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
        "updated_at": _dt(item["updated_at"]),
    }


def _proposal_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": item["proposal_id"],
        "task_run_id": item["task_run_id"],
        "step_id": item["step_id"],
        "requirement_id": item["requirement_id"],
        "status": item["status"],
        "proposal_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
    }


def _approval_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_id": _approval_id(item),
        "task_run_id": str(item.get("task_run_id") or ""),
        "scene_code": str(item.get("scene_code") or ""),
        "approval_json": _dumps(item),
        "created_at": _dt(item["approved_at"]) if item.get("approved_at") else _now(),
    }


def _decision_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": item["decision_id"],
        "task_run_id": item["task_run_id"],
        "step_id": item.get("step_id"),
        "requirement_id": item.get("requirement_id"),
        "proposal_id": item.get("proposal_id"),
        "action_id": item.get("action_id"),
        "scene_run_id": item.get("scene_run_id"),
        "decision_kind": item["decision_kind"],
        "decision_source": item["decision_source"],
        "status": item["status"],
        "target_type": item.get("target_type"),
        "target_id": item.get("target_id"),
        "decision_json": _dumps(item),
        "created_at": _dt(item["created_at"]),
    }


def _approval_id(item: dict[str, Any]) -> str:
    raw = _dumps(item)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _loads(value: str) -> Any:
    return json.loads(value)


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _now() -> datetime:
    return datetime.now(UTC)
