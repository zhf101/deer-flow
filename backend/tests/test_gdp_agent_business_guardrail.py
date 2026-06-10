"""GDP Agent 业务 Guardrail 测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.tools import StructuredTool

from app.gdp.agent.middlewares.business_guardrail import (
    GDPToolApprovalContext,
    GDPToolGuardrailError,
    GuardedGDPTool,
    build_gdp_tool_approval_key,
    evaluate_gdp_tool_guardrail,
    user_submitted_config_write_context,
    user_submitted_probe_context,
    wrap_gdp_tool_guardrail,
)
from app.gdp.agent.tools.registry import get_gdp_tool_specs, get_gdp_tools
from app.gdp.datagen.config.task.models import DatagenTaskPhase


def test_evaluate_gdp_tool_guardrail_allows_read_tool_without_approval():
    spec = _spec("get_scene_contract")

    decision = evaluate_gdp_tool_guardrail(spec, {"scene_code": "createOrder"})

    assert decision.allowed is True
    assert decision.reason == "无副作用工具允许执行。"


def test_evaluate_gdp_tool_guardrail_blocks_write_tool_without_approval():
    spec = _spec("run_datagen_scene_for_task")

    decision = evaluate_gdp_tool_guardrail(spec, _scene_run_input())

    assert decision.allowed is False
    assert decision.requiresApproval is True
    assert decision.approvalKey == build_gdp_tool_approval_key(spec, _scene_run_input())


def test_evaluate_gdp_tool_guardrail_allows_write_tool_by_approval_key():
    spec = _spec("run_datagen_scene_for_task")
    approval_key = build_gdp_tool_approval_key(spec, _scene_run_input())

    decision = evaluate_gdp_tool_guardrail(
        spec,
        _scene_run_input(),
        GDPToolApprovalContext(approvedApprovalKeys=[approval_key]),
    )

    assert decision.allowed is True
    assert decision.reason == "工具调用幂等键已通过审批。"


@pytest.mark.anyio
async def test_guarded_tool_blocks_before_calling_underlying_tool():
    spec = _spec("run_datagen_scene_for_task")
    called = {"value": False}

    async def _write_tool(
        task_run_id: str,
        scene_code: str,
        env_code: str,
        input_params: dict[str, str],
    ) -> dict[str, bool]:
        called["value"] = True
        return {"ok": True}

    tool = StructuredTool.from_function(
        coroutine=_write_tool,
        name="run_datagen_scene_for_task",
        description="执行场景。",
    )
    guarded = wrap_gdp_tool_guardrail(tool, spec)

    with pytest.raises(GDPToolGuardrailError):
        await guarded.ainvoke(_scene_run_input())

    assert called["value"] is False


@pytest.mark.anyio
async def test_guarded_tool_allows_approved_tool_name():
    spec = _spec("run_datagen_scene_for_task")

    async def _write_tool(
        task_run_id: str,
        scene_code: str,
        env_code: str,
        input_params: dict[str, str],
    ) -> dict[str, bool]:
        return {"ok": True}

    tool = StructuredTool.from_function(
        coroutine=_write_tool,
        name="run_datagen_scene_for_task",
        description="执行场景。",
    )
    guarded = wrap_gdp_tool_guardrail(
        tool,
        spec,
        GDPToolApprovalContext(approvedToolNames=["run_datagen_scene_for_task"]),
    )

    assert await guarded.ainvoke(_scene_run_input()) == {"ok": True}


@pytest.mark.anyio
async def test_get_gdp_tools_returns_guarded_tools_by_default():
    tools = get_gdp_tools(_services(), DatagenTaskPhase.SCENE_EXECUTING)
    tool = next(item for item in tools if item.name == "run_datagen_scene_for_task")

    assert isinstance(tool, GuardedGDPTool)
    with pytest.raises(GDPToolGuardrailError):
        await tool.ainvoke(_scene_run_input())


def test_get_gdp_tools_can_return_raw_tools_for_internal_callers():
    tools = get_gdp_tools(_services(), DatagenTaskPhase.SCENE_EXECUTING, guardrails_enabled=False)

    assert not any(isinstance(tool, GuardedGDPTool) for tool in tools)


def _spec(name: str):
    return next(item for item in get_gdp_tool_specs() if item.name == name)


def _scene_run_input() -> dict[str, object]:
    return {
        "task_run_id": "task_1",
        "scene_code": "createOrder",
        "env_code": "DEV",
        "input_params": {"userId": "U1"},
    }


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


def test_user_submitted_contexts_follow_submit_as_confirm_policy():
    """「提交即确认」策略的标准审批上下文：配置写与探测各自只放行对应副作用等级。"""

    config_context = user_submitted_config_write_context(source="source_config 节点", operator="op-1")
    assert config_context.allowConfigWrite is True
    assert config_context.allowBusinessWrite is False
    assert config_context.operator == "op-1"
    assert "提交即确认" in (config_context.reason or "")

    probe_context = user_submitted_probe_context(source="Agent API")
    assert probe_context.allowBusinessWrite is True
    assert probe_context.allowConfigWrite is False
    assert "提交即确认" in (probe_context.reason or "")


def test_config_write_approval_context_is_centralized():
    """配置写放行必须经 user_submitted_config_write_context 构造，禁止散落手写 allowConfigWrite=True。"""

    from pathlib import Path

    gdp_root = Path(__file__).resolve().parent.parent / "app" / "gdp"
    offenders = [
        str(path.relative_to(gdp_root))
        for path in sorted(gdp_root.rglob("*.py"))
        if path.name != "business_guardrail.py" and "allowConfigWrite=True" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"以下文件绕过统一护栏入口手写 allowConfigWrite=True：{offenders}"
