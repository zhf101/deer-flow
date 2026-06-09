"""GDP 造数 Agent LangGraph 工厂。"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

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


def make_gdp_agent(config: RunnableConfig, app_config: AppConfig):
    """DeerFlow Runtime 调用的 GDP Agent 工厂。"""

    _ = (config, app_config)
    return make_gdp_graph(_build_services())


def make_gdp_graph(services: GDPAgentServices, *, checkpointer=None):
    """构造 GDP 造数业务图。"""

    workflow = StateGraph(GDPState)
    workflow.add_node("intake", build_intake_node(services.task_service))
    workflow.add_node(
        "scene_fulfillment",
        build_scene_fulfillment_node(
            catalog_service=services.catalog_service,
            task_service=services.task_service,
            scene_service=services.scene_service,
        ),
    )
    workflow.add_node(
        "scene_design",
        build_scene_design_node(
            catalog_service=services.catalog_service,
            task_service=services.task_service,
            scene_service=services.scene_service,
            http_source_repository=services.http_source_repository,
            sql_source_repository=services.sql_source_repository,
        ),
    )
    workflow.add_node("human_confirm", build_human_confirm_node(services.task_service))
    workflow.add_node(
        "source_config",
        build_source_config_node(
            task_service=services.task_service,
            base_repository=services.base_repository,
            http_source_service=services.http_source_service,
            sql_source_service=services.sql_source_service,
        ),
    )
    workflow.add_node(
        "infra_config",
        build_infra_config_node(
            task_service=services.task_service,
            base_repository=services.base_repository,
        ),
    )
    workflow.add_node(
        "scene_execute",
        build_scene_execute_node(
            catalog_service=services.catalog_service,
            task_service=services.task_service,
            scene_service=services.scene_service,
        ),
    )
    workflow.add_node("progress_reflection", build_progress_reflection_node(services.task_service))

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


def _build_services() -> GDPAgentServices:
    sf = get_session_factory()
    if sf is None:
        raise RuntimeError("GDP Agent 需要先初始化持久化 SessionFactory。")

    base_repository = BaseConfigRepository(sf)
    scene_repository = SceneRepository(sf)
    http_source_repository = HttpSourceRepository(sf)
    sql_source_repository = SqlSourceRepository(sf)
    task_service = DatagenTaskService(DatagenTaskRepository(sf))
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
    )
