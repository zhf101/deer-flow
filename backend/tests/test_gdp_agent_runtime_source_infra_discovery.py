"""GDP Agent Runtime Source / Infra 只读发现测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from _agent_runtime_catalog_fakes import FakeSceneCatalog, make_infra_candidate, make_source_candidate

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import RequirementLayer, SuspendReason, TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store


@pytest.mark.anyio
async def test_scene_zero_candidate_discovers_source_and_infra_without_scene_write(monkeypatch: pytest.MonkeyPatch):
    """Scene 零候选后只读发现 Source / Infra，不发起场景写请求。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[],
            source_candidates=[
                make_source_candidate("createOrderApi", source_name="创建订单接口"),
                make_source_candidate("payOrderApi", source_name="支付订单接口", path="/api/payments"),
            ],
            infra_candidates=[
                make_infra_candidate(resource_type="HTTP", ready=True),
                make_infra_candidate(resource_type="HTTP", ready=False, missing_fields=["serviceEndpoint"]),
            ],
        ),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert called is False
    assert result.status == TaskRunStatus.WAITING_USER
    assert result.suspend_reason == SuspendReason.NEED_SCENE_SELECTION
    assert "发现可复用的 Source" in (result.pending_question or "")
    assert [item["layer"] for item in timeline["requirements"]] == [
        RequirementLayer.SCENE,
        RequirementLayer.SOURCE,
        RequirementLayer.INFRA,
    ]
    source_proposal = timeline["proposals"][1]
    assert source_proposal["source_candidates"][0]["source_code"] == "createOrderApi"
    assert source_proposal["infra_candidates"][1]["missing_fields"] == ["serviceEndpoint"]
    assert source_proposal["candidates"] == []
    assert timeline["actions"] == []
    assert timeline["attempts"] == []


@pytest.mark.anyio
async def test_scene_zero_candidate_without_source_keeps_manual_scene_path():
    """没有 Source 候选时仍等待用户手动补 scene_code，但 timeline 记录 SOURCE 发现为空。"""
    store = Store()
    task_run = create_task_run("找一个不存在的场景", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={}),
        store,
        catalog=FakeSceneCatalog(candidates=[], source_candidates=[]),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.WAITING_USER
    assert result.suspend_reason == SuspendReason.NEED_SCENE_SELECTION
    assert "没有发现可复用" in (result.pending_question or "")
    assert timeline["requirements"][0]["layer"] == RequirementLayer.SCENE
    assert timeline["requirements"][1]["layer"] == RequirementLayer.SOURCE
    assert timeline["proposals"][1]["source_candidates"] == []


@pytest.mark.anyio
async def test_infra_timeline_projection_redacts_sensitive_fields():
    """Infra timeline 投影不能暴露 token、密码或完整连接串。"""
    store = Store()
    task_run = create_task_run("造一笔订单", env_code="SIT1")
    store.save_task_run(task_run)
    unsafe_infra = make_infra_candidate(resource_type="HTTP", ready=True)
    unsafe_infra.matched_service_endpoints[0]["token"] = "secret-token"
    unsafe_infra.matched_datasources.append(
        {
            "datasourceCode": "orderDb",
            "password": "secret-password",
            "connectionString": "mysql://user:pass@host/db",
        }
    )

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[],
            source_candidates=[make_source_candidate("createOrderApi")],
            infra_candidates=[unsafe_infra],
        ),
    )

    timeline = store.get_timeline(result.task_run_id)
    infra = timeline["proposals"][1]["infra_candidates"][0]
    assert "token" not in infra["matched_service_endpoints"][0]
    assert "password" not in infra["matched_datasources"][0]
    assert "connectionString" not in infra["matched_datasources"][0]
