"""场景编排持久化仓储。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.base.repository import DataFactoryConfigAuditRow
from app.gdp.datagen.config.common.models import SceneStatus, VersionStatus
from app.gdp.datagen.config.scene.models import (
    AssertStepDefinition,
    HttpStepDefinition,
    SceneDefinition,
    SceneExecutionResult,
    SceneRunSummary,
    SceneSummary,
    SceneVersion,
    SqlStepDefinition,
    StepDefinition,
    StepExecutionResult,
    StepTemplateRef,
    TransformStepDefinition,
    ValidationResult,
    parse_step_definition_payload,
)
from deerflow.persistence.base import Base


class DataFactorySceneRow(Base):
    """场景主表。"""

    __tablename__ = "df_scene"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="场景唯一编码。")
    scene_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="场景名称。")
    scene_type: Mapped[str | None] = mapped_column(String(128), comment="场景分类。")
    scene_remark: Mapped[str | None] = mapped_column(Text, comment="场景备注。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="场景状态。")
    current_version_no: Mapped[int | None] = mapped_column(Integer, comment="当前编辑版本号。")
    published_version_no: Mapped[int | None] = mapped_column(Integer, comment="当前发布版本号。")
    created_by: Mapped[str | None] = mapped_column(String(128), comment="创建人。")
    updated_by: Mapped[str | None] = mapped_column(String(128), comment="更新人。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")


class DataFactorySceneVersionRow(Base):
    """场景版本表。"""

    __tablename__ = "df_scene_version"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景主表 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景编码。")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号。")
    version_status: Mapped[str] = mapped_column(String(32), nullable=False, comment="版本状态。")
    input_schema_json: Mapped[str] = mapped_column(Text, nullable=False, comment="场景入参定义 JSON。")
    result_schema_json: Mapped[str | None] = mapped_column(Text, comment="场景出参定义 JSON。")
    result_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="场景结果映射 JSON。")
    batch_config_json: Mapped[str] = mapped_column(Text, nullable=False, comment="批量执行配置 JSON。")
    error_policy_json: Mapped[str] = mapped_column(Text, nullable=False, comment="错误策略。")
    validation_result_json: Mapped[str | None] = mapped_column(Text, comment="最近一次校验结果 JSON。")
    created_by: Mapped[str | None] = mapped_column(String(128), comment="创建人。")
    updated_by: Mapped[str | None] = mapped_column(String(128), comment="更新人。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")
    published_by: Mapped[str | None] = mapped_column(String(128), comment="发布人。")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="发布时间。")

    __table_args__ = (UniqueConstraint("scene_code", "version_no", name="uq_df_scene_version"),)


class DataFactorySceneStepRow(Base):
    """场景步骤公共信息表。"""

    __tablename__ = "df_scene_step"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景主表 ID。")
    scene_version_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景版本 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景编码。")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号。")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤执行顺序，从 1 开始。")
    step_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="步骤业务 ID。")
    step_name: Mapped[str | None] = mapped_column(String(256), comment="步骤名称。")
    step_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="步骤类型。")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否启用。")
    depends_on_json: Mapped[str] = mapped_column(Text, nullable=False, comment="步骤依赖 JSON。")
    position_json: Mapped[str | None] = mapped_column(Text, comment="画布坐标 JSON。")
    description: Mapped[str | None] = mapped_column(Text, comment="步骤说明。")
    output_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="输出映射 JSON。")
    output_meta_json: Mapped[str | None] = mapped_column(Text, comment="输出变量元数据 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")

    __table_args__ = (UniqueConstraint("scene_version_id", "step_id", name="uq_df_scene_step"),)


class DataFactorySceneStepHttpConfigRow(Base):
    """场景 HTTP 步骤快照表。"""

    __tablename__ = "df_scene_step_http_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(128), nullable=False)

    source_code: Mapped[str | None] = mapped_column(String(128), comment="来源 HTTP 模板编码，软引用。")
    source_name_at_snapshot: Mapped[str | None] = mapped_column(String(256), comment="导入时模板名称。")
    source_updated_at_snapshot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="导入时模板更新时间。")
    source_hash_snapshot: Mapped[str | None] = mapped_column(String(128), comment="导入时模板 hash。")
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="当前配置 hash。")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照时间。")
    drifted: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否偏离导入时模板。")

    source_name: Mapped[str | None] = mapped_column(String(256), comment="快照名称。")
    sys_code: Mapped[str | None] = mapped_column(String(64), comment="系统编码。")
    path: Mapped[str | None] = mapped_column(String(1024), comment="HTTP 相对路径。")
    method: Mapped[str | None] = mapped_column(String(16), comment="HTTP 方法。")
    timeout_config_json: Mapped[str] = mapped_column(Text, nullable=False, comment="HTTP 分阶段超时配置 JSON。")
    request_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="请求配置 JSON。")
    http_param_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="HTTP 参数映射 JSON。")
    body_schema_json: Mapped[str | None] = mapped_column(Text, comment="请求 body schema JSON。")
    response_schema_json: Mapped[str | None] = mapped_column(Text, comment="响应 body schema JSON。")
    response_headers_schema_json: Mapped[str | None] = mapped_column(Text, comment="响应 header schema JSON。")
    response_cookies_schema_json: Mapped[str | None] = mapped_column(Text, comment="响应 cookie schema JSON。")
    response_handling_json: Mapped[str | None] = mapped_column(Text, comment="响应处理 JSON。")
    error_mapping_json: Mapped[str | None] = mapped_column(Text, comment="传输异常错误映射 JSON。")
    business_error_mapping_json: Mapped[str | None] = mapped_column(Text, comment="业务异常错误映射 JSON。")
    retry_policy_json: Mapped[str | None] = mapped_column(Text, comment="重试策略 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataFactorySceneStepSqlConfigRow(Base):
    """场景 SQL 步骤快照表。"""

    __tablename__ = "df_scene_step_sql_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_id: Mapped[str] = mapped_column(String(128), nullable=False)

    source_code: Mapped[str | None] = mapped_column(String(128), comment="来源 SQL 模板编码，软引用。")
    source_name_at_snapshot: Mapped[str | None] = mapped_column(String(256), comment="导入时模板名称。")
    source_updated_at_snapshot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="导入时模板更新时间。")
    source_hash_snapshot: Mapped[str | None] = mapped_column(String(128), comment="导入时模板 hash。")
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="当前配置 hash。")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照时间。")
    drifted: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否偏离导入时模板。")

    source_name: Mapped[str | None] = mapped_column(String(256), comment="快照名称。")
    sys_code: Mapped[str | None] = mapped_column(String(64), comment="系统编码。")
    datasource_code: Mapped[str | None] = mapped_column(String(128), comment="数据源编码。")
    operation: Mapped[str | None] = mapped_column(String(32), comment="SQL 操作类型。")
    sql_text: Mapped[str | None] = mapped_column(Text, comment="用户原始 SQL。")
    normalized_sql: Mapped[str | None] = mapped_column(Text, comment="标准 SQL。")
    tables_json: Mapped[str] = mapped_column(Text, nullable=False, comment="表元数据 JSON。")
    result_fields_json: Mapped[str] = mapped_column(Text, nullable=False, comment="结果字段 JSON。")
    condition_fields_json: Mapped[str] = mapped_column(Text, nullable=False, comment="条件字段 JSON。")
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False, comment="参数定义 JSON。")
    safety_json: Mapped[str] = mapped_column(Text, nullable=False, comment="安全策略 JSON。")
    param_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="参数映射 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataFactorySceneStepAssertConfigRow(Base):
    """场景断言步骤配置表。"""

    __tablename__ = "df_scene_step_assert_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景主表 ID。")
    scene_version_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景版本 ID。")
    scene_step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="步骤公共信息 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景编码。")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号。")
    step_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="步骤业务 ID。")
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="当前配置 hash。")
    assertions_json: Mapped[str] = mapped_column(Text, nullable=False, comment="断言配置 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")


class DataFactorySceneStepTransformConfigRow(Base):
    """场景变量转换步骤配置表。"""

    __tablename__ = "df_scene_step_transform_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="主键 ID。")
    scene_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景主表 ID。")
    scene_version_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="场景版本 ID。")
    scene_step_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="步骤公共信息 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景编码。")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号。")
    step_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="步骤业务 ID。")
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False, comment="当前配置 hash。")
    assignments_json: Mapped[str] = mapped_column(Text, nullable=False, comment="变量赋值配置 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间。")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间。")


class DataFactorySceneRunRow(Base):
    """场景执行记录主表。

    一行表示一次场景测试执行，保存执行环境、版本、入参、最终输出和错误汇总。
    节点级详情保存在 df_scene_run_step。
    """

    __tablename__ = "df_scene_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="执行记录 ID。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景编码。")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="执行的场景版本号。")
    env_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="执行环境编码。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="执行状态。")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="场景执行开始时间。")
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="场景执行结束时间。")
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, comment="场景执行耗时，单位毫秒。")
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False, comment="本次执行入参 JSON。")
    final_output_json: Mapped[str] = mapped_column(Text, nullable=False, comment="最终输出 JSON。")
    errors_json: Mapped[str] = mapped_column(Text, nullable=False, comment="错误汇总 JSON。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="记录创建时间。")


class DataFactorySceneRunStepRow(Base):
    """场景执行节点明细表。

    一行表示一次执行中的一个节点结果，保存排序、时间、状态、输出、原始响应和错误详情。
    """

    __tablename__ = "df_scene_run_step"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="节点执行记录 ID。")
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="执行记录 ID，关联 df_scene_run.id。")
    scene_code: Mapped[str] = mapped_column(String(128), nullable=False, comment="场景编码。")
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="执行的场景版本号。")
    env_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="执行环境编码。")
    step_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="节点业务 ID。")
    step_name: Mapped[str | None] = mapped_column(String(256), comment="节点名称。")
    step_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="节点类型。")
    step_order: Mapped[int | None] = mapped_column(Integer, comment="节点在编排步骤列表中的顺序。")
    timeline_order: Mapped[int | None] = mapped_column(Integer, comment="节点在本次执行时间线中的顺序。")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="节点执行状态。")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="节点执行开始时间。")
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="节点执行结束时间。")
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, comment="节点执行耗时，单位毫秒。")
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False, comment="节点输出变量 JSON。")
    raw_response_json: Mapped[str | None] = mapped_column(Text, comment="节点原始执行结果 JSON。")
    error: Mapped[str | None] = mapped_column(Text, comment="节点错误信息。")
    status_code: Mapped[int | None] = mapped_column(Integer, comment="HTTP 节点响应状态码。")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="记录创建时间。")

    __table_args__ = (UniqueConstraint("run_id", "step_id", name="uq_df_scene_run_step"),)


class SceneNotFoundError(LookupError):
    """场景不存在。"""


class SceneConflictError(RuntimeError):
    """场景违反唯一性约束。"""


class SceneVersionConflictError(RuntimeError):
    """场景版本状态不允许当前操作。"""


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _stable_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


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


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_stable_dumps(_model_dump(value)).encode("utf-8")).hexdigest()


class SceneRepository:
    """场景配置持久化仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_scenes(
        self,
        *,
        keyword: str = "",
        status: SceneStatus | str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SceneSummary]:
        stmt = select(DataFactorySceneRow).order_by(DataFactorySceneRow.updated_at.desc(), DataFactorySceneRow.scene_code.asc())
        normalized_keyword = keyword.strip()
        if normalized_keyword:
            pattern = f"%{normalized_keyword}%"
            stmt = stmt.where(
                or_(
                    DataFactorySceneRow.scene_code.like(pattern),
                    DataFactorySceneRow.scene_name.like(pattern),
                )
            )
        if status:
            status_value = status.value if isinstance(status, SceneStatus) else str(status)
            stmt = stmt.where(DataFactorySceneRow.status == status_value)
        stmt = stmt.limit(limit).offset(offset)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_summary(row) for row in rows]

    async def create_scene(self, scene: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        async with self._sf() as session:
            existing = await self._get_scene_row(session, scene.sceneCode)
            if existing is not None:
                raise SceneConflictError(f"scene already exists: {scene.sceneCode}")
            now = _now()
            scene_row = DataFactorySceneRow(
                id=_new_id(),
                scene_code=scene.sceneCode,
                scene_name=scene.sceneName,
                scene_type=scene.sceneType,
                scene_remark=scene.sceneRemark,
                status=SceneStatus.DRAFT.value,
                current_version_no=1,
                published_version_no=None,
                created_by=operator,
                updated_by=operator,
                created_at=now,
                updated_at=now,
            )
            version_row = self._new_version_row(scene_row, scene, 1, operator, now)
            session.add(scene_row)
            session.add(version_row)
            self._add_steps(session, scene_row, version_row, scene.steps, now)
            self._add_audit(session, "SCENE", scene_row.id, "CREATE_SCENE", operator, scene.model_dump(mode="json"))
            await self._commit(session)
            return await self._to_scene_version(session, scene_row, version_row)

    async def get_scene(self, scene_code: str, *, version_no: int | None = None) -> SceneVersion:
        async with self._sf() as session:
            scene_row = await self._require_scene_row(session, scene_code)
            version_row = await self._require_version_row(session, scene_row, version_no)
            return await self._to_scene_version(session, scene_row, version_row)

    async def get_published_scene(self, scene_code: str) -> SceneVersion:
        async with self._sf() as session:
            scene_row = await self._require_scene_row(session, scene_code)
            if scene_row.published_version_no is None:
                raise SceneNotFoundError(f"published scene version not found: {scene_code}")
            version_row = await self._require_version_row(session, scene_row, scene_row.published_version_no)
            return await self._to_scene_version(session, scene_row, version_row)

    async def save_scene_run(self, result: SceneExecutionResult) -> SceneExecutionResult:
        """持久化一次场景执行结果和所有节点明细。"""

        run_id = result.runId or _new_id()
        saved = result.model_copy(update={"runId": run_id})
        now = _now()
        async with self._sf() as session:
            session.add(
                DataFactorySceneRunRow(
                    id=run_id,
                    scene_code=saved.sceneCode,
                    version_no=saved.versionNo,
                    env_code=saved.envCode,
                    status=saved.status,
                    started_at=saved.startedAt,
                    finished_at=saved.finishedAt,
                    duration_ms=saved.durationMs,
                    inputs_json=_dumps(_model_dump(saved.inputs)),
                    final_output_json=_dumps(_model_dump(saved.finalOutput)),
                    errors_json=_dumps(_model_dump(saved.errors)),
                    created_at=now,
                )
            )
            for index, step in enumerate(saved.stepResults, 1):
                session.add(
                    DataFactorySceneRunStepRow(
                        id=_new_id(),
                        run_id=run_id,
                        scene_code=saved.sceneCode,
                        version_no=saved.versionNo,
                        env_code=saved.envCode,
                        step_id=step.stepId,
                        step_name=step.stepName,
                        step_type=step.type.value,
                        step_order=step.stepOrder,
                        timeline_order=step.timelineOrder or index,
                        status=step.status,
                        started_at=step.startedAt,
                        finished_at=step.finishedAt,
                        duration_ms=step.durationMs,
                        outputs_json=_dumps(_model_dump(step.outputs)),
                        raw_response_json=_dumps(_model_dump(step.rawResponse)) if step.rawResponse is not None else None,
                        error=step.error,
                        status_code=step.statusCode,
                        created_at=now,
                    )
                )
            await self._commit(session)
        return saved

    async def get_scene_run(self, run_id: str) -> SceneExecutionResult:
        """读取一次已持久化的场景执行详情。"""

        async with self._sf() as session:
            run_row = await session.get(DataFactorySceneRunRow, run_id)
            if run_row is None:
                raise SceneNotFoundError(f"scene run not found: {run_id}")
            step_stmt = (
                select(DataFactorySceneRunStepRow)
                .where(DataFactorySceneRunStepRow.run_id == run_id)
                .order_by(DataFactorySceneRunStepRow.timeline_order.asc(), DataFactorySceneRunStepRow.step_order.asc())
            )
            step_rows = (await session.execute(step_stmt)).scalars().all()
            return SceneExecutionResult(
                runId=run_row.id,
                sceneCode=run_row.scene_code,
                versionNo=run_row.version_no,
                envCode=run_row.env_code,
                inputs=_loads(run_row.inputs_json, {}),
                status=run_row.status,
                startedAt=run_row.started_at,
                finishedAt=run_row.finished_at,
                durationMs=run_row.duration_ms,
                stepResults=[self._to_step_execution_result(row) for row in step_rows],
                finalOutput=_loads(run_row.final_output_json, {}),
                errors=_loads(run_row.errors_json, []),
            )

    async def list_scene_runs(
        self,
        *,
        scene_code: str = "",
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SceneRunSummary]:
        """查询场景执行历史列表，聚合步骤统计信息。"""

        async with self._sf() as session:
            stmt = select(DataFactorySceneRunRow).order_by(DataFactorySceneRunRow.started_at.desc())
            if scene_code:
                stmt = stmt.where(DataFactorySceneRunRow.scene_code == scene_code)
            if status:
                stmt = stmt.where(DataFactorySceneRunRow.status == status)
            stmt = stmt.limit(limit).offset(offset)
            run_rows = (await session.execute(stmt)).scalars().all()

            if not run_rows:
                return []

            # 批量聚合步骤统计
            run_ids = [r.id for r in run_rows]
            step_stats_stmt = (
                select(
                    DataFactorySceneRunStepRow.run_id,
                    func.count().label("total"),
                    func.count().filter(DataFactorySceneRunStepRow.status == "SUCCESS").label("success"),
                    func.count().filter(DataFactorySceneRunStepRow.status == "FAILED").label("failed"),
                )
                .where(DataFactorySceneRunStepRow.run_id.in_(run_ids))
                .group_by(DataFactorySceneRunStepRow.run_id)
            )
            step_stats_rows = (await session.execute(step_stats_stmt)).all()
            stats_map = {
                row.run_id: {"total": row.total, "success": row.success, "failed": row.failed}
                for row in step_stats_rows
            }

            return [
                SceneRunSummary(
                    runId=row.id,
                    sceneCode=row.scene_code,
                    versionNo=row.version_no,
                    envCode=row.env_code,
                    status=row.status,
                    startedAt=row.started_at,
                    finishedAt=row.finished_at,
                    durationMs=row.duration_ms,
                    inputs=_loads(row.inputs_json, {}),
                    finalOutput=_loads(row.final_output_json, {}),
                    errors=_loads(row.errors_json, []),
                    stepCount=stats_map.get(row.id, {}).get("total", 0),
                    successCount=stats_map.get(row.id, {}).get("success", 0),
                    failedCount=stats_map.get(row.id, {}).get("failed", 0),
                )
                for row in run_rows
            ]

    async def update_scene(self, scene_code: str, scene: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        if scene_code != scene.sceneCode:
            raise SceneConflictError("request sceneCode must match definition sceneCode")

        async with self._sf() as session:
            scene_row = await self._require_scene_row(session, scene_code)
            now = _now()
            current_version = await self._require_version_row(session, scene_row, None)

            scene_row.scene_name = scene.sceneName
            scene_row.scene_type = scene.sceneType
            scene_row.scene_remark = scene.sceneRemark
            scene_row.status = SceneStatus.DRAFT.value
            scene_row.updated_by = operator
            scene_row.updated_at = now

            if current_version.version_status == VersionStatus.DRAFT.value:
                version_row = current_version
                self._update_version_row(version_row, scene, operator, now)
                await self._delete_version_steps(session, version_row.id)
            else:
                version_no = (scene_row.current_version_no or current_version.version_no) + 1
                version_row = self._new_version_row(scene_row, scene, version_no, operator, now)
                scene_row.current_version_no = version_no
                session.add(version_row)

            self._add_steps(session, scene_row, version_row, scene.steps, now)
            self._add_audit(session, "SCENE", scene_row.id, "UPDATE_SCENE", operator, scene.model_dump(mode="json"))
            await self._commit(session)
            return await self._to_scene_version(session, scene_row, version_row)

    async def publish_scene(
        self,
        scene_code: str,
        validation_result: ValidationResult,
        *,
        operator: str | None = None,
    ) -> SceneVersion:
        async with self._sf() as session:
            scene_row = await self._require_scene_row(session, scene_code)
            version_row = await self._require_version_row(session, scene_row, None)
            if version_row.version_status != VersionStatus.DRAFT.value:
                raise SceneVersionConflictError(f"current scene version is not draft: {scene_code}")

            now = _now()
            version_row.version_status = VersionStatus.PUBLISHED.value
            version_row.validation_result_json = _dumps(validation_result.model_dump(mode="json"))
            version_row.updated_by = operator
            version_row.updated_at = now
            version_row.published_by = operator
            version_row.published_at = now
            scene_row.status = SceneStatus.PUBLISHED.value
            scene_row.published_version_no = version_row.version_no
            scene_row.current_version_no = version_row.version_no
            scene_row.updated_by = operator
            scene_row.updated_at = now
            self._add_audit(session, "SCENE", scene_row.id, "PUBLISH_SCENE", operator, {"sceneCode": scene_code, "versionNo": version_row.version_no})
            await self._commit(session)
            return await self._to_scene_version(session, scene_row, version_row)

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise SceneConflictError("unique constraint violation") from exc

    async def _get_scene_row(self, session: AsyncSession, scene_code: str) -> DataFactorySceneRow | None:
        stmt = select(DataFactorySceneRow).where(DataFactorySceneRow.scene_code == scene_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_scene_row(self, session: AsyncSession, scene_code: str) -> DataFactorySceneRow:
        row = await self._get_scene_row(session, scene_code)
        if row is None:
            raise SceneNotFoundError(f"scene not found: {scene_code}")
        return row

    async def _require_version_row(
        self,
        session: AsyncSession,
        scene_row: DataFactorySceneRow,
        version_no: int | None,
    ) -> DataFactorySceneVersionRow:
        target_version_no = version_no or scene_row.current_version_no or scene_row.published_version_no
        if target_version_no is None:
            raise SceneNotFoundError(f"scene version not found: {scene_row.scene_code}")
        stmt = select(DataFactorySceneVersionRow).where(
            DataFactorySceneVersionRow.scene_code == scene_row.scene_code,
            DataFactorySceneVersionRow.version_no == target_version_no,
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise SceneNotFoundError(f"scene version not found: {scene_row.scene_code}/{target_version_no}")
        return row

    def _new_version_row(
        self,
        scene_row: DataFactorySceneRow,
        scene: SceneDefinition,
        version_no: int,
        operator: str | None,
        now: datetime,
    ) -> DataFactorySceneVersionRow:
        row = DataFactorySceneVersionRow(
            id=_new_id(),
            scene_id=scene_row.id,
            scene_code=scene.sceneCode,
            version_no=version_no,
            version_status=VersionStatus.DRAFT.value,
            input_schema_json=_dumps(_model_dump(scene.inputSchema)),
            result_schema_json=_dumps(_model_dump(scene.resultSchema)) if scene.resultSchema else None,
            result_mapping_json=_dumps(scene.resultMapping),
            batch_config_json=_dumps(_model_dump(scene.batchConfig)),
            error_policy_json=scene.errorPolicy,
            validation_result_json=None,
            created_by=operator,
            updated_by=operator,
            created_at=now,
            updated_at=now,
            published_by=None,
            published_at=None,
        )
        return row

    @staticmethod
    def _update_version_row(
        row: DataFactorySceneVersionRow,
        scene: SceneDefinition,
        operator: str | None,
        now: datetime,
    ) -> None:
        row.input_schema_json = _dumps(_model_dump(scene.inputSchema))
        row.result_schema_json = _dumps(_model_dump(scene.resultSchema)) if scene.resultSchema else None
        row.result_mapping_json = _dumps(scene.resultMapping)
        row.batch_config_json = _dumps(_model_dump(scene.batchConfig))
        row.error_policy_json = scene.errorPolicy
        row.validation_result_json = None
        row.updated_by = operator
        row.updated_at = now

    async def _delete_version_steps(self, session: AsyncSession, scene_version_id: str) -> None:
        await session.execute(delete(DataFactorySceneStepHttpConfigRow).where(DataFactorySceneStepHttpConfigRow.scene_version_id == scene_version_id))
        await session.execute(delete(DataFactorySceneStepSqlConfigRow).where(DataFactorySceneStepSqlConfigRow.scene_version_id == scene_version_id))
        await session.execute(delete(DataFactorySceneStepAssertConfigRow).where(DataFactorySceneStepAssertConfigRow.scene_version_id == scene_version_id))
        await session.execute(delete(DataFactorySceneStepTransformConfigRow).where(DataFactorySceneStepTransformConfigRow.scene_version_id == scene_version_id))
        await session.execute(delete(DataFactorySceneStepRow).where(DataFactorySceneStepRow.scene_version_id == scene_version_id))

    def _add_steps(
        self,
        session: AsyncSession,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        steps: list[StepDefinition],
        now: datetime,
    ) -> None:
        for index, step in enumerate(_steps_by_execution_order(steps), 1):
            step_row = DataFactorySceneStepRow(
                id=_new_id(),
                scene_id=scene_row.id,
                scene_version_id=version_row.id,
                scene_code=scene_row.scene_code,
                version_no=version_row.version_no,
                sort_order=step.executionOrder or index,
                step_id=step.stepId,
                step_name=step.stepName,
                step_type=step.type.value,
                enabled=step.enabled,
                depends_on_json=_dumps(step.dependsOn),
                position_json=_dumps(_model_dump(step.position)) if step.position else None,
                description=step.description,
                output_mapping_json=_dumps(step.outputMapping),
                output_meta_json=_dumps(step.outputMeta) if step.outputMeta else None,
                created_at=now,
                updated_at=now,
            )
            session.add(step_row)
            if isinstance(step, HttpStepDefinition):
                session.add(self._http_config_row(scene_row, version_row, step_row, step, now))
            elif isinstance(step, SqlStepDefinition):
                session.add(self._sql_config_row(scene_row, version_row, step_row, step, now))
            elif isinstance(step, AssertStepDefinition):
                session.add(self._assert_config_row(scene_row, version_row, step_row, step, now))
            elif isinstance(step, TransformStepDefinition):
                session.add(self._transform_config_row(scene_row, version_row, step_row, step, now))

    def _http_config_row(
        self,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        step_row: DataFactorySceneStepRow,
        step: HttpStepDefinition,
        now: datetime,
    ) -> DataFactorySceneStepHttpConfigRow:
        payload = _http_hash_payload(step)
        config_hash = _hash_payload(payload)
        return DataFactorySceneStepHttpConfigRow(
            id=_new_id(),
            scene_id=scene_row.id,
            scene_version_id=version_row.id,
            scene_step_id=step_row.id,
            scene_code=scene_row.scene_code,
            version_no=version_row.version_no,
            step_id=step.stepId,
            source_code=step.templateRef.sourceCode if step.templateRef else None,
            source_name_at_snapshot=step.templateRef.sourceNameAtSnapshot if step.templateRef else None,
            source_updated_at_snapshot=step.templateRef.sourceUpdatedAtSnapshot if step.templateRef else None,
            source_hash_snapshot=step.templateRef.sourceHashSnapshot if step.templateRef else None,
            config_hash=config_hash,
            snapshot_at=now,
            drifted=step.templateRef.drifted if step.templateRef else False,
            source_name=step.sourceName or step.stepName,
            sys_code=step.sysCode,
            path=step.path,
            method=step.method.value,
            timeout_config_json=_dumps(_model_dump(step.timeoutConfig)),
            request_mapping_json=_dumps(step.requestMapping),
            http_param_mapping_json=_dumps(step.httpParamMapping),
            body_schema_json=_dumps(_model_dump(step.bodySchema)) if step.bodySchema else None,
            response_schema_json=_dumps(_model_dump(step.responseSchema)) if step.responseSchema else None,
            response_headers_schema_json=_dumps(_model_dump(step.responseHeadersSchema)) if step.responseHeadersSchema else None,
            response_cookies_schema_json=_dumps(_model_dump(step.responseCookiesSchema)) if step.responseCookiesSchema else None,
            response_handling_json=_dumps(_model_dump(step.responseHandling)) if step.responseHandling else None,
            error_mapping_json=_dumps(_model_dump(step.errorMapping)) if step.errorMapping else None,
            business_error_mapping_json=_dumps(_model_dump(step.businessErrorMapping)) if step.businessErrorMapping else None,
            retry_policy_json=_dumps(_model_dump(step.retryPolicy)) if step.retryPolicy else None,
            created_at=now,
            updated_at=now,
        )

    def _sql_config_row(
        self,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        step_row: DataFactorySceneStepRow,
        step: SqlStepDefinition,
        now: datetime,
    ) -> DataFactorySceneStepSqlConfigRow:
        param_mapping = step.paramMapping
        payload = _sql_hash_payload(step, param_mapping)
        config_hash = _hash_payload(payload)
        return DataFactorySceneStepSqlConfigRow(
            id=_new_id(),
            scene_id=scene_row.id,
            scene_version_id=version_row.id,
            scene_step_id=step_row.id,
            scene_code=scene_row.scene_code,
            version_no=version_row.version_no,
            step_id=step.stepId,
            source_code=step.templateRef.sourceCode if step.templateRef else None,
            source_name_at_snapshot=step.templateRef.sourceNameAtSnapshot if step.templateRef else None,
            source_updated_at_snapshot=step.templateRef.sourceUpdatedAtSnapshot if step.templateRef else None,
            source_hash_snapshot=step.templateRef.sourceHashSnapshot if step.templateRef else None,
            config_hash=config_hash,
            snapshot_at=now,
            drifted=step.templateRef.drifted if step.templateRef else False,
            source_name=step.sourceName or step.stepName,
            sys_code=step.sysCode,
            datasource_code=step.datasourceCode,
            operation=step.operation.value if step.operation else None,
            sql_text=step.sqlText,
            normalized_sql=step.normalizedSql,
            tables_json=_dumps(step.tables),
            result_fields_json=_dumps(step.resultFields),
            condition_fields_json=_dumps(step.conditionFields),
            parameters_json=_dumps(step.parameters),
            safety_json=_dumps(_model_dump(step.safety)),
            param_mapping_json=_dumps(param_mapping),
            created_at=now,
            updated_at=now,
        )

    def _assert_config_row(
        self,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        step_row: DataFactorySceneStepRow,
        step: AssertStepDefinition,
        now: datetime,
    ) -> DataFactorySceneStepAssertConfigRow:
        payload = _assert_hash_payload(step)
        return DataFactorySceneStepAssertConfigRow(
            id=_new_id(),
            scene_id=scene_row.id,
            scene_version_id=version_row.id,
            scene_step_id=step_row.id,
            scene_code=scene_row.scene_code,
            version_no=version_row.version_no,
            step_id=step.stepId,
            config_hash=_hash_payload(payload),
            assertions_json=_dumps(_model_dump(step.assertions)),
            created_at=now,
            updated_at=now,
        )

    def _transform_config_row(
        self,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        step_row: DataFactorySceneStepRow,
        step: TransformStepDefinition,
        now: datetime,
    ) -> DataFactorySceneStepTransformConfigRow:
        payload = _transform_hash_payload(step)
        return DataFactorySceneStepTransformConfigRow(
            id=_new_id(),
            scene_id=scene_row.id,
            scene_version_id=version_row.id,
            scene_step_id=step_row.id,
            scene_code=scene_row.scene_code,
            version_no=version_row.version_no,
            step_id=step.stepId,
            config_hash=_hash_payload(payload),
            assignments_json=_dumps(step.assignments),
            created_at=now,
            updated_at=now,
        )

    async def _to_scene_version(
        self,
        session: AsyncSession,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
    ) -> SceneVersion:
        steps = await self._load_steps(session, version_row.id)
        definition = SceneDefinition(
            sceneCode=scene_row.scene_code,
            sceneName=scene_row.scene_name,
            sceneRemark=scene_row.scene_remark,
            sceneType=scene_row.scene_type,
            inputSchema=_loads(version_row.input_schema_json, []),
            steps=steps,
            resultSchema=_loads(version_row.result_schema_json, None),
            resultMapping=_loads(version_row.result_mapping_json, {}),
            errorPolicy=version_row.error_policy_json or "STOP_ON_ERROR",
            batchConfig=_loads(version_row.batch_config_json, {}),
            status=_definition_status(scene_row, version_row),
        )
        return SceneVersion(
            id=version_row.id,
            sceneCode=scene_row.scene_code,
            versionNo=version_row.version_no,
            versionStatus=version_row.version_status,
            definition=definition,
            validationResult=_loads(version_row.validation_result_json, None),
            createdBy=version_row.created_by,
            updatedBy=version_row.updated_by,
            createdAt=version_row.created_at,
            updatedAt=version_row.updated_at,
            publishedBy=version_row.published_by,
            publishedAt=version_row.published_at,
        )

    async def _load_steps(self, session: AsyncSession, scene_version_id: str) -> list[StepDefinition]:
        stmt = (
            select(DataFactorySceneStepRow)
            .where(DataFactorySceneStepRow.scene_version_id == scene_version_id)
            .order_by(DataFactorySceneStepRow.sort_order.asc(), DataFactorySceneStepRow.step_id.asc())
        )
        step_rows = (await session.execute(stmt)).scalars().all()
        zero_based_sort_order = any(row.sort_order == 0 for row in step_rows)
        http_rows = {
            row.scene_step_id: row
            for row in (await session.execute(select(DataFactorySceneStepHttpConfigRow).where(DataFactorySceneStepHttpConfigRow.scene_version_id == scene_version_id))).scalars().all()
        }
        sql_rows = {
            row.scene_step_id: row
            for row in (await session.execute(select(DataFactorySceneStepSqlConfigRow).where(DataFactorySceneStepSqlConfigRow.scene_version_id == scene_version_id))).scalars().all()
        }
        assert_rows = {
            row.scene_step_id: row
            for row in (await session.execute(select(DataFactorySceneStepAssertConfigRow).where(DataFactorySceneStepAssertConfigRow.scene_version_id == scene_version_id))).scalars().all()
        }
        transform_rows = {
            row.scene_step_id: row
            for row in (await session.execute(select(DataFactorySceneStepTransformConfigRow).where(DataFactorySceneStepTransformConfigRow.scene_version_id == scene_version_id))).scalars().all()
        }
        return [
            self._to_step(
                row,
                http_rows.get(row.id),
                sql_rows.get(row.id),
                assert_rows.get(row.id),
                transform_rows.get(row.id),
                zero_based_sort_order,
            )
            for row in step_rows
        ]

    @staticmethod
    def _to_step(
        step_row: DataFactorySceneStepRow,
        http_row: DataFactorySceneStepHttpConfigRow | None,
        sql_row: DataFactorySceneStepSqlConfigRow | None,
        assert_row: DataFactorySceneStepAssertConfigRow | None,
        transform_row: DataFactorySceneStepTransformConfigRow | None,
        zero_based_sort_order: bool,
    ) -> StepDefinition:
        base: dict[str, Any] = {
            "stepId": step_row.step_id,
            "stepName": step_row.step_name,
            "type": step_row.step_type,
            "executionOrder": step_row.sort_order + 1 if zero_based_sort_order else step_row.sort_order,
            "enabled": step_row.enabled,
            "dependsOn": _loads(step_row.depends_on_json, []),
            "description": step_row.description,
            "position": _loads(step_row.position_json, None),
            "outputMapping": _loads(step_row.output_mapping_json, {}),
            "outputMeta": _loads(step_row.output_meta_json, None),
        }
        if http_row:
            base.update(
                {
                    "templateRef": _row_template_ref(http_row, "HTTP_SOURCE"),
                    "sourceName": http_row.source_name,
                    "sysCode": http_row.sys_code,
                    "method": http_row.method,
                    "path": http_row.path,
                    "timeoutConfig": _loads(http_row.timeout_config_json, {}),
                    "requestMapping": _loads(http_row.request_mapping_json, {}),
                    "httpParamMapping": _loads(http_row.http_param_mapping_json, {}),
                    "bodySchema": _loads(http_row.body_schema_json, None),
                    "responseSchema": _loads(http_row.response_schema_json, None),
                    "responseHeadersSchema": _loads(http_row.response_headers_schema_json, None),
                    "responseCookiesSchema": _loads(http_row.response_cookies_schema_json, None),
                    "responseHandling": _loads(http_row.response_handling_json, None),
                    "errorMapping": _loads(http_row.error_mapping_json, None),
                    "businessErrorMapping": _loads(http_row.business_error_mapping_json, None),
                    "retryPolicy": _loads(http_row.retry_policy_json, None),
                }
            )
        if sql_row:
            param_mapping = _loads(sql_row.param_mapping_json, {})
            base.update(
                {
                    "templateRef": _row_template_ref(sql_row, "SQL_SOURCE"),
                    "sourceName": sql_row.source_name,
                    "sysCode": sql_row.sys_code,
                    "datasourceCode": sql_row.datasource_code,
                    "operation": sql_row.operation,
                    "sqlText": sql_row.sql_text,
                    "normalizedSql": sql_row.normalized_sql,
                    "tables": _loads(sql_row.tables_json, []),
                    "resultFields": _loads(sql_row.result_fields_json, []),
                    "conditionFields": _loads(sql_row.condition_fields_json, []),
                    "parameters": _loads(sql_row.parameters_json, []),
                    "safety": _loads(sql_row.safety_json, {}),
                    "paramMapping": param_mapping,
                }
            )
        if assert_row:
            base.update({"assertions": _loads(assert_row.assertions_json, [])})
        if transform_row:
            base.update({"assignments": _loads(transform_row.assignments_json, {})})
        return parse_step_definition_payload(base)

    @staticmethod
    def _to_summary(row: DataFactorySceneRow) -> SceneSummary:
        return SceneSummary(
            id=row.id,
            sceneCode=row.scene_code,
            sceneName=row.scene_name,
            sceneRemark=row.scene_remark,
            sceneType=row.scene_type,
            status=row.status,
            currentVersionNo=row.current_version_no,
            publishedVersionNo=row.published_version_no,
            createdBy=row.created_by,
            updatedBy=row.updated_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    @staticmethod
    def _to_step_execution_result(row: DataFactorySceneRunStepRow) -> StepExecutionResult:
        return StepExecutionResult(
            stepId=row.step_id,
            stepName=row.step_name,
            type=row.step_type,
            stepOrder=row.step_order,
            timelineOrder=row.timeline_order,
            status=row.status,
            startedAt=row.started_at,
            finishedAt=row.finished_at,
            durationMs=row.duration_ms,
            outputs=_loads(row.outputs_json, {}),
            rawResponse=_loads(row.raw_response_json, None),
            error=row.error,
            statusCode=row.status_code,
        )

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


def _http_hash_payload(step: HttpStepDefinition) -> dict[str, Any]:
    return {
        "sourceName": step.sourceName or step.stepName,
        "sysCode": step.sysCode,
        "path": step.path,
        "method": step.method,
        "timeoutConfig": step.timeoutConfig,
        "requestMapping": step.requestMapping,
        "httpParamMapping": step.httpParamMapping,
        "bodySchema": step.bodySchema,
        "responseSchema": step.responseSchema,
        "responseHeadersSchema": step.responseHeadersSchema,
        "responseCookiesSchema": step.responseCookiesSchema,
        "responseHandling": step.responseHandling,
        "errorMapping": step.errorMapping,
        "businessErrorMapping": step.businessErrorMapping,
        "retryPolicy": step.retryPolicy,
        "outputMapping": step.outputMapping,
        "outputMeta": step.outputMeta,
    }


def _sql_hash_payload(step: SqlStepDefinition, param_mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceName": step.sourceName or step.stepName,
        "sysCode": step.sysCode,
        "datasourceCode": step.datasourceCode,
        "operation": step.operation,
        "sqlText": step.sqlText,
        "normalizedSql": step.normalizedSql,
        "tables": step.tables,
        "resultFields": step.resultFields,
        "conditionFields": step.conditionFields,
        "parameters": step.parameters,
        "safety": step.safety,
        "paramMapping": param_mapping,
        "outputMapping": step.outputMapping,
        "outputMeta": step.outputMeta,
    }


def _assert_hash_payload(step: AssertStepDefinition) -> dict[str, Any]:
    return {
        "assertions": step.assertions,
        "outputMapping": step.outputMapping,
        "outputMeta": step.outputMeta,
    }


def _transform_hash_payload(step: TransformStepDefinition) -> dict[str, Any]:
    return {
        "assignments": step.assignments,
        "outputMapping": step.outputMapping,
        "outputMeta": step.outputMeta,
    }


def _steps_by_execution_order(steps: list[StepDefinition]) -> list[StepDefinition]:
    """按显式执行顺序排序步骤，缺失顺序时使用请求列表位置兜底。"""

    return [
        step
        for _, step in sorted(
            enumerate(steps),
            key=lambda item: (item[1].executionOrder or item[0] + 1, item[0]),
        )
    ]


def _row_template_ref(row: Any, ref_type: str) -> StepTemplateRef | None:
    if not row.source_code:
        return None
    return StepTemplateRef(
        type=ref_type,
        sourceCode=row.source_code,
        sourceNameAtSnapshot=row.source_name_at_snapshot,
        sourceUpdatedAtSnapshot=row.source_updated_at_snapshot,
        sourceHashSnapshot=row.source_hash_snapshot,
        configHash=row.config_hash,
        snapshotAt=row.snapshot_at,
        drifted=row.drifted,
    )


def _definition_status(scene_row: DataFactorySceneRow, version_row: DataFactorySceneVersionRow) -> SceneStatus:
    if scene_row.status == SceneStatus.DISABLED.value:
        return SceneStatus.DISABLED
    if version_row.version_status == VersionStatus.PUBLISHED.value:
        return SceneStatus.PUBLISHED
    return SceneStatus.DRAFT
