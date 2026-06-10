"""GDP Agent 配置写入幂等测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent.middlewares.idempotency import find_successful_infra_config_step, find_successful_source_config_step
from app.gdp.agent.nodes.infra_config import build_infra_config_node
from app.gdp.agent.nodes.source_config import build_source_config_node
from app.gdp.datagen.config.base.models import EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, InputFieldDefinition, InputFieldType
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest, DatagenTaskStepStatus, DatagenTaskStepType
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def config_services(tmp_path):
    db_path = tmp_path / "gdp-config-idempotency.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        base_repo = BaseConfigRepository(session_factory)
        http_repo = HttpSourceRepository(session_factory)
        sql_repo = SqlSourceRepository(session_factory)
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        yield {
            "base_repo": base_repo,
            "task_service": task_service,
            "http_service": HttpSourceService(http_repo, base_repo),
            "sql_service": SqlSourceService(sql_repo, base_repo),
            "sql_execution": SqlExecutionService(
                base_repository=base_repo,
                sql_source_repository=sql_repo,
                registry=SqlExecutorRegistry(),
            ),
        }
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_source_config_node_reuses_successful_same_payload_step(config_services):
    await _create_http_basis(config_services["base_repo"])
    task_run = await config_services["task_service"].create_task_run(DatagenTaskRunCreateRequest(userIntent="帮我造订单"))
    source_payload = {"sourceType": "HTTP", "config": _order_http_source().model_dump(mode="json")}
    node = build_source_config_node(
        task_service=config_services["task_service"],
        base_repository=config_services["base_repo"],
        http_source_service=config_services["http_service"],
        sql_source_service=config_services["sql_service"],
    )

    first = await node({"task_run_id": task_run.taskRunId, "user_inputs": source_payload})
    second = await node({"task_run_id": task_run.taskRunId, "user_inputs": source_payload})

    assert first["current_phase"] == "SCENE_DESIGN"
    assert second["decision_context"]["sourceConfigResult"]["idempotentReuse"] is True
    steps = await config_services["task_service"].list_steps(task_run.taskRunId)
    source_steps = [step for step in steps if step.stepType == DatagenTaskStepType.CONFIG_HTTP_SOURCE]
    assert len(source_steps) == 1
    assert find_successful_source_config_step(steps, source_payload=source_payload) == source_steps[0]
    events = await config_services["task_service"].list_events(task_run.taskRunId)
    assert [event.eventType for event in events].count("SOURCE_CONFIG_SAVED") == 1
    assert [event.eventType for event in events].count("SOURCE_CONFIG_REUSED") == 1


@pytest.mark.anyio
async def test_infra_config_node_reuses_successful_same_payload_step(config_services):
    task_run = await config_services["task_service"].create_task_run(DatagenTaskRunCreateRequest(userIntent="补齐基础配置"))
    infra_payload = {
        "system": SysConfig(sysCode="TRADE", sysName="交易系统").model_dump(mode="json"),
        "environment": EnvironmentConfig(envCode="DEV", envName="开发环境").model_dump(mode="json"),
        "serviceEndpoint": ServiceEndpointConfig(
            envCode="DEV",
            sysCode="TRADE",
            baseUrl="http://trade-dev.example",
        ).model_dump(mode="json"),
    }
    node = build_infra_config_node(
        task_service=config_services["task_service"],
        base_repository=config_services["base_repo"],
    )

    first = await node({"task_run_id": task_run.taskRunId, "user_inputs": {"infra": infra_payload}})
    second = await node({"task_run_id": task_run.taskRunId, "user_inputs": {"infra": infra_payload}})

    assert first["current_phase"] == "SOURCE_CONFIG"
    assert second["decision_context"]["infraConfigResult"]["idempotentReuse"] is True
    steps = await config_services["task_service"].list_steps(task_run.taskRunId)
    infra_steps = [step for step in steps if step.stepType == DatagenTaskStepType.CONFIG_INFRA]
    assert len(infra_steps) == 1
    assert infra_steps[0].status == DatagenTaskStepStatus.SUCCESS
    assert find_successful_infra_config_step(steps, infra_payload=infra_payload) == infra_steps[0]
    events = await config_services["task_service"].list_events(task_run.taskRunId)
    assert [event.eventType for event in events].count("INFRA_CONFIG_SAVED") == 1
    assert [event.eventType for event in events].count("INFRA_CONFIG_REUSED") == 1


async def _create_http_basis(base_repo: BaseConfigRepository) -> None:
    await base_repo.upsert_system(SysConfig(sysCode="TRADE", sysName="交易系统"))
    await base_repo.upsert_environment(EnvironmentConfig(envCode="DEV", envName="开发环境"))
    await base_repo.create_service_endpoint(
        ServiceEndpointConfig(envCode="DEV", sysCode="TRADE", baseUrl="http://trade-dev.example")
    )


def _order_http_source() -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode="createOrderApi",
        sourceName="创建订单接口",
        tags=["订单", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[{"effectType": "CREATE_ORDER", "target": "orders"}],
        agentDescription="创建一笔测试订单，返回订单号。",
        sysCode="TRADE",
        path="/orders",
        method=HttpMethod.POST,
        bodySchema=[
            InputFieldDefinition(
                name="userId",
                label="用户",
                type=InputFieldType.STRING,
                semanticType="USER_ID",
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        status=ConfigStatus.ENABLED,
    )
