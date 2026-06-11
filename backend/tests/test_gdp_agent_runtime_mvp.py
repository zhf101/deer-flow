"""GDP Agent Runtime MVP 纵切片测试。"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.agent_runtime import api as runtime_api
from app.gdp.agent_runtime.flow import create_single_step, create_task_run, make_scene_action
from app.gdp.agent_runtime.models import LMProposal, TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store
from app.gdp.agent_runtime.transitions import IllegalTransition, transition_task_run


@pytest.mark.anyio
async def test_runtime_mvp_happy_path_completes_from_scene_evidence(monkeypatch: pytest.MonkeyPatch, caplog):
    """执行已支付订单场景后，Evidence 通过并完成 TaskRun。"""
    caplog.set_level(logging.INFO, logger="app.gdp.agent_runtime")

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "create_paid_order"
        assert env_code == "SIT1"
        assert inputs == {"buyer_id": "U1"}
        return {
            "status": "SUCCESS",
            "finalOutput": {
                "order_id": "ORDER-1",
                "pay_status": "PAID",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert timeline["actions"][0]["status"] == "SUCCEEDED"
    assert timeline["steps"][0]["status"] == "DONE"
    assert timeline["attempts"][0]["status"] == "SUCCEEDED"
    assert timeline["verdicts"][0]["verdict_type"] == "DONE"
    assert timeline["variables"][0]["provenance"]["source_type"] == "USER_INPUT"

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "GDP Agent Runtime TaskRun 开始运行" in messages
    assert "GDP Agent Runtime PlanStep 已创建" in messages
    assert "GDP Agent Runtime Action Attempt 开始" in messages
    assert "GDP Agent Runtime Scene 调用完成" in messages
    assert "GDP Agent Runtime Evidence 已生成" in messages
    assert "GDP Agent Runtime Verdict 已生成" in messages
    assert "GDP Agent Runtime TaskRun 运行结束" in messages


@pytest.mark.anyio
async def test_runtime_mvp_unknown_state_waits_for_user(monkeypatch: pytest.MonkeyPatch):
    """副作用未知时不自动失败或重放，进入 WAITING_USER。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        raise TimeoutError("timeout")

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.WAITING_USER
    assert result.pending_question == "执行结果未知: attempt_result_unknown"
    assert timeline["actions"][0]["status"] == "UNKNOWN_STATE"
    assert timeline["steps"][0]["status"] == "BLOCKED"
    assert timeline["attempts"][0]["status"] == "UNKNOWN_STATE"
    assert timeline["verdicts"][0]["verdict_type"] == "UNKNOWN_STATE"


@pytest.mark.anyio
async def test_runtime_mvp_completes_when_scene_business_rules_succeed(monkeypatch: pytest.MonkeyPatch):
    """Scene 已按自身业务规则判定成功时，Agent 不再要求固定订单字段。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        assert scene_code == "mock_full_stack_http_sql_complex"
        return {
            "status": "SUCCESS",
            "finalOutput": {
                "summary": "复杂编排执行成功",
                "logId": 10001,
                "accountName": "测试账户",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("执行复杂 HTTP/SQL 编排", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(
            scene_code="mock_full_stack_http_sql_complex",
            inputs={"accountId": "10001", "orderNo": "T202606110101"},
        ),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    assert timeline["actions"][0]["status"] == "SUCCEEDED"
    assert timeline["attempts"][0]["status"] == "SUCCEEDED"
    assert timeline["evidences"][0]["facts"][0]["subject"] == "scene.status"
    assert timeline["evidences"][0]["facts"][0]["passed"] is True
    assert timeline["evidences"][0]["missing_facts"] == []
    assert timeline["verdicts"][0]["verdict_type"] == "DONE"


@pytest.mark.anyio
async def test_runtime_mvp_scene_failure_fails_task_run(monkeypatch: pytest.MonkeyPatch):
    """Scene 明确失败时 TaskRun 进入 FAILED。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "FAILED",
            "finalOutput": {},
            "errors": ["余额不足"],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="create_paid_order", inputs={"buyer_id": "U1"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.FAILED
    assert "attempt.status" in result.failure_reason
    assert timeline["actions"][0]["status"] == "FAILED"
    assert timeline["steps"][0]["status"] == "FAILED"
    assert timeline["attempts"][0]["status"] == "FAILED"


def test_runtime_mvp_idempotency_key_ignores_random_action_id():
    """同一 TaskRun、Scene 和输入生成同一幂等键。"""

    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)

    first = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
    second = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})

    assert first.action_id != second.action_id
    assert first.idempotency_key == second.idempotency_key


def test_runtime_mvp_rejects_lm_proposal_as_status_fact():
    """事实状态写入接口拒绝 LMProposal。"""

    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    proposal = LMProposal(
        proposal_id="proposal-1",
        payload=TaskRunStatus.RUNNING,
        prompt_hash="hash",
        model_name="mock",
        confidence=0.5,
    )

    with pytest.raises(TypeError, match="LMProposal 不能作为事实写入"):
        transition_task_run(task_run, proposal)  # type: ignore[arg-type]

    with pytest.raises(IllegalTransition):
        transition_task_run(task_run, TaskRunStatus.COMPLETED)


@pytest.mark.anyio
async def test_runtime_mvp_api_create_start_query_timeline(monkeypatch: pytest.MonkeyPatch):
    """API 能创建、启动、查询和读取 timeline。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {
                "order_id": "ORDER-1",
                "pay_status": "PAID",
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr(runtime_api, "_store", Store())

    app = FastAPI()
    app.include_router(runtime_api.router, prefix="/api/v1/datagen")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "造一笔已支付订单", "env_code": "SIT1"},
        )
        assert create.status_code == 200, create.text
        task_run_id = create.json()["task_run_id"]

        empty_scene = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "", "inputs": {}},
        )
        assert empty_scene.status_code == 422

        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"scene_code": "create_paid_order", "inputs": {"buyer_id": "U1"}},
        )
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "COMPLETED"

        get = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}")
        assert get.status_code == 200
        assert get.json()["status"] == "COMPLETED"

        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/timeline")
        assert timeline.status_code == 200
        assert timeline.json()["verdicts"][0]["verdict_type"] == "DONE"


def test_runtime_mvp_does_not_import_old_gdp_agent_core():
    """新 runtime 不能导入旧 GDP Agent 核心模块。"""

    runtime_root = Path(__file__).resolve().parents[1] / "app" / "gdp" / "agent_runtime"
    violations: list[str] = []

    for py_file in runtime_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "app.gdp.agent" in text or "backend.app.gdp.agent" in text:
            violations.append(str(py_file.relative_to(runtime_root)))

    assert violations == []
