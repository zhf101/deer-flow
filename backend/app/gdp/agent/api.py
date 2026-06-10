"""GDP Agent 场景设计接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.gdp.agent.middlewares.business_guardrail import GDPToolApprovalContext
from app.gdp.agent.tools.infra_config_tools import (
    resolve_infra_basis,
    upsert_datasource_from_agent,
    upsert_environment_from_agent,
    upsert_service_endpoint_from_agent,
    upsert_system_from_agent,
)
from app.gdp.agent.tools.registry import assert_gdp_registered_tool_allowed
from app.gdp.agent.tools.scene_design_tools import compose_scene_draft_from_source, publish_scene_from_source
from app.gdp.agent.tools.source_config_tools import (
    parse_sql_source_from_agent,
    resolve_http_source_basis,
    resolve_sql_source_basis,
    test_http_source_from_agent,
    test_sql_source_from_agent,
    upsert_http_source_from_agent,
    upsert_sql_source_from_agent,
)
from app.gdp.datagen.agent_catalog.models import AgentSourceContract
from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    EnvironmentConfig,
    ServiceEndpointConfig,
    SysConfig,
)
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig, HttpSourceTestRequest
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.models import SceneDefinition, ValidationResult
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.scene.validation import validate_scene_publish
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig, SqlSourceParseRequest
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.runtime.sql.models import SqlSourceTestRequest
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-agent"])


class AgentSceneDraftRequest(BaseModel):
    """Agent 生成场景草稿请求。"""

    taskRunId: str = Field(..., min_length=1, description="造数任务运行 ID，用于生成稳定场景编码和记录来源。")
    goal: str = Field(..., min_length=1, description="当前缺失场景或用户造数目标。")
    sourceContract: AgentSourceContract = Field(..., description="用于生成场景的 Source 能力契约。")


class AgentSceneDraftResponse(BaseModel):
    """Agent 生成场景草稿响应。"""

    definition: SceneDefinition = Field(..., description="生成的场景草稿定义。")


class AgentSceneValidateRequest(BaseModel):
    """Agent 校验场景草稿请求。"""

    definition: SceneDefinition = Field(..., description="待校验的场景定义。")


class AgentScenePublishRequest(BaseModel):
    """Agent 基于 Source 自动发布场景请求。"""

    taskRunId: str = Field(..., min_length=1, description="造数任务运行 ID，发布过程会写入任务事件。")
    goal: str = Field(..., min_length=1, description="当前缺失场景或用户造数目标。")
    sourceContract: AgentSourceContract = Field(..., description="用于生成并发布场景的 Source 能力契约。")


class AgentScenePublishResponse(BaseModel):
    """Agent 自动发布场景响应。"""

    sceneCode: str = Field(..., description="已发布场景编码。")
    versionNo: int = Field(..., description="已发布场景版本号。")
    definition: SceneDefinition = Field(..., description="已发布场景定义。")


class AgentHttpBasisRequest(BaseModel):
    """Agent HTTP Source 基础配置解析请求。"""

    sysCode: str = Field(..., min_length=1, description="HTTP Source 所属系统编码。")
    envCode: str = Field(..., min_length=1, description="目标环境编码。")


class AgentSqlBasisRequest(BaseModel):
    """Agent SQL Source 基础配置解析请求。"""

    sysCode: str = Field(..., min_length=1, description="SQL Source 所属系统编码。")
    envCode: str = Field(..., min_length=1, description="目标环境编码。")
    datasourceCode: str = Field(..., min_length=1, description="SQL Source 引用的数据源编码。")


class AgentHttpSourceUpsertRequest(BaseModel):
    """Agent 保存 HTTP Source 请求。"""

    envCode: str = Field(..., min_length=1, description="目标环境编码，用于保存前检查服务端点是否齐备。")
    config: HttpSourceConfig = Field(..., description="待保存的 HTTP Source 配置。")


class AgentSqlSourceUpsertRequest(BaseModel):
    """Agent 保存 SQL Source 请求。"""

    envCode: str = Field(..., min_length=1, description="目标环境编码，用于保存前检查数据源是否齐备。")
    config: SqlSourceConfig = Field(..., description="待保存的 SQL Source 配置。")


class AgentInfraResolveRequest(BaseModel):
    """Agent 基础配置解析请求。"""

    query: str = Field(..., min_length=1, description="用户目标、系统线索或 Source 描述。")
    envCode: str = Field(default="DEV", min_length=1, description="目标环境编码。")
    sysCode: str | None = Field(default=None, description="已知系统编码。")
    datasourceCode: str | None = Field(default=None, description="SQL Source 已知数据源编码。")
    resourceType: str = Field(default="HTTP", description="目标资源类型，HTTP 或 SQL。")


class AgentSystemUpsertRequest(BaseModel):
    """Agent 保存系统基础配置请求。"""

    config: SysConfig = Field(..., description="系统基础配置。")


class AgentEnvironmentUpsertRequest(BaseModel):
    """Agent 保存环境基础配置请求。"""

    config: EnvironmentConfig = Field(..., description="环境基础配置。")


class AgentServiceEndpointUpsertRequest(BaseModel):
    """Agent 保存 HTTP 服务端点基础配置请求。"""

    config: ServiceEndpointConfig = Field(..., description="服务端点基础配置。")


class AgentDatasourceUpsertRequest(BaseModel):
    """Agent 保存数据源基础配置请求。"""

    config: DatasourceConfig = Field(..., description="数据源基础配置。")


class _AgentSceneDesignServices(BaseModel):
    """Agent 设计和配置接口依赖集合。"""

    model_config = {"arbitrary_types_allowed": True}

    base_repository: BaseConfigRepository = Field(..., description="基础配置仓储，用于读取系统、环境、端点和数据源。")
    task_service: DatagenTaskService = Field(..., description="造数任务服务，用于发布场景时写入任务事件。")
    scene_service: SceneService = Field(..., description="场景配置服务，用于校验、保存和发布场景定义。")
    http_source_service: HttpSourceService = Field(..., description="HTTP Source 服务，用于保存和测试 HTTP 数据源配置。")
    sql_source_service: SqlSourceService = Field(..., description="SQL Source 服务，用于保存 SQL 数据源配置。")
    sql_execution_service: SqlExecutionService = Field(..., description="SQL 执行服务，用于测试 SQL Source 查询。")
    http_source_repository: HttpSourceRepository = Field(..., description="HTTP Source 仓储，用于场景生成时读取已发布 Source。")
    sql_source_repository: SqlSourceRepository = Field(..., description="SQL Source 仓储，用于场景生成时读取已发布 Source。")


def _get_services() -> _AgentSceneDesignServices:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    base_repository = BaseConfigRepository(sf)
    scene_repository = SceneRepository(sf)
    http_source_repository = HttpSourceRepository(sf)
    sql_source_repository = SqlSourceRepository(sf)
    return _AgentSceneDesignServices(
        base_repository=base_repository,
        task_service=DatagenTaskService(DatagenTaskRepository(sf)),
        scene_service=SceneService(scene_repository),
        http_source_service=HttpSourceService(http_source_repository, base_repository),
        sql_source_service=SqlSourceService(sql_source_repository, base_repository),
        sql_execution_service=SqlExecutionService(
            base_repository=base_repository,
            sql_source_repository=sql_source_repository,
            registry=SqlExecutorRegistry(),
        ),
        http_source_repository=http_source_repository,
        sql_source_repository=sql_source_repository,
    )


@router.post("/agent/scenes/draft", response_model=AgentSceneDraftResponse)
async def draft_scene_from_source(
    body: AgentSceneDraftRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> AgentSceneDraftResponse:
    definition = await compose_scene_draft_from_source(
        task_run_id=body.taskRunId,
        goal=body.goal,
        source_contract=_source_contract_payload(body.sourceContract),
        http_source_repository=services.http_source_repository,
        sql_source_repository=services.sql_source_repository,
    )
    return AgentSceneDraftResponse(definition=definition)


@router.post("/agent/scenes/validate", response_model=ValidationResult)
async def validate_agent_scene(body: AgentSceneValidateRequest) -> ValidationResult:
    return validate_scene_publish(body.definition)


@router.post("/agent/scenes/publish", response_model=AgentScenePublishResponse)
async def publish_scene_from_source_api(
    body: AgentScenePublishRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> AgentScenePublishResponse:
    source_contract = _source_contract_payload(body.sourceContract)
    _assert_agent_api_config_write_allowed(
        "publish_scene_from_source",
        {"task_run_id": body.taskRunId, "source_contract": source_contract},
    )
    result = await publish_scene_from_source(
        task_service=services.task_service,
        scene_service=services.scene_service,
        http_source_repository=services.http_source_repository,
        sql_source_repository=services.sql_source_repository,
        task_run_id=body.taskRunId,
        goal=body.goal,
        source_contract=source_contract,
    )
    return AgentScenePublishResponse(**result)


@router.post("/agent/sources/http/basis", response_model=dict[str, Any])
async def resolve_http_source_basis_api(
    body: AgentHttpBasisRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    return await resolve_http_source_basis(services.base_repository, sys_code=body.sysCode, env_code=body.envCode)


@router.post("/agent/sources/sql/basis", response_model=dict[str, Any])
async def resolve_sql_source_basis_api(
    body: AgentSqlBasisRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    return await resolve_sql_source_basis(
        services.base_repository,
        sys_code=body.sysCode,
        env_code=body.envCode,
        datasource_code=body.datasourceCode,
    )


@router.post("/agent/sources/http/upsert", response_model=dict[str, Any])
async def upsert_http_source_api(
    body: AgentHttpSourceUpsertRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_config_write_allowed("upsert_http_source_from_agent", {"config": body.config})
    return await upsert_http_source_from_agent(
        services.http_source_service,
        services.base_repository,
        config=body.config,
        env_code=body.envCode,
    )


@router.post("/agent/sources/sql/parse", response_model=dict[str, Any])
async def parse_sql_source_api(body: SqlSourceParseRequest) -> dict[str, Any]:
    return parse_sql_source_from_agent(body)


@router.post("/agent/sources/sql/upsert", response_model=dict[str, Any])
async def upsert_sql_source_api(
    body: AgentSqlSourceUpsertRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_config_write_allowed("upsert_sql_source_from_agent", {"config": body.config})
    return await upsert_sql_source_from_agent(
        services.sql_source_service,
        services.base_repository,
        config=body.config,
        env_code=body.envCode,
    )


@router.post("/agent/sources/http/test", response_model=dict[str, Any])
async def test_http_source_api(
    body: HttpSourceTestRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_business_write_allowed("test_http_source_from_agent", {"request": body})
    return await test_http_source_from_agent(services.http_source_service, request=body)


@router.post("/agent/sources/sql/test", response_model=dict[str, Any])
async def test_sql_source_api(
    body: SqlSourceTestRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_business_write_allowed("test_sql_source_from_agent", {"request": body})
    return await test_sql_source_from_agent(services.sql_execution_service, request=body)


@router.post("/agent/infra/resolve", response_model=dict[str, Any])
async def resolve_infra_basis_api(
    body: AgentInfraResolveRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    return await resolve_infra_basis(
        services.base_repository,
        query=body.query,
        env_code=body.envCode,
        sys_code=body.sysCode,
        datasource_code=body.datasourceCode,
        resource_type=body.resourceType,
    )


@router.post("/agent/infra/systems/upsert", response_model=dict[str, Any])
async def upsert_system_api(
    body: AgentSystemUpsertRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_config_write_allowed("upsert_system_from_agent", {"config": body.config})
    return await upsert_system_from_agent(services.base_repository, config=body.config)


@router.post("/agent/infra/environments/upsert", response_model=dict[str, Any])
async def upsert_environment_api(
    body: AgentEnvironmentUpsertRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_config_write_allowed("upsert_environment_from_agent", {"config": body.config})
    return await upsert_environment_from_agent(services.base_repository, config=body.config)


@router.post("/agent/infra/service-endpoints/upsert", response_model=dict[str, Any])
async def upsert_service_endpoint_api(
    body: AgentServiceEndpointUpsertRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_config_write_allowed("upsert_service_endpoint_from_agent", {"config": body.config})
    return await upsert_service_endpoint_from_agent(services.base_repository, config=body.config)


@router.post("/agent/infra/datasources/upsert", response_model=dict[str, Any])
async def upsert_datasource_api(
    body: AgentDatasourceUpsertRequest,
    services: _AgentSceneDesignServices = Depends(_get_services),
) -> dict[str, Any]:
    _assert_agent_api_config_write_allowed("upsert_datasource_from_agent", {"config": body.config})
    return await upsert_datasource_from_agent(services.base_repository, config=body.config)


def _source_contract_payload(contract: AgentSourceContract) -> dict[str, Any]:
    return contract.model_dump(mode="json")


def _assert_agent_api_config_write_allowed(tool_name: str, tool_input: dict[str, Any]) -> None:
    assert_gdp_registered_tool_allowed(
        tool_name,
        tool_input,
        GDPToolApprovalContext(
            allowConfigWrite=True,
            reason="用户通过 Agent API 显式提交配置写入请求。",
        ),
    )


def _assert_agent_api_business_write_allowed(tool_name: str, tool_input: dict[str, Any]) -> None:
    assert_gdp_registered_tool_allowed(
        tool_name,
        tool_input,
        GDPToolApprovalContext(
            allowBusinessWrite=True,
            reason="用户通过 Agent API 显式提交业务探测请求。",
        ),
    )
