"""GDP Agent 阶段技能注册测试。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gdp.agent.skills.api import router as skill_router
from app.gdp.agent.skills.registry import (
    get_gdp_skill_context,
    list_gdp_skills,
    list_gdp_skills_for_phase,
)
from app.gdp.agent.tools.registry import get_gdp_tool_specs
from app.gdp.datagen.config.task.models import DatagenTaskPhase


def test_gdp_skill_registry_maps_phase_to_methodology_refs():
    skills = list_gdp_skills_for_phase(DatagenTaskPhase.SCENE_DESIGN)
    skill_ids = {skill.skillId for skill in skills}

    assert {"gdp-scene-design", "gdp-sql-source-design", "gdp-http-source-design"}.issubset(skill_ids)
    assert all(skill.version for skill in skills)
    assert all(skill.allowedActions for skill in skills)
    assert all(skill.guidance for skill in skills)


def test_gdp_skill_context_is_lightweight_state_payload():
    context = get_gdp_skill_context(DatagenTaskPhase.SCENE_FULFILLMENT)

    assert context["enabled"] is True
    assert context["phase"] == "SCENE_FULFILLMENT"
    assert context["skillIds"] == ["gdp-scene-selection", "gdp-variable-stack"]
    assert all("content" not in skill for skill in context["skills"])
    assert all("prompt" not in skill for skill in context["skills"])


def test_gdp_skill_allowed_actions_match_registered_tool_names():
    tool_names = {tool.name for tool in get_gdp_tool_specs()}

    for skill in list_gdp_skills():
        assert set(skill.allowedActions).issubset(tool_names), skill.skillId


def test_gdp_approval_policy_covers_all_write_phases():
    approval_skill = next(skill for skill in list_gdp_skills() if skill.skillId == "gdp-approval-policy")

    assert set(approval_skill.phases) == {
        DatagenTaskPhase.SCENE_DESIGN,
        DatagenTaskPhase.SOURCE_CONFIG,
        DatagenTaskPhase.INFRA_CONFIG,
        DatagenTaskPhase.SCENE_EXECUTING,
    }
    assert {
        "publish_scene_from_source",
        "upsert_http_source_from_agent",
        "upsert_sql_source_from_agent",
        "upsert_system_from_agent",
        "upsert_environment_from_agent",
        "upsert_service_endpoint_from_agent",
        "upsert_datasource_from_agent",
        "run_datagen_scene_for_task",
    }.issubset(set(approval_skill.allowedActions))


def test_gdp_skill_api_uses_get_query_contract():
    app = FastAPI()
    app.include_router(skill_router, prefix="/api/v1/datagen")
    client = TestClient(app)

    all_response = client.get("/api/v1/datagen/agent-skills")
    phase_response = client.get("/api/v1/datagen/agent-skills/phase/SCENE_EXECUTING")

    assert all_response.status_code == 200
    assert len(all_response.json()) == len(list_gdp_skills())
    assert phase_response.status_code == 200
    assert {item["skillId"] for item in phase_response.json()["skills"]} == {
        "gdp-approval-policy",
        "gdp-task-recovery",
    }
