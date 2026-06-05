"""GDP 造数工厂业务逻辑层。封装场景、环境、数据源、SQL模板等配置的业务操作。

本模块是路由层与持久化仓储之间的中间层，负责：
- 在写入前执行静态校验（草稿校验 / 发布校验）；
- 将仓储层抛出的 NotFound / Conflict 异常转换为 HTTP 状态码；
- 协调多个仓储调用以完成复合业务操作（如发布场景需要同时读取场景与 SQL 模板）。
"""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.models import (
    ConfigStatus,
    DatasourceConfig,
    DatasourceResponse,
    DisableResponse,
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
)
from app.gdp.persistence.repository import (
    DataFactoryConflictError,
    DataFactoryNotFoundError,
    DataFactoryRepository,
)
from app.gdp.validation import validate_draft, validate_publish


# 造数工厂核心业务服务类，聚合全部业务操作
class DataFactoryService:
    def __init__(self, repository: DataFactoryRepository) -> None:
        self._repo = repository

    # ---------- 场景管理 ----------

    # 分页查询场景摘要，支持按类型、状态、关键字过滤
    async def list_scenes(
        self,
        *,
        scene_type: str | None = None,
        status: SceneStatus | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SceneSummary]:
        return await self._repo.list_scenes(scene_type=scene_type, status=status, keyword=keyword, limit=limit, offset=offset)

    # 新建场景：先做草稿校验，通过后写入主表和首版版本记录
    async def create_scene(self, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        result = validate_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._repo.create_scene(definition, operator=operator))

    # 更新场景：草稿校验通过后生成新版本，状态回退为 DRAFT
    async def update_scene(self, scene_code: str, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        result = validate_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._repo.update_scene(scene_code, definition, operator=operator))

    # 获取场景完整定义（含最新版本的全部配置）
    async def get_scene(self, scene_code: str) -> SceneDefinition:
        return await self._guard(lambda: self._repo.get_scene_definition(scene_code))

    # 对已保存场景执行发布前校验（只读操作，不修改状态）
    async def validate_scene(self, scene_code: str) -> ValidationResult:
        scene = await self._guard(lambda: self._repo.validate_scene_saved(scene_code))
        # 加载所有已启用的 SQL 模板，供校验步骤中的模板引用检查使用
        templates = await self._enabled_templates_by_code()
        return validate_publish(scene, sql_templates_by_code=templates)

    # 发布场景：完整校验通过后将最新草稿版本标记为 PUBLISHED
    async def publish_scene(self, scene_code: str, *, operator: str | None = None) -> SceneVersion:
        scene = await self._guard(lambda: self._repo.get_scene_definition(scene_code))
        # 加载启用的 SQL 模板映射，用于校验 SQL 步骤的参数完整性
        templates = await self._enabled_templates_by_code()
        result = validate_publish(scene, sql_templates_by_code=templates)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._repo.publish_scene(scene_code, result, operator=operator))

    # 禁用场景（逻辑禁用，不删除数据）
    async def disable_scene(self, scene_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_scene(scene_code, operator=operator))
        return DisableResponse(success=True)

    # 物理删除场景及其全部版本
    async def delete_scene(self, scene_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_scene(scene_code, operator=operator))
        return DisableResponse(success=True)

    # 复制场景：以源场景最新版本为蓝本创建新草稿
    async def copy_scene(self, scene_code: str, target_scene_code: str, *, operator: str | None = None) -> SceneVersion:
        return await self._guard(lambda: self._repo.copy_scene(scene_code, target_scene_code, operator=operator))

    # 查询场景的全部版本历史
    async def list_scene_versions(self, scene_code: str) -> list[SceneVersion]:
        return await self._guard(lambda: self._repo.list_scene_versions(scene_code))

    # 获取场景的指定版本快照
    async def get_scene_version(self, scene_code: str, version_no: int) -> SceneVersion:
        return await self._guard(lambda: self._repo.get_scene_version(scene_code, version_no))

    # ---------- 环境管理 ----------

    # 查询全部环境配置
    async def list_environments(self) -> list[EnvironmentResponse]:
        return await self._repo.list_environments()

    # 新建或更新环境（Upsert）
    async def upsert_environment(self, config: EnvironmentConfig) -> EnvironmentResponse:
        return await self._guard(lambda: self._repo.upsert_environment(config))

    # ---------- 服务端点管理 ----------

    # 查询服务端点列表，可按环境过滤
    async def list_service_endpoints(self, *, env_code: str | None = None) -> list[ServiceEndpointResponse]:
        return await self._repo.list_service_endpoints(env_code=env_code)

    # 新建服务端点
    async def create_service_endpoint(self, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.create_service_endpoint(config))

    # 更新服务端点
    async def update_service_endpoint(self, endpoint_id: str, config: ServiceEndpointConfig) -> ServiceEndpointResponse:
        return await self._guard(lambda: self._repo.update_service_endpoint(endpoint_id, config))

    # ---------- 数据源管理 ----------

    # 查询数据源列表，可按环境过滤
    async def list_datasources(self, *, env_code: str | None = None) -> list[DatasourceResponse]:
        return await self._repo.list_datasources(env_code=env_code)

    # 新建数据源
    async def create_datasource(self, config: DatasourceConfig) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.create_datasource(config))

    # 更新数据源
    async def update_datasource(self, datasource_id: str, config: DatasourceConfig) -> DatasourceResponse:
        return await self._guard(lambda: self._repo.update_datasource(datasource_id, config))

    # ---------- 删除操作 ----------

    # 物理删除环境配置
    async def delete_environment(self, env_code: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_environment(env_code))
        return DisableResponse(success=True)

    # 物理删除服务端点
    async def delete_service_endpoint(self, endpoint_id: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_service_endpoint(endpoint_id))
        return DisableResponse(success=True)

    # 物理删除数据源
    async def delete_datasource(self, datasource_id: str) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_datasource(datasource_id))
        return DisableResponse(success=True)

    # ---------- SQL 模板管理 ----------

    # 查询全部 SQL 模板列表
    async def list_sql_templates(self) -> list[SqlTemplateResponse]:
        return await self._repo.list_sql_templates()

    # 新建 SQL 模板（Upsert 语义）
    async def create_sql_template(self, template: SqlTemplateConfig, *, operator: str | None = None) -> SqlTemplateResponse:
        return await self._guard(lambda: self._repo.upsert_sql_template(template, operator=operator))

    # 获取指定 SQL 模板详情
    async def get_sql_template(self, template_code: str) -> SqlTemplateResponse:
        return await self._guard(lambda: self._repo.get_sql_template(template_code))

    # 更新 SQL 模板，路径参数与请求体中的 templateCode 必须一致
    async def update_sql_template(
        self,
        template_code: str,
        template: SqlTemplateConfig,
        *,
        operator: str | None = None,
    ) -> SqlTemplateResponse:
        if template_code != template.templateCode:
            raise HTTPException(status_code=409, detail="path templateCode must match request templateCode")
        return await self._guard(lambda: self._repo.upsert_sql_template(template, operator=operator))

    # 禁用 SQL 模板
    async def disable_sql_template(self, template_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_sql_template(template_code, operator=operator))
        return DisableResponse(success=True)

    # ---------- 场景执行 ----------

    # 执行已发布的造数场景——加载配置、校验输入、逐步执行并返回结果
    async def run_scene(self, scene_code: str, request: "ExecutionRequest") -> "ExecutionResult":
        """执行已发布的场景。

        调用执行引擎加载已发布版本，校验输入参数，按顺序执行各步骤，
        最终解析 resultMapping 返回造数结果。
        """
        from app.gdp.engine.executor import SceneExecutor
        from app.gdp.engine.models import ExecutionRequest, ExecutionResult  # noqa: F811

        executor = SceneExecutor(self._repo._sf)
        return await executor.execute(scene_code, request)

    # ---------- 内部辅助方法 ----------

    # 获取所有已启用 SQL 模板的 code -> config 映射，供发布校验使用
    async def _enabled_templates_by_code(self) -> dict[str, SqlTemplateConfig]:
        templates = await self._repo.list_sql_templates(status=ConfigStatus.ENABLED)
        return {
            template.templateCode: SqlTemplateConfig.model_validate(template.model_dump(mode="json"))
            for template in templates
        }

    # 统一异常守卫：将仓储层的 NotFound / Conflict 异常转换为对应的 HTTP 状态码
    async def _guard(self, call):
        try:
            return await call()
        except DataFactoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DataFactoryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
