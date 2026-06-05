"""GDP 造数工厂持久化仓储——封装所有 SQLAlchemy 异步 CRUD 操作。

仓储层直接操作 ORM 行模型，对上层（Service）屏蔽数据库交互细节：
- 每个公开方法自行管理 AsyncSession 生命周期（通过 async_sessionmaker）；
- 所有写操作统一通过 ``_commit`` 提交，自动捕获唯一约束冲突并转换为业务异常；
- 关键变更操作同步写入审计日志表 df_config_audit。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gdp.models import (
    ConfigStatus,
    DatasourceConfig,
    DatasourceResponse,
    EnvironmentConfig,
    EnvironmentResponse,
    SceneDefinition,
    SceneStatus,
    SceneSummary,
    SceneVersion,
    ServiceEndpointConfig,
    ServiceEndpointResponse,
    SqlTemplateConfig,
    SqlTemplateResponse,
    ValidationResult,
    VersionStatus,
)
from app.gdp.persistence.model import (
    DataFactoryConfigAuditRow,
    DataFactoryDatasourceRow,
    DataFactoryEnvironmentRow,
    DataFactorySceneRow,
    DataFactorySceneVersionRow,
    DataFactoryServiceEndpointRow,
    DataFactorySqlTemplateRow,
)


# 业务异常：请求的资源不存在
class DataFactoryNotFoundError(LookupError):
    """当请求的造数工厂配置实体不存在时抛出。"""


# 业务异常：唯一约束冲突
class DataFactoryConflictError(RuntimeError):
    """当造数工厂配置实体违反唯一约束时抛出（如重复的 sceneCode）。"""


def _new_id() -> str:
    """生成全局唯一的 UUID 主键。"""
    return str(uuid.uuid4())


def _now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    """将 Python 对象序列化为紧凑 JSON 字符串，支持中文非转义。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    """将 JSON 字符串反序列化为 Python 对象，空值时返回默认值。"""
    if value is None or value == "":
        return default
    return json.loads(value)


class DataFactoryRepository:
    """造数工厂仓储类，封装全部数据库 CRUD 操作。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    # ========================= 场景 CRUD =========================

    # 分页查询场景列表，支持按类型、状态、关键字过滤
    async def list_scenes(
        self,
        *,
        scene_type: str | None = None,
        status: SceneStatus | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SceneSummary]:
        stmt = select(DataFactorySceneRow)
        if scene_type:
            stmt = stmt.where(DataFactorySceneRow.scene_type == scene_type)
        if status:
            stmt = stmt.where(DataFactorySceneRow.status == status.value)
        if keyword:
            # 关键字同时模糊匹配场景编码和场景名称
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                DataFactorySceneRow.scene_code.like(pattern) | DataFactorySceneRow.scene_name.like(pattern)
            )
        stmt = stmt.order_by(DataFactorySceneRow.updated_at.desc(), DataFactorySceneRow.scene_code.asc()).offset(offset).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._scene_summary(row) for row in rows]

    # 新建场景：写入主表 + 创建首个版本记录 + 审计日志
    async def create_scene(self, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        async with self._sf() as session:
            existing = await self._get_scene_row(session, definition.sceneCode)
            if existing is not None:
                raise DataFactoryConflictError(f"sceneCode already exists: {definition.sceneCode}")
            now = _now()
            scene = DataFactorySceneRow(
                id=_new_id(),
                scene_code=definition.sceneCode,
                scene_name=definition.sceneName,
                scene_remark=definition.sceneRemark,
                scene_type=definition.sceneType,
                status=SceneStatus.DRAFT.value,
                current_version_no=None,
                created_by=operator,
                updated_by=operator,
                created_at=now,
                updated_at=now,
            )
            session.add(scene)
            version = self._make_version_row(scene, definition, version_no=1, operator=operator)
            session.add(version)
            self._add_audit(session, "SCENE", scene.id, "CREATE", operator, None, self._definition_payload(definition))
            await self._commit(session)
            await session.refresh(scene)
            await session.refresh(version)
            return self._scene_version(scene, version)

    # 更新场景：状态回退为 DRAFT，递增版本号并写入新版本快照
    async def update_scene(self, scene_code: str, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        if scene_code != definition.sceneCode:
            raise DataFactoryConflictError("path sceneCode must match request sceneCode")
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            before = self._scene_row_payload(scene)
            scene.scene_name = definition.sceneName
            scene.scene_remark = definition.sceneRemark
            scene.scene_type = definition.sceneType
            scene.status = SceneStatus.DRAFT.value
            scene.updated_by = operator
            scene.updated_at = _now()
            # 计算下一个版本号
            version_no = await self._next_version_no(session, scene.id)
            version = self._make_version_row(scene, definition, version_no=version_no, operator=operator)
            session.add(version)
            self._add_audit(session, "SCENE", scene.id, "UPDATE_DRAFT", operator, before, self._definition_payload(definition))
            await self._commit(session)
            await session.refresh(scene)
            await session.refresh(version)
            return self._scene_version(scene, version)

    # 获取场景完整定义（场景主信息 + 最新版本配置）
    async def get_scene_definition(self, scene_code: str) -> SceneDefinition:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            version = await self._require_latest_version_row(session, scene.id)
            return self._definition_from_rows(scene, version)

    # 获取场景定义（专用于校验场景的别名方法）
    async def validate_scene_saved(self, scene_code: str) -> SceneDefinition:
        return await self.get_scene_definition(scene_code)

    # 发布场景：将最新草稿版本标记为 PUBLISHED，同步更新主表状态和当前版本号
    async def publish_scene(
        self,
        scene_code: str,
        validation_result: ValidationResult,
        *,
        operator: str | None = None,
    ) -> SceneVersion:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            version = await self._require_latest_version_row(session, scene.id)
            # 如果已经是发布态则幂等返回
            if version.version_status == VersionStatus.PUBLISHED.value:
                return self._scene_version(scene, version)
            before = self._scene_row_payload(scene)
            now = _now()
            version.version_status = VersionStatus.PUBLISHED.value
            version.validation_result_json = _dumps(validation_result.model_dump(mode="json"))
            version.published_by = operator
            version.published_at = now
            scene.status = SceneStatus.PUBLISHED.value
            scene.current_version_no = version.version_no
            scene.updated_by = operator
            scene.updated_at = now
            self._add_audit(
                session,
                "SCENE",
                scene.id,
                "PUBLISH",
                operator,
                before,
                {"sceneCode": scene_code, "versionNo": version.version_no},
            )
            await self._commit(session)
            await session.refresh(scene)
            await session.refresh(version)
            return self._scene_version(scene, version)

    # 禁用场景：仅修改状态为 DISABLED，保留全部数据
    async def disable_scene(self, scene_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            before = self._scene_row_payload(scene)
            scene.status = SceneStatus.DISABLED.value
            scene.updated_by = operator
            scene.updated_at = _now()
            self._add_audit(session, "SCENE", scene.id, "DISABLE", operator, before, self._scene_row_payload(scene))
            await self._commit(session)
            return True

    # 查询场景的全部版本历史，按版本号降序
    async def list_scene_versions(self, scene_code: str) -> list[SceneVersion]:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            stmt = (
                select(DataFactorySceneVersionRow)
                .where(DataFactorySceneVersionRow.scene_id == scene.id)
                .order_by(DataFactorySceneVersionRow.version_no.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._scene_version(scene, row) for row in rows]

    # 获取场景的指定版本
    async def get_scene_version(self, scene_code: str, version_no: int) -> SceneVersion:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            stmt = select(DataFactorySceneVersionRow).where(
                DataFactorySceneVersionRow.scene_id == scene.id,
                DataFactorySceneVersionRow.version_no == version_no,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise DataFactoryNotFoundError(f"scene version not found: {scene_code}@{version_no}")
            return self._scene_version(scene, row)

    # ========================= SQL 模板 CRUD =========================

    # 查询 SQL 模板列表，可按状态过滤，按更新时间降序
    async def list_sql_templates(self, *, status: ConfigStatus | None = None) -> list[SqlTemplateResponse]:
        stmt = select(DataFactorySqlTemplateRow)
        if status:
            stmt = stmt.where(DataFactorySqlTemplateRow.status == status.value)
        stmt = stmt.order_by(DataFactorySqlTemplateRow.updated_at.desc(), DataFactorySqlTemplateRow.template_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._sql_template_response(row) for row in rows]

    # 获取指定 SQL 模板详情
    async def get_sql_template(self, template_code: str) -> SqlTemplateResponse:
        async with self._sf() as session:
            row = await self._require_sql_template_row(session, template_code)
            return self._sql_template_response(row)

    # Upsert SQL 模板：存在则更新，不存在则新建
    async def upsert_sql_template(
        self,
        template: SqlTemplateConfig,
        *,
        operator: str | None = None,
    ) -> SqlTemplateResponse:
        async with self._sf() as session:
            row = await self._get_sql_template_row(session, template.templateCode)
            now = _now()
            if row is None:
                # 新建模板
                row = DataFactorySqlTemplateRow(
                    id=_new_id(),
                    template_code=template.templateCode,
                    template_name=template.templateName,
                    operation=template.operation.value,
                    datasource_type=template.datasourceType,
                    sql_text=template.sqlText,
                    parameters_json=_dumps([p.model_dump(mode="json") for p in template.parameters]),
                    safety_json=_dumps(template.safety.model_dump(mode="json")),
                    status=template.status.value,
                    created_by=operator,
                    updated_by=operator,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                action = "CREATE_SQL_TEMPLATE"
            else:
                # 更新已有模板的字段
                row.template_name = template.templateName
                row.operation = template.operation.value
                row.datasource_type = template.datasourceType
                row.sql_text = template.sqlText
                row.parameters_json = _dumps([p.model_dump(mode="json") for p in template.parameters])
                row.safety_json = _dumps(template.safety.model_dump(mode="json"))
                row.status = template.status.value
                row.updated_by = operator
                row.updated_at = now
                action = "UPDATE_SQL_TEMPLATE"
            self._add_audit(session, "SQL_TEMPLATE", row.id, action, operator, None, template.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(row)
            return self._sql_template_response(row)

    # 禁用 SQL 模板：修改状态为 DISABLED
    async def disable_sql_template(self, template_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            row = await self._require_sql_template_row(session, template_code)
            row.status = ConfigStatus.DISABLED.value
            row.updated_by = operator
            row.updated_at = _now()
            self._add_audit(session, "SQL_TEMPLATE", row.id, "DISABLE_SQL_TEMPLATE", operator, None, {"templateCode": template_code})
            await self._commit(session)
            return True

    # ========================= 环境 CRUD =========================

    # 查询全部环境配置，按 env_code 升序
    async def list_environments(self) -> list[EnvironmentResponse]:
        async with self._sf() as session:
            rows = (await session.execute(select(DataFactoryEnvironmentRow).order_by(DataFactoryEnvironmentRow.env_code.asc()))).scalars().all()
            return [self._environment_response(row) for row in rows]

    # Upsert 环境配置：存在则更新名称/状态/备注，不存在则新建
    async def upsert_environment(self, config: EnvironmentConfig) -> EnvironmentResponse:
        async with self._sf() as session:
            stmt = select(DataFactoryEnvironmentRow).where(DataFactoryEnvironmentRow.env_code == config.envCode)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = _now()
            if row is None:
                row = DataFactoryEnvironmentRow(
                    id=_new_id(),
                    env_code=config.envCode,
                    env_name=config.envName,
                    status=config.status.value,
                    remark=config.remark,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.env_name = config.envName
                row.status = config.status.value
                row.remark = config.remark
                row.updated_at = now
            await self._commit(session)
            await session.refresh(row)
            return self._environment_response(row)

    # ========================= 服务端点 CRUD =========================

    # 查询服务端点列表，可按环境过滤
    async def list_service_endpoints(self, *, env_code: str | None = None) -> list[ServiceEndpointResponse]:
        stmt = select(DataFactoryServiceEndpointRow)
        if env_code:
            stmt = stmt.where(DataFactoryServiceEndpointRow.env_code == env_code)
        stmt = stmt.order_by(DataFactoryServiceEndpointRow.env_code.asc(), DataFactoryServiceEndpointRow.service_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._service_endpoint_response(row) for row in rows]

    # 新建服务端点
    async def create_service_endpoint(self, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        row = DataFactoryServiceEndpointRow(
            id=_new_id(),
            env_code=config.envCode,
            service_code=config.serviceCode,
            service_name=config.serviceName,
            base_url=config.baseUrl,
            status=config.status.value,
            created_at=_now(),
            updated_at=_now(),
        )
        async with self._sf() as session:
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._service_endpoint_response(row)

    # 根据 ID 更新服务端点
    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryServiceEndpointRow, endpoint_id, "service endpoint")
            row.env_code = config.envCode
            row.service_code = config.serviceCode
            row.service_name = config.serviceName
            row.base_url = config.baseUrl
            row.status = config.status.value
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._service_endpoint_response(row)

    # ========================= 数据源 CRUD =========================

    # 查询数据源列表，可按环境过滤
    async def list_datasources(self, *, env_code: str | None = None) -> list[DatasourceResponse]:
        stmt = select(DataFactoryDatasourceRow)
        if env_code:
            stmt = stmt.where(DataFactoryDatasourceRow.env_code == env_code)
        stmt = stmt.order_by(DataFactoryDatasourceRow.env_code.asc(), DataFactoryDatasourceRow.datasource_code.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._datasource_response(row) for row in rows]

    # 新建数据源
    async def create_datasource(self, config: DatasourceConfig) -> DatasourceResponse:
        row = DataFactoryDatasourceRow(
            id=_new_id(),
            env_code=config.envCode,
            datasource_code=config.datasourceCode,
            datasource_name=config.datasourceName,
            db_type=config.dbType,
            host=config.host,
            port=config.port,
            database_name=config.databaseName,
            username=config.username,
            password=config.password,
            status=config.status.value,
            created_at=_now(),
            updated_at=_now(),
        )
        async with self._sf() as session:
            session.add(row)
            await self._commit(session)
            await session.refresh(row)
            return self._datasource_response(row)

    # 根据 ID 更新数据源
    async def update_datasource(self, datasource_id: str, config: DatasourceConfig) -> DatasourceResponse:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryDatasourceRow, datasource_id, "datasource")
            row.env_code = config.envCode
            row.datasource_code = config.datasourceCode
            row.datasource_name = config.datasourceName
            row.db_type = config.dbType
            row.host = config.host
            row.port = config.port
            row.database_name = config.databaseName
            row.username = config.username
            row.password = config.password
            row.status = config.status.value
            row.updated_at = _now()
            await self._commit(session)
            await session.refresh(row)
            return self._datasource_response(row)

    # ========================= 删除操作 =========================

    # 物理删除场景：先删除全部版本记录，再删除主表记录
    async def delete_scene(self, scene_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            before = self._scene_row_payload(scene)

            # 先删除关联的版本记录（避免外键或孤儿数据）
            stmt_versions = select(DataFactorySceneVersionRow).where(DataFactorySceneVersionRow.scene_id == scene.id)
            versions = (await session.execute(stmt_versions)).scalars().all()
            for version in versions:
                await session.delete(version)

            await session.delete(scene)
            self._add_audit(session, "SCENE", scene.id, "DELETE", operator, before, None)
            await self._commit(session)
            return True

    # 复制场景：以源场景最新版本为蓝本，在目标编码下创建新草稿
    async def copy_scene(self, scene_code: str, target_scene_code: str, *, operator: str | None = None) -> SceneVersion:
        async with self._sf() as session:
            source_scene = await self._require_scene_row(session, scene_code)
            source_version = await self._require_latest_version_row(session, source_scene.id)

            # 检查目标编码是否已被占用
            existing = await self._get_scene_row(session, target_scene_code)
            if existing is not None:
                raise DataFactoryConflictError(f"target sceneCode already exists: {target_scene_code}")

            # 从源场景最新版本构建定义，修改编码和名称
            definition = self._definition_from_rows(source_scene, source_version)
            definition.sceneCode = target_scene_code
            definition.sceneName = f"Copy of {definition.sceneName}"

            now = _now()
            new_scene = DataFactorySceneRow(
                id=_new_id(),
                scene_code=target_scene_code,
                scene_name=definition.sceneName,
                scene_remark=definition.sceneRemark,
                scene_type=definition.sceneType,
                status=SceneStatus.DRAFT.value,
                current_version_no=None,
                created_by=operator,
                updated_by=operator,
                created_at=now,
                updated_at=now,
            )
            session.add(new_scene)
            new_version = self._make_version_row(new_scene, definition, version_no=1, operator=operator)
            session.add(new_version)
            self._add_audit(session, "SCENE", new_scene.id, "COPY_FROM", operator, {"source": scene_code}, self._definition_payload(definition))
            await self._commit(session)
            await session.refresh(new_scene)
            await session.refresh(new_version)
            return self._scene_version(new_scene, new_version)

    # 物理删除环境配置
    async def delete_environment(self, env_code: str) -> bool:
        async with self._sf() as session:
            stmt = select(DataFactoryEnvironmentRow).where(DataFactoryEnvironmentRow.env_code == env_code)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise DataFactoryNotFoundError(f"environment not found: {env_code}")
            await session.delete(row)
            await self._commit(session)
            return True

    # 物理删除服务端点
    async def delete_service_endpoint(self, endpoint_id: str) -> bool:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryServiceEndpointRow, endpoint_id, "service endpoint")
            await session.delete(row)
            await self._commit(session)
            return True

    # 物理删除数据源
    async def delete_datasource(self, datasource_id: str) -> bool:
        async with self._sf() as session:
            row = await self._require_by_id(session, DataFactoryDatasourceRow, datasource_id, "datasource")
            await session.delete(row)
            await self._commit(session)
            return True

    # ========================= 内部辅助方法 =========================

    # 统一提交入口：捕获唯一约束冲突并转换为业务异常
    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise DataFactoryConflictError("data-factory unique constraint violation") from exc

    # 按 scene_code 查询场景行，不存在返回 None
    async def _get_scene_row(self, session: AsyncSession, scene_code: str) -> DataFactorySceneRow | None:
        stmt = select(DataFactorySceneRow).where(DataFactorySceneRow.scene_code == scene_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    # 按 scene_code 查询场景行，不存在则抛出 NotFoundError
    async def _require_scene_row(self, session: AsyncSession, scene_code: str) -> DataFactorySceneRow:
        row = await self._get_scene_row(session, scene_code)
        if row is None:
            raise DataFactoryNotFoundError(f"scene not found: {scene_code}")
        return row

    # 计算场景的下一个版本号（当前最大版本号 + 1）
    async def _next_version_no(self, session: AsyncSession, scene_id: str) -> int:
        stmt = select(func.coalesce(func.max(DataFactorySceneVersionRow.version_no), 0)).where(DataFactorySceneVersionRow.scene_id == scene_id)
        return int((await session.execute(stmt)).scalar_one()) + 1

    # 获取场景的最新版本行（按 version_no 降序取第一条）
    async def _require_latest_version_row(self, session: AsyncSession, scene_id: str) -> DataFactorySceneVersionRow:
        stmt = (
            select(DataFactorySceneVersionRow)
            .where(DataFactorySceneVersionRow.scene_id == scene_id)
            .order_by(DataFactorySceneVersionRow.version_no.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise DataFactoryNotFoundError("scene version not found")
        return row

    # 按 template_code 查询 SQL 模板行，不存在返回 None
    async def _get_sql_template_row(self, session: AsyncSession, template_code: str) -> DataFactorySqlTemplateRow | None:
        stmt = select(DataFactorySqlTemplateRow).where(DataFactorySqlTemplateRow.template_code == template_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    # 按 template_code 查询 SQL 模板行，不存在则抛出 NotFoundError
    async def _require_sql_template_row(self, session: AsyncSession, template_code: str) -> DataFactorySqlTemplateRow:
        row = await self._get_sql_template_row(session, template_code)
        if row is None:
            raise DataFactoryNotFoundError(f"SQL template not found: {template_code}")
        return row

    # 通用按主键 ID 查询，不存在则抛出 NotFoundError
    async def _require_by_id(self, session: AsyncSession, row_type: type, row_id: str, label: str):
        row = await session.get(row_type, row_id)
        if row is None:
            raise DataFactoryNotFoundError(f"{label} not found: {row_id}")
        return row

    # 构建版本行模型：将 SceneDefinition 序列化为 JSON 写入版本表
    def _make_version_row(
        self,
        scene: DataFactorySceneRow,
        definition: SceneDefinition,
        *,
        version_no: int,
        operator: str | None,
    ) -> DataFactorySceneVersionRow:
        return DataFactorySceneVersionRow(
            id=_new_id(),
            scene_id=scene.id,
            scene_code=scene.scene_code,
            version_no=version_no,
            version_status=VersionStatus.DRAFT.value,
            environment_field=definition.environmentField,
            input_schema_json=_dumps([field.model_dump(mode="json") for field in definition.inputSchema]),
            steps_json=_dumps([step.model_dump(mode="json") for step in definition.steps]),
            result_mapping_json=_dumps(definition.resultMapping),
            batch_config_json=_dumps(definition.batchConfig.model_dump(mode="json")),
            validation_result_json=None,
            created_by=operator,
            created_at=_now(),
        )

    # 从主表行 + 版本行还原 SceneDefinition 对象
    def _definition_from_rows(self, scene: DataFactorySceneRow, version: DataFactorySceneVersionRow) -> SceneDefinition:
        return SceneDefinition(
            sceneCode=scene.scene_code,
            sceneName=scene.scene_name,
            sceneRemark=scene.scene_remark,
            sceneType=scene.scene_type,
            environmentField=version.environment_field,
            inputSchema=_loads(version.input_schema_json, []),
            steps=_loads(version.steps_json, []),
            resultMapping=_loads(version.result_mapping_json, {}),
            batchConfig=_loads(version.batch_config_json, {}),
            status=scene.status,
        )

    # 将场景主表行转换为摘要 DTO
    def _scene_summary(self, row: DataFactorySceneRow) -> SceneSummary:
        return SceneSummary(
            id=row.id,
            sceneCode=row.scene_code,
            sceneName=row.scene_name,
            sceneRemark=row.scene_remark,
            sceneType=row.scene_type,
            status=row.status,
            currentVersionNo=row.current_version_no,
            createdBy=row.created_by,
            updatedBy=row.updated_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    # 将场景主表行 + 版本行组合为版本 DTO
    def _scene_version(self, scene: DataFactorySceneRow, version: DataFactorySceneVersionRow) -> SceneVersion:
        return SceneVersion(
            id=version.id,
            sceneCode=version.scene_code,
            versionNo=version.version_no,
            versionStatus=version.version_status,
            definition=self._definition_from_rows(scene, version),
            validationResult=_loads(version.validation_result_json, None),
            createdBy=version.created_by,
            createdAt=version.created_at,
            publishedBy=version.published_by,
            publishedAt=version.published_at,
        )

    # 将 SQL 模板行转换为响应 DTO
    def _sql_template_response(self, row: DataFactorySqlTemplateRow) -> SqlTemplateResponse:
        return SqlTemplateResponse(
            id=row.id,
            templateCode=row.template_code,
            templateName=row.template_name,
            operation=row.operation,
            datasourceType=row.datasource_type,
            sqlText=row.sql_text,
            parameters=_loads(row.parameters_json, []),
            safety=_loads(row.safety_json, {}),
            status=row.status,
            createdBy=row.created_by,
            updatedBy=row.updated_by,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    # 将环境行转换为响应 DTO
    def _environment_response(self, row: DataFactoryEnvironmentRow) -> EnvironmentResponse:
        return EnvironmentResponse(
            id=row.id,
            envCode=row.env_code,
            envName=row.env_name,
            status=row.status,
            remark=row.remark,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    # 将服务端点行转换为响应 DTO
    def _service_endpoint_response(self, row: DataFactoryServiceEndpointRow) -> ServiceEndpointResponse:
        return ServiceEndpointResponse(
            id=row.id,
            envCode=row.env_code,
            serviceCode=row.service_code,
            serviceName=row.service_name,
            baseUrl=row.base_url,
            status=row.status,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    # 将数据源行转换为响应 DTO
    def _datasource_response(self, row: DataFactoryDatasourceRow) -> DatasourceResponse:
        return DatasourceResponse(
            id=row.id,
            envCode=row.env_code,
            datasourceCode=row.datasource_code,
            datasourceName=row.datasource_name,
            dbType=row.db_type,
            host=row.host,
            port=row.port,
            databaseName=row.database_name,
            username=row.username,
            password=row.password,
            status=row.status,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )

    # 将 SceneDefinition 序列化为字典（用于审计日志的 after 快照）
    def _definition_payload(self, definition: SceneDefinition) -> dict[str, Any]:
        return definition.model_dump(mode="json")

    # 从场景主表行提取关键字段作为审计日志的 before/after 快照
    def _scene_row_payload(self, row: DataFactorySceneRow) -> dict[str, Any]:
        return {
            "sceneCode": row.scene_code,
            "sceneName": row.scene_name,
            "sceneRemark": row.scene_remark,
            "sceneType": row.scene_type,
            "status": row.status,
            "currentVersionNo": row.current_version_no,
        }

    # 写入审计日志记录，追踪所有配置变更的操作轨迹
    def _add_audit(
        self,
        session: AsyncSession,
        target_type: str,
        target_id: str,
        action: str,
        operator: str | None,
        before: Any,
        after: Any,
    ) -> None:
        session.add(
            DataFactoryConfigAuditRow(
                id=_new_id(),
                target_type=target_type,
                target_id=target_id,
                action=action,
                operator=operator,
                before_json=_dumps(before) if before is not None else None,
                after_json=_dumps(after) if after is not None else None,
                created_at=_now(),
            )
        )
