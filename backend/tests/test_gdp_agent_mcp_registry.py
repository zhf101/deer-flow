"""GDP Agent MCP 能力策略注册测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.gdp.agent.mcp.api import router as mcp_router
from app.gdp.agent.mcp.models import GDPMCPCapabilityPlanRequest, GDPMCPCapabilityResultApplyRequest
from app.gdp.agent.mcp.planner import plan_gdp_mcp_capability_call
from app.gdp.agent.mcp.registry import (
    evaluate_gdp_mcp_capability,
    get_gdp_mcp_capability,
    list_gdp_mcp_capabilities,
    list_gdp_mcp_capabilities_for_phase,
)
from app.gdp.agent.mcp.result_handler import apply_gdp_mcp_capability_result
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskRunCreateRequest
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


def test_gdp_mcp_registry_exposes_capabilities_not_raw_tools():
    capabilities = list_gdp_mcp_capabilities()

    assert {item.capabilityName for item in capabilities} >= {
        "gdp-mcp-knowledge-search",
        "gdp-mcp-approval-ticket",
    }
    assert all(item.mcpServerName for item in capabilities)
    assert all(item.mcpToolName for item in capabilities)
    assert all(item.allowedPhases for item in capabilities)


def test_gdp_mcp_registry_filters_by_phase():
    capabilities = list_gdp_mcp_capabilities_for_phase(DatagenTaskPhase.SCENE_EXECUTING)

    assert {item.capabilityName for item in capabilities} == {
        "gdp-mcp-approval-ticket",
        "gdp-mcp-quality-check",
    }


def test_gdp_mcp_policy_denies_unknown_raw_tool_name():
    decision = evaluate_gdp_mcp_capability(
        capability_name="raw-slack-send-message",
        phase=DatagenTaskPhase.SCENE_EXECUTING,
        env_code="DEV",
        arguments={},
    )

    assert decision.allowed is False
    assert decision.reason == "MCP 能力未在 GDP registry 注册，禁止暴露原始 MCP tool。"


def test_gdp_mcp_policy_requires_approval_for_side_effect_capability():
    capability = get_gdp_mcp_capability("gdp-mcp-approval-ticket")
    decision = evaluate_gdp_mcp_capability(
        capability_name=capability.capabilityName,
        phase=DatagenTaskPhase.SCENE_EXECUTING,
        env_code="DEV",
        arguments={"taskRunId": "task_1", "ticketType": "WRITE_APPROVAL"},
    )

    assert decision.allowed is False
    assert decision.requiresApproval is True
    assert decision.approvalKey == 'gdp-mcp-approval-ticket:{"taskRunId":"task_1","ticketType":"WRITE_APPROVAL"}'

    approved = evaluate_gdp_mcp_capability(
        capability_name=capability.capabilityName,
        phase=DatagenTaskPhase.SCENE_EXECUTING,
        env_code="DEV",
        arguments={"taskRunId": "task_1", "ticketType": "WRITE_APPROVAL"},
        approved_approval_keys=[decision.approvalKey],
    )
    assert approved.allowed is True


def test_gdp_mcp_api_uses_get_and_post_contracts():
    app = FastAPI()
    app.include_router(mcp_router, prefix="/api/v1/datagen")
    client = TestClient(app)

    list_response = client.get("/api/v1/datagen/agent-mcp/capabilities")
    phase_response = client.get("/api/v1/datagen/agent-mcp/capabilities/phase/SCENE_DESIGN")
    evaluate_response = client.post(
        "/api/v1/datagen/agent-mcp/capabilities/evaluate",
        json={
            "capabilityName": "gdp-mcp-knowledge-search",
            "phase": "SCENE_DESIGN",
            "envCode": "DEV",
            "arguments": {"query": "订单造数"},
        },
    )

    assert list_response.status_code == 200
    assert phase_response.status_code == 200
    assert evaluate_response.status_code == 200
    assert evaluate_response.json()["allowed"] is True


@pytest.mark.anyio
async def test_plan_gdp_mcp_capability_call_records_allowed_task_event(tmp_path):
    db_path = tmp_path / "gdp-mcp-plan.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="设计订单造数 Source", envCode="TEST")
        )

        response = await plan_gdp_mcp_capability_call(
            task_service,
            GDPMCPCapabilityPlanRequest(
                taskRunId=task.taskRunId,
                capabilityName="gdp-mcp-knowledge-search",
                phase=DatagenTaskPhase.SCENE_DESIGN,
                arguments={"query": "订单造数 Source"},
            ),
        )

        assert response.decision.allowed is True
        assert response.executionMode == "EXTERNAL_EXECUTOR"
        assert response.callSpec is not None
        assert response.callSpec.taskRunId == task.taskRunId
        assert response.callSpec.phase == "SCENE_DESIGN"
        assert response.callSpec.envCode == "TEST"
        assert response.resultRef == {
            "ref_type": "MCP_CAPABILITY",
            "capability_name": "gdp-mcp-knowledge-search",
            "approval_key": 'gdp-mcp-knowledge-search:{"query":"订单造数 Source"}',
            "summary": {
                "allowed": True,
                "phase": "SCENE_DESIGN",
                "outputVariablePolicy": "SUMMARY_ONLY",
            },
        }
        events = await task_service.list_events(task.taskRunId)
        assert events[-1].eventType == "MCP_CAPABILITY_EVALUATED"
        assert events[-1].payload["callSpec"]["mcpServerName"] == "knowledge-base"
        assert events[-1].payload["decision"]["allowed"] is True
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_plan_gdp_mcp_capability_call_records_rejected_task_event(tmp_path):
    db_path = tmp_path / "gdp-mcp-plan-rejected.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="创建审批单", envCode="DEV")
        )

        response = await plan_gdp_mcp_capability_call(
            task_service,
            GDPMCPCapabilityPlanRequest(
                taskRunId=task.taskRunId,
                capabilityName="gdp-mcp-approval-ticket",
                phase=DatagenTaskPhase.SCENE_EXECUTING,
                arguments={"taskRunId": task.taskRunId, "ticketType": "WRITE_APPROVAL"},
            ),
        )

        assert response.decision.allowed is False
        assert response.callSpec is None
        assert response.resultRef is None
        events = await task_service.list_events(task.taskRunId)
        assert events[-1].eventType == "MCP_CAPABILITY_REJECTED"
        assert events[-1].payload["decision"]["approvalKey"] == (
            f'gdp-mcp-approval-ticket:{{"taskRunId":"{task.taskRunId}","ticketType":"WRITE_APPROVAL"}}'
        )
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_gdp_mcp_plan_api_records_task_event(tmp_path):
    db_path = tmp_path / "gdp-mcp-plan-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="校验造数结果", envCode="DEV")
        )
        app = FastAPI()
        app.include_router(mcp_router, prefix="/api/v1/datagen")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/datagen/agent-mcp/capabilities/plan",
                json={
                    "taskRunId": task.taskRunId,
                    "capabilityName": "gdp-mcp-quality-check",
                    "phase": "PROGRESS_REFLECTION",
                    "arguments": {"taskRunId": task.taskRunId, "sceneRunId": "scene_run_1"},
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["decision"]["allowed"] is True
        assert body["executionMode"] == "EXTERNAL_EXECUTOR"
        assert body["callSpec"]["mcpToolName"] == "validate_datagen_result"
        events = await task_service.list_events(task.taskRunId)
        assert events[-1].eventType == "MCP_QUALITY_CHECKED"
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_gdp_mcp_apply_result_api_records_task_event(tmp_path):
    db_path = tmp_path / "gdp-mcp-apply-api.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="归并 MCP 结果", envCode="DEV")
        )
        app = FastAPI()
        app.include_router(mcp_router, prefix="/api/v1/datagen")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/datagen/agent-mcp/capabilities/apply-result",
                json={
                    "taskRunId": task.taskRunId,
                    "capabilityName": "gdp-mcp-knowledge-search",
                    "phase": "SCENE_DESIGN",
                    "outputVariablePolicy": "SUMMARY_ONLY",
                    "success": True,
                    "output": {"documents": [{"title": "接口规范"}]},
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["eventType"] == "MCP_CAPABILITY_RESULT_RECORDED"
        assert body["nextAction"] == "CALL_TASK_CONTINUE"
        assert body["visibleVariables"] == []
        events = await task_service.list_events(task.taskRunId)
        assert events[-1].eventType == "MCP_CAPABILITY_RESULT_RECORDED"
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_apply_gdp_mcp_summary_result_records_event_without_variable_stack(tmp_path):
    db_path = tmp_path / "gdp-mcp-result-summary.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="搜索造数知识", envCode="DEV")
        )

        result = await apply_gdp_mcp_capability_result(
            task_service,
            GDPMCPCapabilityResultApplyRequest(
                taskRunId=task.taskRunId,
                capabilityName="gdp-mcp-knowledge-search",
                phase=DatagenTaskPhase.SCENE_DESIGN,
                outputVariablePolicy="SUMMARY_ONLY",
                success=True,
                output={"documents": [{"title": "订单造数规范", "content": "X" * 200}]},
            ),
        )

        assert result.visibleVariables == []
        assert result.nextAction == "CALL_TASK_CONTINUE"
        assert result.resultRef["ref_type"] == "MCP_CAPABILITY_RESULT"
        assert result.resultRef["summary"]["outputKeys"] == ["documents"]
        refreshed = await task_service.get_task_run(task.taskRunId)
        assert refreshed.visibleVariables == []
        events = await task_service.list_events(task.taskRunId)
        assert events[-1].eventType == "MCP_CAPABILITY_RESULT_RECORDED"
        assert events[-1].payload["outputPreview"]["documents"][0]["title"] == "订单造数规范"
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_apply_gdp_mcp_visible_variable_result_updates_variable_stack(tmp_path):
    db_path = tmp_path / "gdp-mcp-result-variable.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="补全订单变量", envCode="DEV")
        )

        result = await apply_gdp_mcp_capability_result(
            task_service,
            GDPMCPCapabilityResultApplyRequest(
                taskRunId=task.taskRunId,
                capabilityName="gdp-mcp-variable-enrichment",
                phase=DatagenTaskPhase.PROGRESS_REFLECTION,
                outputVariablePolicy="VISIBLE_VARIABLE",
                outputSensitivity="SENSITIVE",
                success=True,
                output={"riskScore": 0.12, "customerToken": "secret-token"},
                storageRef="storage://mcp/result/1",
            ),
        )

        assert result.visibleVariables == ["riskScore", "customerToken"]
        refreshed = await task_service.get_task_run(task.taskRunId)
        variables = {item.name: item for item in refreshed.visibleVariables}
        assert variables["riskScore"].source == "${task.mcp.gdp-mcp-variable-enrichment.output.riskScore}"
        assert variables["riskScore"].sensitive is True
        assert variables["riskScore"].valuePreview is None
        assert variables["riskScore"].storageRef == "storage://mcp/result/1"
        events = await task_service.list_events(task.taskRunId)
        assert [event.eventType for event in events][-2:] == [
            "VARIABLE_STACK_UPDATED",
            "MCP_CAPABILITY_RESULT_RECORDED",
        ]
    finally:
        await close_engine()

@pytest.mark.anyio
async def test_apply_gdp_mcp_result_ignores_caller_supplied_policy(tmp_path):
    """归并策略必须以服务端 registry 为准，调用方自报的策略字段会被忽略。"""

    db_path = tmp_path / "gdp-mcp-result-policy.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="校验造数结果", envCode="DEV")
        )

        # gdp-mcp-quality-check 在 registry 注册为 SENSITIVE + SUMMARY_ONLY；
        # 调用方自报 PUBLIC + VISIBLE_VARIABLE 试图绕过脱敏并写入变量栈。
        result = await apply_gdp_mcp_capability_result(
            task_service,
            GDPMCPCapabilityResultApplyRequest(
                taskRunId=task.taskRunId,
                capabilityName="gdp-mcp-quality-check",
                phase=DatagenTaskPhase.PROGRESS_REFLECTION,
                outputVariablePolicy="VISIBLE_VARIABLE",
                outputSensitivity="PUBLIC",
                success=True,
                output={"ruleResult": "PASSED", "customerToken": "secret-token"},
            ),
        )

        assert result.visibleVariables == []
        assert result.resultRef["summary"]["outputVariablePolicy"] == "SUMMARY_ONLY"
        assert result.resultRef["summary"]["outputSensitivity"] == "SENSITIVE"
        refreshed = await task_service.get_task_run(task.taskRunId)
        assert refreshed.visibleVariables == []
        events = await task_service.list_events(task.taskRunId)
        payload = events[-1].payload
        assert payload["outputVariablePolicy"] == "SUMMARY_ONLY"
        assert payload["outputSensitivity"] == "SENSITIVE"
        assert payload["outputPreview"] is None
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_apply_gdp_mcp_result_rejects_unregistered_capability(tmp_path):
    db_path = tmp_path / "gdp-mcp-result-unknown.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        task = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(userIntent="归并未注册能力", envCode="DEV")
        )

        with pytest.raises(KeyError):
            await apply_gdp_mcp_capability_result(
                task_service,
                GDPMCPCapabilityResultApplyRequest(
                    taskRunId=task.taskRunId,
                    capabilityName="raw-unregistered-capability",
                    success=True,
                    output={"data": 1},
                ),
            )

        app = FastAPI()
        app.include_router(mcp_router, prefix="/api/v1/datagen")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/datagen/agent-mcp/capabilities/apply-result",
                json={
                    "taskRunId": task.taskRunId,
                    "capabilityName": "raw-unregistered-capability",
                    "success": True,
                    "output": {"data": 1},
                },
            )
        assert response.status_code == 404
    finally:
        await close_engine()
