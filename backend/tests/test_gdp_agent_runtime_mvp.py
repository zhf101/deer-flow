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
    assert "GDP Agent 运行时任务开始运行" in messages
    assert "GDP Agent 运行时计划步骤已创建" in messages
    assert "GDP Agent 运行时动作尝试开始" in messages
    assert "GDP Agent 运行时场景调用完成" in messages
    assert "GDP Agent 运行时判定证据已生成" in messages
    assert "GDP Agent 运行时判定结果已生成" in messages
    assert "GDP Agent 运行时任务运行结束" in messages
    assert "任务目标=造一笔已支付订单" in messages
    assert '输入内容={"buyer_id": "U1"}' in messages
    assert '输入摘要={"buyer_id": "U1"}' in messages
    assert '"order_id": "ORDER-1"' in messages
    assert "订单支付状态(order.pay_status)" in messages
    assert "目标长度" not in messages
    assert "输入数量" not in messages
    assert "预览字段" not in messages


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
    assert result.pending_question == "执行结果未知：执行尝试结果未知(attempt_result_unknown)"
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
async def test_runtime_mvp_business_result_failure_carries_exact_reason(monkeypatch: pytest.MonkeyPatch):
    """场景配了 successCriteria 并判业务失败时，Agent 采信 businessResult 并保留精确原因。

    复现踩坑点：业务规则判失败时 Scene 把 status 降级为 FAILED 但 errors 为空，
    真正原因只在 businessResult.reason/failedRules 里。此前 Agent 不读该字段，
    会把原因吞成“场景执行失败”。本用例钉住失败原因必须一路传到 failure_reason。
    """

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "FAILED",  # 业务判定失败被降级，但步骤无报错
            "finalOutput": {"pay_status": "UNPAID"},
            "businessResult": {
                "isSuccess": False,
                "reason": "命中场景失败规则: pay_status eq UNPAID",
                "matchedRules": ["pay_status eq UNPAID"],
                "failedRules": ["pay_status eq UNPAID"],
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
    assert result.status == TaskRunStatus.FAILED
    # 精确原因没有被吞成“场景执行失败”，failedRules 一路传到了 failure_reason
    assert "pay_status eq UNPAID" in result.failure_reason
    # business_success 事实被抽出且 detail 带规则原因
    business_facts = [
        f for f in timeline["evidences"][0]["facts"] if f["subject"] == "scene.business_success"
    ]
    assert business_facts and business_facts[0]["passed"] is False
    assert "pay_status eq UNPAID" in business_facts[0]["detail"]
    assert timeline["verdicts"][0]["verdict_type"] == "FAILED"


@pytest.mark.anyio
async def test_runtime_mvp_business_result_success_completes(monkeypatch: pytest.MonkeyPatch):
    """场景配了 successCriteria 并判业务成功时，Agent 采信 businessResult 直接完成。

    任意配了规则的真实场景都应能复用，而不依赖 create_paid_order 的硬编码字段契约。
    """

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "SUCCESS",
            "finalOutput": {"any_field": "any_value"},
            "businessResult": {
                "isSuccess": True,
                "reason": "所有场景成功条件均已满足",
                "matchedRules": ["code eq 0"],
                "failedRules": [],
            },
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    store = Store()
    task_run = create_task_run("执行任意配规则的场景", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code="some_configured_scene", inputs={"k": "v"}),
        store,
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.COMPLETED
    business_facts = [
        f for f in timeline["evidences"][0]["facts"] if f["subject"] == "scene.business_success"
    ]
    assert business_facts and business_facts[0]["passed"] is True
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
    # 失败原因直接给用户看得懂的业务原因，而不是“期望=SUCCEEDED 实际=FAILED”的机器话
    assert "余额不足" in result.failure_reason
    assert timeline["actions"][0]["status"] == "FAILED"
    assert timeline["steps"][0]["status"] == "FAILED"
    assert timeline["attempts"][0]["status"] == "FAILED"


@pytest.mark.anyio
async def test_runtime_mvp_http_failure_surfaces_friendly_reason(monkeypatch: pytest.MonkeyPatch):
    """HTTP 步骤连接失败时，Agent 把执行器写的中文排查提示透传给用户。

    复现踩坑点：真正友好的原因藏在 stepResults[].rawResponse.error.detail，
    顶层 errors 只有“All connection attempts failed”这种堆栈味英文。
    此前只取顶层 errors，本用例钉住友好中文必须一路传到 failure_reason。
    """

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "status": "FAILED",
            "businessResult": None,
            "finalOutput": {},
            "errors": ["http_session_login: All connection attempts failed"],
            "stepResults": [
                {
                    "stepId": "http_session_login",
                    "status": "FAILED",
                    "rawResponse": {
                        "error": {
                            "type": "ConnectError",
                            "message": "All connection attempts failed",
                            "detail": "无法连接到目标服务器，请检查服务器地址、端口是否正确，以及目标服务是否正常运行。",
                        }
                    },
                }
            ],
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

    assert result.status == TaskRunStatus.FAILED
    # 友好中文透传到失败原因，而不是 All connection attempts failed
    assert "无法连接到目标服务器" in result.failure_reason
    assert "All connection attempts failed" not in result.failure_reason


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
async def test_runtime_mvp_api_create_start_query_timeline(monkeypatch: pytest.MonkeyPatch, caplog):
    """API 能创建、启动、查询和读取 timeline。"""
    caplog.set_level(logging.INFO, logger="app.gdp.agent_runtime")

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

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "用户目标=造一笔已支付订单" in messages
    assert '用户输入请求报文={"buyer_id": "U1"}' in messages
    assert "时间线内容=" in messages
    assert '"goal": "造一笔已支付订单"' in messages
    assert '"input_preview": {"buyer_id": "U1"}' in messages


def test_runtime_mvp_does_not_import_old_gdp_agent_core():
    """新 runtime 不能导入旧 GDP Agent 核心模块。"""

    runtime_root = Path(__file__).resolve().parents[1] / "app" / "gdp" / "agent_runtime"
    violations: list[str] = []

    for py_file in runtime_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "app.gdp.agent" in text or "backend.app.gdp.agent" in text:
            violations.append(str(py_file.relative_to(runtime_root)))

    assert violations == []
