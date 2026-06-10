"""GDP 造数 Agent LangGraph 工厂。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.gdp.agent.middlewares.error_handling import wrap_gdp_error_handling
from app.gdp.agent.middlewares.goal_guard import wrap_gdp_goal_guard
from app.gdp.agent.middlewares.interrupt import wrap_gdp_interrupt
from app.gdp.agent.middlewares.node_audit import wrap_gdp_node_audit
from app.gdp.agent.middlewares.progress_loop import wrap_gdp_progress_loop_detection
from app.gdp.agent.middlewares.recovery import wrap_gdp_task_recovery
from app.gdp.agent.middlewares.runtime_context import wrap_gdp_runtime_context
from app.gdp.agent.middlewares.skill_context import wrap_gdp_skill_context
from app.gdp.agent.middlewares.task_run_sync import wrap_gdp_task_run_sync
from app.gdp.agent.nodes.human_confirm import build_human_confirm_node
from app.gdp.agent.nodes.infra_config import build_infra_config_node
from app.gdp.agent.nodes.intake import build_intake_node
from app.gdp.agent.nodes.progress_reflection import build_progress_reflection_node
from app.gdp.agent.nodes.scene_design import build_scene_design_node
from app.gdp.agent.nodes.scene_execute import build_scene_execute_node
from app.gdp.agent.nodes.scene_fulfillment import build_scene_fulfillment_node
from app.gdp.agent.nodes.source_config import build_source_config_node
from app.gdp.agent.observability import configure_gdp_observability
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
from app.gdp.datagen.config.task.models import DatagenTaskPhase
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
    app_config: AppConfig | None = None


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
    """GDP Agent 运行策略开关。

    可配置开关只有三个：``llm_decision_enabled``（config.yaml ``gdp_agent.llm_decision_enabled``）、
    ``memory_enabled``（config.yaml ``memory.enabled``）、``checkpointer_enabled``（由运行时决定）。
    **其余字段是内部常量**：生产路径恒为 True，仅供测试注入关闭，不通过 config.yaml
    暴露，前端/运维不应将其视为可配置能力。字段默认值即生产默认策略，构造方只需
    显式传入与默认不同的开关，避免字段清单多处手抄。
    """

    llm_decision_enabled: bool = False
    audit_enabled: bool = True
    goal_guard_enabled: bool = True
    memory_enabled: bool = False
    skills_enabled: bool = True
    progress_loop_enabled: bool = True
    checkpointer_enabled: bool = False
    runtime_context_enabled: bool = True
    task_run_sync_enabled: bool = True
    interrupt_enabled: bool = True
    error_handling_enabled: bool = True
    recovery_enabled: bool = True

    def as_metadata_dict(self) -> dict[str, Any]:
        """policy → metadata 的唯一序列化出口，避免字段映射多处手抄。"""

        return {
            "llmDecisionEnabled": self.llm_decision_enabled,
            "auditEnabled": self.audit_enabled,
            "goalGuardEnabled": self.goal_guard_enabled,
            "memoryEnabled": self.memory_enabled,
            "skillsEnabled": self.skills_enabled,
            "progressLoopEnabled": self.progress_loop_enabled,
            "checkpointerEnabled": self.checkpointer_enabled,
            "runtimeContextEnabled": self.runtime_context_enabled,
            "taskRunSyncEnabled": self.task_run_sync_enabled,
            "interruptEnabled": self.interrupt_enabled,
            "errorHandlingEnabled": self.error_handling_enabled,
            "recoveryEnabled": self.recovery_enabled,
        }


@dataclass(frozen=True)
class GDPAgentMetadata:
    """GDP Agent 图装配元数据。"""

    assistant_id: str
    thread_id: str | None
    run_id: str | None
    user_id: str | None
    operator: str | None
    model_name: str | None
    log_level: str | None
    policy: dict[str, Any]


def make_gdp_agent(config: RunnableConfig, app_config: AppConfig):
    """DeerFlow Runtime 调用的 GDP Agent 工厂。"""

    runtime = _get_gdp_runtime_config(config)
    policy = _build_gdp_policy(app_config)
    metadata = _build_gdp_metadata(app_config, runtime, policy)
    configure_gdp_observability(config, runtime=runtime, metadata=metadata)
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
    policy = policy or GDPAgentPolicy(checkpointer_enabled=checkpointer is not None)
    metadata = metadata or GDPAgentMetadata(
        assistant_id=runtime.assistant_id,
        thread_id=runtime.thread_id,
        run_id=runtime.run_id,
        user_id=runtime.user_id,
        operator=runtime.operator,
        model_name=runtime.model_name,
        log_level=None,
        policy=policy.as_metadata_dict(),
    )

    workflow = StateGraph(GDPState)
    workflow.add_node(
        "intake",
        _wrap_node(
            "intake",
            build_intake_node(
                services.task_service,
                services.memory_service,
                services.subtask_service,
                app_config=services.app_config,
                llm_enabled=policy.llm_decision_enabled,
            ),
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
                app_config=services.app_config,
                llm_enabled=policy.llm_decision_enabled,
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
                app_config=services.app_config,
                llm_enabled=policy.llm_decision_enabled,
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
                app_config=services.app_config,
                llm_enabled=policy.llm_decision_enabled,
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
            build_progress_reflection_node(
                services.task_service,
                services.subtask_service,
                app_config=services.app_config,
                llm_enabled=policy.llm_decision_enabled,
            ),
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
            "scene_design": "scene_design",
            "source_config": "source_config",
            "infra_config": "infra_config",
            "scene_execute": "scene_execute",
            "human_confirm": "human_confirm",
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

    node = wrap_gdp_runtime_context(
        node=node,
        metadata=metadata,
        enabled=policy.runtime_context_enabled,
    )
    node = wrap_gdp_task_recovery(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        enabled=policy.recovery_enabled,
    )
    node = wrap_gdp_task_run_sync(
        node=node,
        task_service=services.task_service,
        enabled=policy.task_run_sync_enabled,
    )
    node = wrap_gdp_interrupt(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        enabled=policy.interrupt_enabled,
    )
    node = wrap_gdp_skill_context(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        enabled=policy.skills_enabled,
    )
    node = wrap_gdp_goal_guard(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        subtask_service=services.subtask_service,
        enabled=policy.goal_guard_enabled,
    )
    node = wrap_gdp_progress_loop_detection(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        enabled=policy.progress_loop_enabled,
    )
    if policy.audit_enabled:
        node = wrap_gdp_node_audit(
            node_name=node_name,
            node=node,
            task_service=services.task_service,
            metadata=metadata,
        )
    return wrap_gdp_error_handling(
        node_name=node_name,
        node=node,
        task_service=services.task_service,
        metadata=metadata,
        enabled=policy.error_handling_enabled,
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
        llm_decision_enabled=_gdp_agent_config_bool(app_config, "llm_decision_enabled", True),
        memory_enabled=bool(getattr(getattr(app_config, "memory", None), "enabled", False)),
        # Gateway 工厂路径运行时恒有 checkpointer：worker（runtime/runs/worker.py）在构图后
        # 总会挂载 make_checkpointer() 的结果，未配置 checkpointer/database 时也会回退
        # InMemorySaver。因此 metadata 的 checkpointerEnabled 按运行时真实值写 True，
        # 而不是按 app_config.checkpointer 是否配置判断。
        checkpointer_enabled=True,
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
        operator=runtime.operator,
        model_name=runtime.model_name,
        log_level=getattr(app_config, "log_level", None),
        policy=policy.as_metadata_dict(),
    )


def _runtime_value(config: RunnableConfig | None, key: str) -> str | None:
    if not config:
        return None
    for container_name in ("context", "configurable", "metadata"):
        container = config.get(container_name)
        if isinstance(container, dict) and container.get(key) is not None:
            return str(container[key])
    return None


_PHASE_TO_NODE: dict[DatagenTaskPhase, str] = {
    DatagenTaskPhase.SCENE_FULFILLMENT: "scene_fulfillment",
    DatagenTaskPhase.SCENE_DESIGN: "scene_design",
    DatagenTaskPhase.SOURCE_CONFIG: "source_config",
    DatagenTaskPhase.INFRA_CONFIG: "infra_config",
    DatagenTaskPhase.SCENE_EXECUTING: "scene_execute",
    DatagenTaskPhase.WAITING_USER: "human_confirm",
}
"""阶段 → 图节点的唯一映射表。

节点写入 phase 时使用 ``DatagenTaskPhase.X.value``，路由读取时统一经
``_normalize_phase`` 还原为枚举后查本表，保证读写两侧同一份真相。
"""


def _normalize_phase(value: Any) -> DatagenTaskPhase | None:
    if isinstance(value, DatagenTaskPhase):
        return value
    if value is None:
        return None
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return None


def _route_by_phase(state: GDPState, *, allowed: frozenset[str], default: str) -> str:
    """按 current_phase 查表路由；目标不在当前节点出边集合内时走默认分支。"""

    target = _PHASE_TO_NODE.get(_normalize_phase(state.get("current_phase")))
    if target is not None and target in allowed:
        return target
    return default


def _route_after_scene_fulfillment(state: GDPState) -> str:
    return _route_by_phase(
        state,
        allowed=frozenset({"human_confirm", "scene_design", "source_config"}),
        default="progress_reflection",
    )


def _route_after_scene_design(state: GDPState) -> str:
    return _route_by_phase(
        state,
        allowed=frozenset({"scene_fulfillment", "source_config", "human_confirm"}),
        default="progress_reflection",
    )


def _route_after_source_config(state: GDPState) -> str:
    return _route_by_phase(
        state,
        allowed=frozenset({"scene_design", "infra_config", "human_confirm"}),
        default="progress_reflection",
    )


def _route_after_infra_config(state: GDPState) -> str:
    return _route_by_phase(
        state,
        allowed=frozenset({"source_config", "human_confirm"}),
        default="progress_reflection",
    )


def _route_after_human_confirm(state: GDPState) -> str:
    return _route_by_phase(
        state,
        allowed=frozenset({"scene_execute", "scene_fulfillment", "scene_design", "source_config", "infra_config"}),
        default="progress_reflection",
    )


def _route_after_progress_reflection(state: GDPState) -> str:
    return _route_by_phase(
        state,
        allowed=frozenset({"scene_fulfillment", "scene_design", "source_config", "infra_config", "scene_execute", "human_confirm"}),
        default="end",
    )


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
    memory_enabled = bool(getattr(getattr(app_config, "memory", None), "enabled", False))
    memory_service = GDPAgentMemoryService(GDPAgentMemoryRepository(sf)) if memory_enabled else None
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
        app_config=app_config,
    )


def _gdp_agent_config_bool(app_config: AppConfig | None, key: str, default: bool) -> bool:
    """读取 GDP Agent 专用布尔配置，支持 config.yaml 额外字段。"""

    if app_config is None:
        return default
    container = getattr(app_config, "gdp_agent", None)
    if container is None:
        return default
    if isinstance(container, dict):
        return bool(container.get(key, default))
    return bool(getattr(container, key, default))
