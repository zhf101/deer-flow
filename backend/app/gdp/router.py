"""GDP 造数工厂 FastAPI 路由层。

定义造数工厂对外暴露的全部 RESTful 接口，包括场景（Scene）的增删改查、
发布/禁用/复制、版本管理，以及环境、服务端点、数据源、SQL 模板等
基础配置资源的 CRUD 操作。所有接口统一挂载在 ``/api/v1/data-factory`` 前缀下。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.engine.models import ExecutionRequest, ExecutionResult
from app.gdp.models import (
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
from app.gdp.persistence.repository import DataFactoryRepository
from app.gdp.service import DataFactoryService
from deerflow.persistence.engine import get_session_factory

# 创建造数工厂路由，统一前缀和 OpenAPI 标签
router = APIRouter(prefix="/api/v1/data-factory", tags=["data-factory"])


def get_data_factory_service() -> DataFactoryService:
    """依赖注入：构造 DataFactoryService 实例。

    从全局获取异步 Session 工厂，若持久化层尚未就绪则返回 503，
    否则创建仓储并注入到业务服务中。
    """
    session_factory = get_session_factory()
    if session_factory is None:
        raise HTTPException(status_code=503, detail="Data factory persistence not available")
    return DataFactoryService(DataFactoryRepository(session_factory))


async def get_operator(request: Request) -> str | None:
    """依赖注入：从请求上下文中提取当前操作人标识。

    用于审计日志记录，获取不到时返回 None 而不阻断请求。
    """
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


# ========================= 场景（Scene）接口 =========================


@router.get("/scenes", response_model=list[SceneSummary])
async def list_scenes(
    scene_type: str | None = Query(default=None, alias="sceneType"),
    status: SceneStatus | None = None,
    keyword: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[SceneSummary]:
    """分页查询场景摘要列表。

    支持按场景类型（sceneType）、状态（status）和关键字（keyword）过滤，
    关键字同时匹配 scene_code 和 scene_name。
    """
    return await service.list_scenes(scene_type=scene_type, status=status, keyword=keyword, limit=limit, offset=offset)


@router.post("/scenes", response_model=SceneVersion)
async def create_scene(
    body: SceneDefinition,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    """新建造数场景。

    先执行草稿态静态校验，校验不通过返回 422；
    校验通过后持久化场景主记录和首个版本记录。
    """
    return await service.create_scene(body, operator=operator)


@router.get("/scenes/{sceneCode}", response_model=SceneDefinition)
async def get_scene(
    sceneCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneDefinition:
    """根据场景编码获取场景完整定义（含最新版本配置详情）。"""
    return await service.get_scene(sceneCode)


@router.put("/scenes/{sceneCode}", response_model=SceneVersion)
async def update_scene(
    sceneCode: str,
    body: SceneDefinition,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    """更新造数场景，生成新的草稿版本。

    路径参数 sceneCode 必须与请求体中的 sceneCode 一致；
    每次更新都会递增版本号并保留历史快照。
    """
    return await service.update_scene(sceneCode, body, operator=operator)


@router.post("/scenes/{sceneCode}/validate", response_model=ValidationResult)
async def validate_scene(
    sceneCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ValidationResult:
    """对已保存的场景执行发布前校验（仅校验，不改变状态）。

    校验内容包括基础结构、环境变量、步骤引用合法性、SQL 模板参数匹配等。
    """
    return await service.validate_scene(sceneCode)


@router.post("/scenes/{sceneCode}/publish", response_model=SceneVersion)
async def publish_scene(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    """发布场景：先执行完整校验，通过后把最新草稿版本标记为已发布。

    发布后场景状态变为 PUBLISHED，可被造数引擎调用执行。
    """
    return await service.publish_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/run")
async def run_scene(
    sceneCode: str,
    body: ExecutionRequest,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ExecutionResult:
    """执行已发布的造数场景。

    接收环境编码和输入参数，加载已发布的场景配置，逐步执行 HTTP/SQL/断言/转换
    步骤，最终返回包含各步骤结果和最终输出的执行报告。
    """
    return await service.run_scene(sceneCode, body)


@router.post("/scenes/{sceneCode}/disable", response_model=DisableResponse)
async def disable_scene(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """禁用场景：将状态设为 DISABLED，不删除数据，可随时重新启用。"""
    return await service.disable_scene(sceneCode, operator=operator)


@router.delete("/scenes/{sceneCode}", response_model=DisableResponse)
async def delete_scene(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """物理删除场景及其全部版本记录（RESTful DELETE 语义）。"""
    return await service.delete_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/delete", response_model=DisableResponse)
async def delete_scene_post(
    sceneCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """物理删除场景（POST 兼容方式）。

    某些前端/网关环境不便发送 DELETE 请求，因此额外提供 POST 方式完成同样的删除操作。
    """
    return await service.delete_scene(sceneCode, operator=operator)


@router.post("/scenes/{sceneCode}/copy", response_model=SceneVersion)
async def copy_scene(
    sceneCode: str,
    targetSceneCode: str = Query(..., alias="targetSceneCode"),
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    """复制场景：以源场景最新版本为蓝本，在目标编码下创建一份新的草稿副本。"""
    return await service.copy_scene(sceneCode, targetSceneCode, operator=operator)


# ========================= 场景版本接口 =========================


@router.get("/scenes/{sceneCode}/versions", response_model=list[SceneVersion])
async def list_scene_versions(
    sceneCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[SceneVersion]:
    """查询指定场景的全部版本记录，按版本号降序排列。"""
    return await service.list_scene_versions(sceneCode)


@router.get("/scenes/{sceneCode}/versions/{versionNo}", response_model=SceneVersion)
async def get_scene_version(
    sceneCode: str,
    versionNo: int,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SceneVersion:
    """获取场景的指定版本详情，用于版本回溯或对比。"""
    return await service.get_scene_version(sceneCode, versionNo)


# ========================= 环境（Environment）接口 =========================


@router.get("/environments", response_model=list[EnvironmentResponse])
async def list_environments(
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[EnvironmentResponse]:
    """查询全部环境配置列表（如 DEV / SIT / PROD 等）。"""
    return await service.list_environments()


@router.post("/environments", response_model=EnvironmentResponse)
async def create_environment(
    body: EnvironmentConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> EnvironmentResponse:
    """新建或更新环境配置（Upsert 语义），以 envCode 为唯一键。"""
    return await service.upsert_environment(body)


@router.put("/environments/{envCode}", response_model=EnvironmentResponse)
async def update_environment(
    envCode: str,
    body: EnvironmentConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> EnvironmentResponse:
    """更新已有环境配置。路径参数 envCode 必须与请求体中的一致，否则返回 409。"""
    if envCode != body.envCode:
        raise HTTPException(status_code=409, detail="path envCode must match request envCode")
    return await service.upsert_environment(body)


@router.delete("/environments/{envCode}", response_model=DisableResponse)
async def delete_environment(
    envCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """物理删除指定环境配置。"""
    return await service.delete_environment(envCode)


# ========================= 服务端点（Service Endpoint）接口 =========================


@router.get("/service-endpoints", response_model=list[ServiceEndpointResponse])
async def list_service_endpoints(
    env_code: str | None = Query(default=None, alias="envCode"),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[ServiceEndpointResponse]:
    """查询服务端点列表，可按环境编码过滤。"""
    return await service.list_service_endpoints(env_code=env_code)


@router.post("/service-endpoints", response_model=ServiceEndpointResponse)
async def create_service_endpoint(
    body: ServiceEndpointConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ServiceEndpointResponse:
    """新建服务端点（同一环境下 serviceCode 唯一）。"""
    return await service.create_service_endpoint(body)


@router.put("/service-endpoints/{endpointId}", response_model=ServiceEndpointResponse)
async def update_service_endpoint(
    endpointId: str,
    body: ServiceEndpointConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> ServiceEndpointResponse:
    """根据端点 ID 更新服务端点配置。"""
    return await service.update_service_endpoint(endpointId, body)


@router.delete("/service-endpoints/{endpointId}", response_model=DisableResponse)
async def delete_service_endpoint(
    endpointId: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """物理删除指定服务端点。"""
    return await service.delete_service_endpoint(endpointId)


# ========================= 数据源（Datasource）接口 =========================


@router.get("/datasources", response_model=list[DatasourceResponse])
async def list_datasources(
    env_code: str | None = Query(default=None, alias="envCode"),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[DatasourceResponse]:
    """查询数据源列表，可按环境编码过滤。"""
    return await service.list_datasources(env_code=env_code)


@router.post("/datasources", response_model=DatasourceResponse)
async def create_datasource(
    body: DatasourceConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DatasourceResponse:
    """新建数据源配置（同一环境下 datasourceCode 唯一）。"""
    return await service.create_datasource(body)


@router.put("/datasources/{datasourceId}", response_model=DatasourceResponse)
async def update_datasource(
    datasourceId: str,
    body: DatasourceConfig,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DatasourceResponse:
    """根据数据源 ID 更新数据源配置。"""
    return await service.update_datasource(datasourceId, body)


@router.delete("/datasources/{datasourceId}", response_model=DisableResponse)
async def delete_datasource(
    datasourceId: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """物理删除指定数据源配置。"""
    return await service.delete_datasource(datasourceId)


# ========================= SQL 模板（SQL Template）接口 =========================


@router.get("/sql-templates", response_model=list[SqlTemplateResponse])
async def list_sql_templates(
    service: DataFactoryService = Depends(get_data_factory_service),
) -> list[SqlTemplateResponse]:
    """查询全部 SQL 模板列表，按更新时间降序排列。"""
    return await service.list_sql_templates()


@router.post("/sql-templates", response_model=SqlTemplateResponse)
async def create_sql_template(
    body: SqlTemplateConfig,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SqlTemplateResponse:
    """新建 SQL 模板（Upsert 语义），以 templateCode 为唯一键。"""
    return await service.create_sql_template(body, operator=operator)


@router.get("/sql-templates/{templateCode}", response_model=SqlTemplateResponse)
async def get_sql_template(
    templateCode: str,
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SqlTemplateResponse:
    """根据模板编码获取 SQL 模板详情。"""
    return await service.get_sql_template(templateCode)


@router.put("/sql-templates/{templateCode}", response_model=SqlTemplateResponse)
async def update_sql_template(
    templateCode: str,
    body: SqlTemplateConfig,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> SqlTemplateResponse:
    """更新 SQL 模板。路径参数 templateCode 必须与请求体中的一致。"""
    return await service.update_sql_template(templateCode, body, operator=operator)


@router.post("/sql-templates/{templateCode}/disable", response_model=DisableResponse)
async def disable_sql_template(
    templateCode: str,
    operator: str | None = Depends(get_operator),
    service: DataFactoryService = Depends(get_data_factory_service),
) -> DisableResponse:
    """禁用 SQL 模板，禁用后引用该模板的场景将无法通过发布校验。"""
    return await service.disable_sql_template(templateCode, operator=operator)
