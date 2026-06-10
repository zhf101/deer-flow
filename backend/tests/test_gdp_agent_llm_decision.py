"""GDP Agent 模型决策调用测试。"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from app.gdp.agent.llm.decision import (
    draft_gdp_source_config,
    enhance_gdp_scene_draft,
    normalize_gdp_goal,
    reflect_gdp_scene_result,
    select_gdp_scene_candidate,
    select_gdp_source_candidate,
)


class _FakeChatModel:
    """记录模型调用并返回预设响应。"""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def ainvoke(self, messages, config=None):
        self.calls.append({"messages": messages, "config": config})
        return AIMessage(content=self.content)


@pytest.mark.anyio
async def test_normalize_gdp_goal_parses_json_and_inherits_trace_config():
    model = _FakeChatModel(
        """```json
        {
          "normalizedIntent": "在测试环境创建一笔已支付订单",
          "envCode": "TEST",
          "taskType": "CREATE_PAID_ORDER",
          "businessDomain": "交易",
          "userInputs": {"userId": "U1"},
          "subGoals": [{"goal": "创建订单", "phaseHint": "SCENE_FULFILLMENT"}],
          "missingInformation": [],
          "confidence": 0.91,
          "reason": "用户明确要求测试环境和已支付订单。"
        }
        ```"""
    )
    parent_config = {
        "tags": ["root-tag"],
        "callbacks": ["root-callback"],
        "metadata": {"thread_id": "thread-1"},
    }

    decision = await normalize_gdp_goal(
        user_intent="帮我在测试服造一笔已支付订单",
        user_inputs={},
        config=parent_config,
        model=model,
    )

    assert decision.envCode == "TEST"
    assert decision.subGoals[0].goal == "创建订单"
    call_config = model.calls[0]["config"]
    assert call_config["run_name"] == "gdp_goal_normalization"
    assert call_config["callbacks"] == ["root-callback"]
    assert "root-tag" in call_config["tags"]
    assert "node:gdp.intake" in call_config["tags"]
    assert "decision:goal_normalization" in call_config["tags"]
    assert call_config["metadata"]["thread_id"] == "thread-1"
    assert call_config["metadata"]["gdp_decision"] == "goal_normalization"


@pytest.mark.anyio
async def test_reflect_gdp_scene_result_parses_model_decision():
    model = _FakeChatModel(
        """
        {
          "completed": false,
          "nextAction": "SEARCH_NEXT_SCENE",
          "reason": "当前只有订单号，还没有支付状态。",
          "confidence": 0.88,
          "missingInformation": ["orderStatus"],
          "evidence": ["finalOutputPreview.orderId"]
        }
        """
    )

    decision = await reflect_gdp_scene_result(
        goal="造一笔已支付订单",
        scene_result={"success": True, "finalOutputPreview": {"orderId": "O1"}},
        config={"metadata": {"thread_id": "thread-2"}},
        model=model,
    )

    assert decision.completed is False
    assert decision.nextAction == "SEARCH_NEXT_SCENE"
    assert decision.missingInformation == ["orderStatus"]
    call_config = model.calls[0]["config"]
    assert call_config["run_name"] == "gdp_result_reflection"
    assert "node:gdp.progress_reflection" in call_config["tags"]
    assert call_config["metadata"]["gdp_decision"] == "result_reflection"


@pytest.mark.anyio
async def test_select_gdp_scene_candidate_uses_scene_trace_tags():
    model = _FakeChatModel(
        """
        {
          "decision": "USE_SCENE",
          "sceneCode": "queryOrderB",
          "reason": "第二个场景的结果字段更贴近目标。",
          "confidence": 0.87,
          "missingInputs": [],
          "requiresUserConfirmation": false,
          "candidateRank": ["queryOrderB", "queryOrderA"],
          "evidence": ["queryOrderB.resultSchema.orderId"]
        }
        """
    )

    decision = await select_gdp_scene_candidate(
        goal="查询订单",
        candidates=[{"contract": {"sceneCode": "queryOrderA"}}, {"contract": {"sceneCode": "queryOrderB"}}],
        config={"tags": ["root"], "metadata": {"thread_id": "thread-scene"}},
        model=model,
    )

    assert decision.sceneCode == "queryOrderB"
    call_config = model.calls[0]["config"]
    assert call_config["run_name"] == "gdp_scene_candidate_selection"
    assert "node:gdp.scene_fulfillment" in call_config["tags"]
    assert call_config["metadata"]["gdp_decision"] == "scene_candidate_selection"


@pytest.mark.anyio
async def test_select_gdp_source_candidate_uses_source_trace_tags():
    model = _FakeChatModel(
        """
        {
          "decision": "USE_SOURCE",
          "sourceCode": "createOrderApiV2",
          "sourceType": "HTTP",
          "reason": "V2 Source 的输出字段更完整。",
          "confidence": 0.9,
          "missingInputs": [],
          "requiresUserConfirmation": false,
          "generationStrategy": "生成单步骤 HTTP 场景。",
          "candidateRank": ["createOrderApiV2", "createOrderApi"],
          "evidence": ["createOrderApiV2.outputMapping.orderId"]
        }
        """
    )

    decision = await select_gdp_source_candidate(
        goal="创建订单",
        candidates=[{"contract": {"sourceCode": "createOrderApi"}}, {"contract": {"sourceCode": "createOrderApiV2"}}],
        config={"tags": ["root"], "metadata": {"thread_id": "thread-source"}},
        model=model,
    )

    assert decision.sourceCode == "createOrderApiV2"
    call_config = model.calls[0]["config"]
    assert call_config["run_name"] == "gdp_source_candidate_selection"
    assert "node:gdp.scene_design" in call_config["tags"]
    assert call_config["metadata"]["gdp_decision"] == "source_candidate_selection"


@pytest.mark.anyio
async def test_draft_gdp_source_config_uses_source_config_trace_tags():
    model = _FakeChatModel(
        """
        {
          "decision": "DRAFT_SOURCE",
          "sourceType": "HTTP",
          "configDraft": {
            "sourceCode": "createOrderApi",
            "sourceName": "创建订单接口",
            "sysCode": "TRADE",
            "path": "/orders",
            "method": "POST"
          },
          "infraReadiness": {
            "recommendedSysCode": "TRADE",
            "missingInfraFields": [],
            "canUseExistingInfra": true,
            "reason": "基础配置摘要中 TRADE 可用。"
          },
          "missingInformation": ["响应字段映射"],
          "confidence": 0.78,
          "reason": "用户目标明确要求创建订单，但响应结构仍需确认。",
          "assumptions": ["交易系统编码为 TRADE"],
          "evidence": ["目标包含创建订单"]
        }
        """
    )

    decision = await draft_gdp_source_config(
        goal="创建订单",
        env_code="DEV",
        infra_summary={"availableSystems": [{"sysCode": "TRADE", "sysName": "交易系统"}]},
        config={"tags": ["root"], "metadata": {"thread_id": "thread-source-config"}},
        model=model,
    )

    assert decision.sourceType == "HTTP"
    assert decision.configDraft["sourceCode"] == "createOrderApi"
    assert decision.infraReadiness["recommendedSysCode"] == "TRADE"
    call_config = model.calls[0]["config"]
    assert "TRADE" in model.calls[0]["messages"][1].content
    assert call_config["run_name"] == "gdp_source_config_draft"
    assert "node:gdp.source_config" in call_config["tags"]
    assert call_config["metadata"]["gdp_decision"] == "source_config_draft"


@pytest.mark.anyio
async def test_enhance_gdp_scene_draft_uses_scene_design_trace_tags():
    model = _FakeChatModel(
        """
        {
          "decision": "ENHANCE_SCENE",
          "sceneDraft": {
            "sceneCode": "agent_createOrder_001",
            "sceneName": "创建订单造数场景",
            "sceneRemark": "用于创建测试订单并返回订单号。",
            "tags": ["订单", "造数"],
            "agentDescription": "创建一笔测试订单并输出 orderId。",
            "inputSchema": [],
            "steps": [],
            "resultMapping": {}
          },
          "missingInformation": [],
          "confidence": 0.84,
          "reason": "基础草稿可补全业务说明。",
          "assumptions": ["订单接口已由 Source 校验"],
          "evidence": ["Source 名称包含创建订单"]
        }
        """
    )

    decision = await enhance_gdp_scene_draft(
        goal="创建订单",
        source_contract={"sourceCode": "createOrderApi", "sourceType": "HTTP"},
        base_scene_draft={"sceneCode": "agent_createOrder_001"},
        config={"tags": ["root"], "metadata": {"thread_id": "thread-scene-draft"}},
        model=model,
    )

    assert decision.decision == "ENHANCE_SCENE"
    assert decision.sceneDraft["sceneCode"] == "agent_createOrder_001"
    call_config = model.calls[0]["config"]
    assert call_config["run_name"] == "gdp_scene_draft_enhancement"
    assert "node:gdp.scene_design" in call_config["tags"]
    assert "decision:scene_draft_enhancement" in call_config["tags"]
    assert call_config["metadata"]["gdp_decision"] == "scene_draft_enhancement"
