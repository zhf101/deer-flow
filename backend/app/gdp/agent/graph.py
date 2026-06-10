"""GDP 造数 Agent LangGraph 工厂。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.gdp.agent.middlewares.node_audit import wrap_gdp_node_audit
from app.gdp.agent.nodes.human_confirm import build_human_confirm_node
from app.gdp.agent.nodes.infra_config import build_infra_config_node
from app.gdp.agent.nodes.intake import build_intake_node
from app.gdp.agent.nodes.progress_reflection import build_progress_reflection_node
from app.gdp.agent.nodes.scene_design import build_scene_design_node
from app.gdp.agent.nodes.scene_execute import build_scene_execute_node
from app.gdp.agent.nodes.scene_fulfillment import build_scene_fulfillment_node
from app.gdp.agent.nodes.source_config import build_source_config_node
from app.gdp.agent.state import GDPState
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.agent_memory.repository import GDPAgentMemoryRepository
from app.gdp.datagen.agent_memory.service import GDPAgentMemoryService
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.executor import SceneExecutor
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_repository import DatagenTaskSubtaskRepository
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.config.app_config import AppConfig
from deerflow.persistence.engine import get_session_factory


@dataclass(frozen=True)
class GDPAgentServices:
    """GDP Agent 图运行依赖。"""

    task_service: DatagenTaskService
    catalog_service: AgentCatalogService
    scene_service: SceneService
    base_repository: BaseConfigRepository
    http_source_repository: HttpSourceRepository
    sql_source_repository: SqlSourceRepository
    http_source_service: HttpSourceService
    sql_source_service: SqlSourceService
    sql_execution_service: SqlExecutionService
    memory_service: GDPAgentMemoryService | None = None
    subtask_service: DatagenTaskSubtaskService | None = None


@dataclass(frozen=True)
class GDPAgentRuntimeConfig:
    """GDP Agent 本次运行的轻量配置。"""

    assistant_id: str
    thread_id: str | None
    run_id: str | None
    user_id: str | None
    operator: str | None
    model_name: str | None


@dataclass(frozen=True)
class GDPAgentPolicy:
    """GDP Agent 运行策略开关。"""

    audit_enabled: bool
    memory_enabled: bool
    checkpointer_enabled: bool


@dataclass(frozen=True)
class GDPAgentMetadata:
    """GDP Agent 图装配元数据。"""

    assistant_id: str
    thread_id: str | None
    run_id: str | None
    user_id: str | None
    model_name: str | None
    log_level: str | None
    policy: dict[str, Any]


def make_gdp_agent(config: RunnableConfig, app_config: AppConfig):
    """DeerFlow Runtime 调用的 GDP Agent 工厂。"""

    runtime = _get_gdp_runtime_config(config)
    policy = _build_gdp_policy(app_config)
    metadata = _build_gdp_metadata(app_config, runtime, policy)
    services = _build_services(app_config=app_config, runtime=runtime)
    return make_gdp_graph(
        services,
        runtime=runtime,
        policy=policy,
        metadata=metadata,
    )


def make_gdp_graph(
    services: GDPAgentServices,
    *,
    checkpointer=None,
    runtime: GDPAgentRuntimeConfig | None = None,
    policy: GDPAgentPolicy | None = None,
    metadata: GDPAgentMetadata | None = None,
):
    """构造 GDP 造数业务图。"""

    runtime = runtime or GDPAgentRuntimeConfig(
        assistant_id="gdp_agent",
        thread_id=None,
        run_id=None,
        user_id=None,
        operator=None,
        model_name=None,
    )
    policy = policy or GDPAgentPolicy(
        audit_enabled=True,
        memory_enabled=False,
        checkpointer_enabled=checkpointer is not None,
    )
    metadata = metadata or GDPAgentMetadata(
        assistant_id=runtime.assistant_id,
        thread_id=runtime.thread_id,
        run_id=runtime.run_id,
        user_id=runtime.user_id,
        model_name=runtime.model_name,
        log_level=None,
        policy={
            "auditEnabled": policy.audit_enabled,
            "memoryEnabled": policy.memory_enabled,
            "checkpointerEnabled": policy.checkpointer_enabled,
        },
    )

    workflow = StateGraph(GDPState)
    workflow.add_node(
        "intake",
        _wrap_node(
            "intake",
            build_intake_node(services.task_service, services.memory_service, services.subtask_service),
            services,
            policy,
            metadata,
        ),
    )
    workflow.add_node(
        "scene_fulfillment",
        _wrap_node(
            "scene_fulfillment",
            build_scene_fulfillment_node(
                catalog_service=services.catalog_service,
                task_service=services.task_service,
                scene_service=services.scene_service,
            ),
            services,
            policy,
            metadata,
        ),
    )
    workflow.add_node(
        "scene_design",
        _wrap_node(
            "scene_design",
            build_scene_design_node(
                catalog_service=services.catalog_service,
                task_service=services.task_service,
                scene_service=services.scene_service,
                http_source_repository=services.http_source_repository,
                sql_source_repository=services.sql_source_repository,
            ),
            services,
            policy,
            metadata,
        ),
    )
    workflow.add_node(
        "human_confirm",
        _wrap_node("human_confirm", build_human_confirm_node(services.task_service), services, policy, metadata),
    )
    workflow.add_node(
        "source_config",
        _wrap_node(
            "source_config",
            build_source_config_node(
                task_service=services.task_service,
                base_repository=services.base_repository,
                http_source_service=services.http_source_service,
                sql_source_service=services.sql_source_service,
            ),
            services,
            policy,
            metadata,
        ),
    )
    workflow.add_node(
        "infra_config",
        _wrap_node(
            "infra_config",
            build_infra_config_node(
                task_service=services.task_service,
                base_repository=services.base_repository,
            ),
            services,
            policy,
            metadata,
        ),
    )
    workflow.add_node(
        "scene_execute",
        _wrap_node(
            "scene_execute",
            build_scene_execute_node(
                catalog_service=services.catalog_service,
                task_service=services.task_service,
                scene_service=services.scene_service,
            ),
            services,
            policy,
            metadata,
        ),
    )
    workflow.add_node(
        "progress_reflection",
        _wrap_node(
            "progress_reflection",
            build_progress_reflection_node(services.task_service, services.subtask_service),
            services,
            policy,
            metadata,
        ),
    )

    workflow.add_edge(START, "intake")
    workflow.add_edge("intake", "scene_fulfillment")
    workflow.add_conditional_edges(
        "scene_fulfillment",
        _route_after_scene_fulfillment,
        {
            "human_confirm": "human_confirm",
            "scene_design": "scene_design",
            "source_config": "source_config",
            "progress_reflection": "progress_reflection",
        },
    )
    workflow.add_conditional_edges(
        "scene_design",
        _route_after_scene_design,
        {
            "scene_fulfillment": "scene_fulfillment",
            "source_config": "source_config",
            "human_confirm": "human_confirm",
            "progress_reflection": "progress_reflection",
        },
    )
    workflow.add_conditional_edges(
        "source_config",
        _route_after_source_config,
        {
            "scene_design": "scene_design",
            "infra_config": "infra_config",
            "human_confirm": "human_confirm",
            "progress_reflection": "progress_reflection",
        },
    )
    workflow.add_conditional_edges(
        "infra_config",
        _route_after_infra_config,
        {
            "source_config": "source_config",
            "human_confirm": "human_confirm",
            "progress_reflection": "progress_reflection",
        },
    )
    workflow.add_conditional_edges(
        "human_confirm",
        _route_after_human_confirm,
        {
            "scene_execute": "scene_execute",
            "scene_fulfillment": "scene_fulfillment",
            "scene_design": "scene_design",
            "source_config": "source_config",
            "infra_config": "infra_config",
            "progress_reflection": "progress_reflection",
        },
    )
    workflow.add_edge("scene_execute", "progress_reflection")
    workflow.add_conditional_edges(
        "progress_reflection",
        _route_after_progress_reflection,
        {
            "scene_fulfillment": "scene_fulfillment",
            "end": END,
        },
    )
    return workflow.compile(checkpointer=checkpointer)


def _wrap_node(
    node_name: str,
    node,
    services: GDPAgentServices,
    policy: GDPAgentPolicy,
    metadata: GDPAgentMetadata,
):
    """按 GDP 策略给图节点套用运行时 wrapper。"""

    if not policy.audit_enabled:
        return node
    return wrap_gdp_node_audit(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        metadata=metadata,
    )


def _get_gdp_runtime_config(config: RunnableConfig | None) -> GDPAgentRuntimeConfig:
    """从 RunnableConfig 中解析 GDP 运行时上下文。"""

    return GDPAgentRuntimeConfig(
        assistant_id=_runtime_value(config, "assistant_id") or "gdp_agent",
        thread_id=_runtime_value(config, "thread_id"),
        run_id=_runtime_value(config, "run_id"),
        user_id=_runtime_value(config, "user_id"),
        operator=_runtime_value(config, "operator"),
        model_name=_runtime_value(config, "model_name"),
    )


def _build_gdp_policy(app_config: AppConfig | None) -> GDPAgentPolicy:
    """从 AppConfig 中抽取 GDP 当前可用的运行策略。"""

    return GDPAgentPolicy(
        audit_enabled=True,
        memory_enabled=bool(getattr(getattr(app_config, "memory", None), "enabled", False)),
        checkpointer_enabled=getattr(app_config, "checkpointer", None) is not None,
    )


def _build_gdp_metadata(
    app_config: AppConfig | None,
    runtime: GDPAgentRuntimeConfig,
    policy: GDPAgentPolicy,
) -> GDPAgentMetadata:
    """构造 GDP 图装配元数据，供审计和追踪使用。"""

    return GDPAgentMetadata(
        assistant_id=runtime.assistant_id,
        thread_id=runtime.thread_id,
        run_id=runtime.run_id,
        user_id=runtime.user_id,
        model_name=runtime.model_name,
        log_level=getattr(app_config, "log_level", None),
        policy={
            "auditEnabled": policy.audit_enabled,
            "memoryEnabled": policy.memory_enabled,
            "checkpointerEnabled": policy.checkpointer_enabled,
        },
    )


def _runtime_value(config: RunnableConfig | None, key: str) -> str | None:
    if not config:
        return None
    for container_name in ("context", "configurable", "metadata"):
        container = config.get(container_name)
        if isinstance(container, dict) and container.get(key) is not None:
            return str(container[key])
    return None


def _route_after_scene_fulfillment(state: GDPState) -> str:
    if state.get("current_phase") == "WAITING_USER":
        return "human_confirm"
    if state.get("current_phase") == "SCENE_DESIGN":
        return "scene_design"
    if state.get("current_phase") == "SOURCE_CONFIG":
        return "source_config"
    return "progress_reflection"


def _route_after_scene_design(state: GDPState) -> str:
    if state.get("current_phase") == "SCENE_FULFILLMENT":
        return "scene_fulfillment"
    if state.get("current_phase") == "SOURCE_CONFIG":
        return "source_config"
    if state.get("current_phase") == "WAITING_USER":
        return "human_confirm"
    return "progress_reflection"


def _route_after_source_config(state: GDPState) -> str:
    if state.get("current_phase") == "SCENE_DESIGN":
        return "scene_design"
    if state.get("current_phase") == "INFRA_CONFIG":
        return "infra_config"
    if state.get("current_phase") == "WAITING_USER":
        return "human_confirm"
    return "progress_reflection"


def _route_after_infra_config(state: GDPState) -> str:
    if state.get("current_phase") == "SOURCE_CONFIG":
        return "source_config"
    if state.get("current_phase") == "WAITING_USER":
        return "human_confirm"
    return "progress_reflection"


def _route_after_human_confirm(state: GDPState) -> str:
    if state.get("current_phase") == "SCENE_EXECUTING":
        return "scene_execute"
    if state.get("current_phase") == "SCENE_FULFILLMENT":
        return "scene_fulfillment"
    if state.get("current_phase") == "SCENE_DESIGN":
        return "scene_design"
    if state.get("current_phase") == "SOURCE_CONFIG":
        return "source_config"
    if state.get("current_phase") == "INFRA_CONFIG":
        return "infra_config"
    return "progress_reflection"


def _route_after_progress_reflection(state: GDPState) -> str:
    if state.get("current_phase") == "SCENE_FULFILLMENT":
        return "scene_fulfillment"
    return "end"


def _build_services(
    *,
    app_config: AppConfig | None = None,
    runtime: GDPAgentRuntimeConfig | None = None,
) -> GDPAgentServices:
    """按本次 GDP 运行装配业务服务依赖。"""

    sf = get_session_factory()
    if sf is None:
        raise RuntimeError("GDP Agent 需要先初始化持久化 SessionFactory。")

    base_repository = BaseConfigRepository(sf)
    scene_repository = SceneRepository(sf)
    http_source_repository = HttpSourceRepository(sf)
    sql_source_repository = SqlSourceRepository(sf)
    task_service = DatagenTaskService(DatagenTaskRepository(sf))
    subtask_service = DatagenTaskSubtaskService(DatagenTaskSubtaskRepository(sf), task_service)
    http_source_service = HttpSourceService(http_source_repository, base_repository)
    sql_source_service = SqlSourceService(sql_source_repository, base_repository)
    catalog_service = AgentCatalogService(
        scene_repository=scene_repository,
        http_source_repository=http_source_repository,
        sql_source_repository=sql_source_repository,
        base_repository=base_repository,
    )
    sql_execution = SqlExecutionService(
        base_repository=base_repository,
        sql_source_repository=sql_source_repository,
        registry=SqlExecutorRegistry(),
    )
    scene_service = SceneService(scene_repository, SceneExecutor(sql_execution, base_repository))
    memory_service = GDPAgentMemoryService(GDPAgentMemoryRepository(sf))
    return GDPAgentServices(
        task_service=task_service,
        catalog_service=catalog_service,
        scene_service=scene_service,
        base_repository=base_repository,
        http_source_repository=http_source_repository,
        sql_source_repository=sql_source_repository,
        http_source_service=http_source_service,
        sql_source_service=sql_source_service,
        sql_execution_service=sql_execution,
        memory_service=memory_service,
        subtask_service=subtask_service,
    )
