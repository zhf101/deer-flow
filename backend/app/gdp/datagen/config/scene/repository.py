"""场景编排持久化仓储。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.gdp.datagen.config.base.repository import DataFactoryConfigAuditRow
from app.gdp.datagen.config.common.models import SceneStatus, StepType, VersionStatus
from app.gdp.datagen.config.scene.models import (
    SceneDefinition,
    SceneSummary,
    SceneVersion,
    StepDefinition,
    StepTemplateRef,
    ValidationResult,
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
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, comment="步骤顺序。")
    step_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="步骤业务 ID。")
    step_name: Mapped[str | None] = mapped_column(String(256), comment="步骤名称。")
    step_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="步骤类型。")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, comment="是否启用。")
    depends_on_json: Mapped[str] = mapped_column(Text, nullable=False, comment="步骤依赖 JSON。")
    position_json: Mapped[str | None] = mapped_column(Text, comment="画布坐标 JSON。")
    description: Mapped[str | None] = mapped_column(Text, comment="步骤说明。")
    output_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, comment="输出映射 JSON。")
    output_meta_json: Mapped[str | None] = mapped_column(Text, comment="输出变量元数据 JSON。")
    assertions_json: Mapped[str] = mapped_column(Text, nullable=False, comment="断言 JSON。")
    assignments_json: Mapped[str] = mapped_column(Text, nullable=False, comment="变量赋值 JSON。")
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
        await session.execute(delete(DataFactorySceneStepRow).where(DataFactorySceneStepRow.scene_version_id == scene_version_id))

    def _add_steps(
        self,
        session: AsyncSession,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        steps: list[StepDefinition],
        now: datetime,
    ) -> None:
        for index, step in enumerate(steps):
            _ensure_custom_step_only(step)
            step_row = DataFactorySceneStepRow(
                id=_new_id(),
                scene_id=scene_row.id,
                scene_version_id=version_row.id,
                scene_code=scene_row.scene_code,
                version_no=version_row.version_no,
                sort_order=index,
                step_id=step.stepId,
                step_name=step.stepName,
                step_type=step.type.value,
                enabled=step.enabled,
                depends_on_json=_dumps(step.dependsOn),
                position_json=_dumps(_model_dump(step.position)) if step.position else None,
                description=step.description,
                output_mapping_json=_dumps(step.outputMapping),
                output_meta_json=_dumps(step.outputMeta) if step.outputMeta else None,
                assertions_json=_dumps(_model_dump(step.assertions)),
                assignments_json=_dumps(step.assignments),
                created_at=now,
                updated_at=now,
            )
            session.add(step_row)
            if step.type == StepType.HTTP:
                session.add(self._http_config_row(scene_row, version_row, step_row, step, now))
            elif step.type == StepType.SQL:
                session.add(self._sql_config_row(scene_row, version_row, step_row, step, now))

    def _http_config_row(
        self,
        scene_row: DataFactorySceneRow,
        version_row: DataFactorySceneVersionRow,
        step_row: DataFactorySceneStepRow,
        step: StepDefinition,
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
            source_code=None,
            source_name_at_snapshot=None,
            source_updated_at_snapshot=None,
            source_hash_snapshot=None,
            config_hash=config_hash,
            snapshot_at=now,
            drifted=False,
            source_name=step.sourceName or step.stepName,
            sys_code=step.sysCode,
            path=step.path or step.url,
            method=step.method.value if step.method else None,
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
        step: StepDefinition,
        now: datetime,
    ) -> DataFactorySceneStepSqlConfigRow:
        param_mapping = step.paramMapping or step.sqlParamMapping
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
            source_code=None,
            source_name_at_snapshot=None,
            source_updated_at_snapshot=None,
            source_hash_snapshot=None,
            config_hash=config_hash,
            snapshot_at=now,
            drifted=False,
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
        http_rows = {
            row.scene_step_id: row
            for row in (await session.execute(select(DataFactorySceneStepHttpConfigRow).where(DataFactorySceneStepHttpConfigRow.scene_version_id == scene_version_id))).scalars().all()
        }
        sql_rows = {
            row.scene_step_id: row
            for row in (await session.execute(select(DataFactorySceneStepSqlConfigRow).where(DataFactorySceneStepSqlConfigRow.scene_version_id == scene_version_id))).scalars().all()
        }
        return [self._to_step(row, http_rows.get(row.id), sql_rows.get(row.id)) for row in step_rows]

    @staticmethod
    def _to_step(
        step_row: DataFactorySceneStepRow,
        http_row: DataFactorySceneStepHttpConfigRow | None,
        sql_row: DataFactorySceneStepSqlConfigRow | None,
    ) -> StepDefinition:
        base: dict[str, Any] = {
            "stepId": step_row.step_id,
            "stepName": step_row.step_name,
            "type": step_row.step_type,
            "enabled": step_row.enabled,
            "dependsOn": _loads(step_row.depends_on_json, []),
            "description": step_row.description,
            "position": _loads(step_row.position_json, None),
            "outputMapping": _loads(step_row.output_mapping_json, {}),
            "outputMeta": _loads(step_row.output_meta_json, None),
            "assertions": _loads(step_row.assertions_json, []),
            "assignments": _loads(step_row.assignments_json, {}),
        }
        if http_row:
            base.update(
                {
                    "templateRef": _row_template_ref(http_row, "HTTP_SOURCE"),
                    "httpSourceCode": http_row.source_code,
                    "sourceName": http_row.source_name,
                    "sysCode": http_row.sys_code,
                    "method": http_row.method,
                    "path": http_row.path,
                    "url": http_row.path,
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
                    "sqlSourceCode": sql_row.source_code,
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
                    "sqlParamMapping": param_mapping,
                }
            )
        return StepDefinition(**base)

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


def _http_hash_payload(step: StepDefinition) -> dict[str, Any]:
    return {
        "sourceName": step.sourceName or step.stepName,
        "sysCode": step.sysCode,
        "path": step.path or step.url,
        "method": step.method,
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


def _ensure_custom_step_only(step: StepDefinition) -> None:
    if step.templateRef is not None or step.httpSourceCode or step.sqlSourceCode:
        raise SceneConflictError("template references are not supported in custom scene step persistence")


def _sql_hash_payload(step: StepDefinition, param_mapping: dict[str, Any]) -> dict[str, Any]:
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
