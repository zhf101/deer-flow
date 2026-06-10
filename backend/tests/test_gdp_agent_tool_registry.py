"""GDP Agent 工具能力注册表测试。"""

from __future__ import annotations

from types import SimpleNamespace

from app.gdp.agent.tools.registry import (
    GDPToolOutputTarget,
    GDPToolSideEffectLevel,
    get_gdp_tool_specs,
    get_gdp_tools,
)
from app.gdp.datagen.config.task.models import DatagenTaskPhase


EXPECTED_TOOL_NAMES = {
    "get_datagen_task_state",
    "search_scene_contracts",
    "get_scene_contract",
    "bind_scene_inputs",
    "run_datagen_scene_for_task",
    "reflect_scene_result",
    "search_source_contracts",
    "compose_scene_draft_from_source",
    "publish_scene_from_source",
    "resolve_http_source_basis",
    "resolve_sql_source_basis",
    "upsert_http_source_from_agent",
    "upsert_sql_source_from_agent",
    "test_http_source_from_agent",
    "test_sql_source_from_agent",
    "parse_sql_source_from_agent",
    "resolve_infra_basis",
    "upsert_system_from_agent",
    "upsert_environment_from_agent",
    "upsert_service_endpoint_from_agent",
    "upsert_datasource_from_agent",
}


def test_get_gdp_tool_specs_covers_all_current_tools():
    specs = get_gdp_tool_specs()

    assert {item.name for item in specs} == EXPECTED_TOOL_NAMES
    assert len(specs) == len(EXPECTED_TOOL_NAMES)


def test_get_gdp_tools_returns_only_registered_tools():
    tools = get_gdp_tools(_services())

    assert {tool.name for tool in tools} == EXPECTED_TOOL_NAMES


def test_get_gdp_tool_specs_filters_by_phase():
    scene_design_specs = get_gdp_tool_specs("SCENE_DESIGN")

    assert {item.name for item in scene_design_specs} == {
        "get_datagen_task_state",
        "search_source_contracts",
        "compose_scene_draft_from_source",
        "publish_scene_from_source",
    }


def test_get_gdp_tools_filters_by_phase():
    tools = get_gdp_tools(_services(), DatagenTaskPhase.SCENE_EXECUTING)

    assert {tool.name for tool in tools} == {
        "get_datagen_task_state",
        "get_scene_contract",
        "bind_scene_inputs",
        "run_datagen_scene_for_task",
    }


def test_registry_marks_business_write_tools_as_approval_required():
    specs = {item.name: item for item in get_gdp_tool_specs()}

    scene_run = specs["run_datagen_scene_for_task"]
    assert scene_run.sideEffectLevel == GDPToolSideEffectLevel.BUSINESS_WRITE
    assert scene_run.requiresApproval is True
    assert scene_run.outputTarget == GDPToolOutputTarget.TASK_STEP
    assert scene_run.sensitiveOutput is True
    assert scene_run.idempotencyKeyFields == ["task_run_id", "scene_code", "env_code", "input_params"]

    http_test = specs["test_http_source_from_agent"]
    sql_test = specs["test_sql_source_from_agent"]
    assert http_test.sideEffectLevel == GDPToolSideEffectLevel.BUSINESS_WRITE
    assert sql_test.sideEffectLevel == GDPToolSideEffectLevel.BUSINESS_WRITE
    assert http_test.requiresApproval is True
    assert sql_test.requiresApproval is True
    assert http_test.outputTarget == GDPToolOutputTarget.STORAGE_REF
    assert sql_test.outputTarget == GDPToolOutputTarget.STORAGE_REF


def test_registry_marks_config_write_tools_as_approval_required():
    specs = {item.name: item for item in get_gdp_tool_specs()}
    config_write_names = {
        "publish_scene_from_source",
        "upsert_http_source_from_agent",
        "upsert_sql_source_from_agent",
        "upsert_system_from_agent",
        "upsert_environment_from_agent",
        "upsert_service_endpoint_from_agent",
        "upsert_datasource_from_agent",
    }

    for name in config_write_names:
        assert specs[name].sideEffectLevel == GDPToolSideEffectLevel.CONFIG_WRITE
        assert specs[name].requiresApproval is True
        assert specs[name].idempotencyKeyFields


def _services() -> SimpleNamespace:
    return SimpleNamespace(
        task_service=object(),
        catalog_service=object(),
        scene_service=object(),
        base_repository=object(),
        http_source_repository=object(),
        sql_source_repository=object(),
        http_source_service=object(),
        sql_source_service=object(),
        sql_execution_service=object(),
    )
