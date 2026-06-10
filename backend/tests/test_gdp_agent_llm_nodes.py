"""GDP Agent 节点内模型决策接入测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.gdp.agent.nodes import scene_design as scene_design_module
from app.gdp.agent.nodes import scene_fulfillment as scene_fulfillment_module
from app.gdp.agent.nodes.intake import build_intake_node
from app.gdp.agent.nodes.progress_reflection import build_progress_reflection_node
from app.gdp.agent.nodes.scene_design import build_scene_design_node
from app.gdp.agent.nodes.scene_fulfillment import build_scene_fulfillment_node
from app.gdp.agent.nodes.source_config import build_source_config_node
from app.gdp.agent.tools.scene_design_tools import publish_scene_from_source
from app.gdp.datagen.config.base.models import (
    DatasourceResponse,
    EnvironmentResponse,
    ServiceEndpointResponse,
    SysConfigResponse,
)
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, InputFieldDefinition, InputFieldType
from app.gdp.datagen.config.httpsource.models import HttpSourceResponse
from app.gdp.datagen.config.scene.validation import validate_scene_draft, validate_scene_publish
from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


class _FakeChatModel:
    """记录模型调用并返回预设响应。"""

    def __init__(self, content: str | list[str] | None = None, error: Exception | None = None) -> None:
        if isinstance(content, list):
            self.contents = content or ["{}"]
        else:
            self.contents = [content or "{}"]
        self.error = error
        self.calls: list[dict] = []

    async def ainvoke(self, messages, config=None):
        self.calls.append({"messages": messages, "config": config})
        if self.error is not None:
            raise self.error
        index = min(len(self.calls) - 1, len(self.contents) - 1)
        return AIMessage(content=self.contents[index])


@pytest.fixture
async def task_service(tmp_path):
    db_path = tmp_path / "gdp-agent-llm-nodes.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        yield DatagenTaskService(DatagenTaskRepository(session_factory))
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_intake_uses_llm_goal_normalization_and_records_event(task_service):
    model = _FakeChatModel(
        """
        {
          "normalizedIntent": "在测试环境创建一笔订单",
          "envCode": "TEST",
          "taskType": "CREATE_ORDER",
          "businessDomain": "交易",
          "userInputs": {"userId": "U1"},
          "subGoals": [{"goal": "创建订单", "expectedOutputs": ["orderId"]}],
          "missingInformation": [],
          "confidence": 0.9,
          "reason": "用户要求创建订单，并提到了测试环境。"
        }
        """
    )
    intake = build_intake_node(task_service, llm_enabled=True, llm_model=model)

    result = await intake(
        {"messages": [HumanMessage(content="帮我在测试服给 U1 造一笔订单")]},
        {"configurable": {"thread_id": "thread-llm-intake"}, "tags": ["root"]},
    )

    task = await task_service.get_task_run(result["task_run_id"])
    events = await task_service.list_events(task.taskRunId)

    assert task.envCode == "TEST"
    assert task.normalizedGoal["normalizedIntent"] == "在测试环境创建一笔订单"
    assert task.normalizedGoal["llmDecision"]["confidence"] == 0.9
    assert result["user_inputs"] == {"userId": "U1"}
    assert result["last_llm_decision"]["decisionType"] == "goal_normalization"
    assert "LLM_GOAL_NORMALIZED" in [event.eventType for event in events]
    assert model.calls[0]["config"]["run_name"] == "gdp_goal_normalization"
    assert "node:gdp.intake" in model.calls[0]["config"]["tags"]


@pytest.mark.anyio
async def test_intake_falls_back_to_rule_env_when_llm_fails(task_service):
    intake = build_intake_node(
        task_service,
        llm_enabled=True,
        llm_model=_FakeChatModel(error=RuntimeError("模型不可用")),
    )

    result = await intake(
        {"messages": [HumanMessage(content="帮我在测试环境造一笔订单")]},
        {"configurable": {"thread_id": "thread-llm-intake-fallback"}},
    )

    task = await task_service.get_task_run(result["task_run_id"])
    events = await task_service.list_events(task.taskRunId)

    assert task.envCode == "TEST"
    assert result["last_llm_decision"]["decisionSource"] == "fallback_rule"
    assert "LLM_GOAL_NORMALIZATION_FAILED" in [event.eventType for event in events]


@pytest.mark.anyio
async def test_progress_reflection_uses_llm_decision_and_records_event(task_service):
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="造一笔已支付订单"))
    model = _FakeChatModel(
        """
        {
          "completed": false,
          "nextAction": "SEARCH_NEXT_SCENE",
          "reason": "当前场景只返回订单号，还没有支付状态。",
          "confidence": 0.86,
          "missingInformation": ["orderStatus"],
          "evidence": ["finalOutputPreview.orderId"]
        }
        """
    )
    node = build_progress_reflection_node(task_service, llm_enabled=True, llm_model=model)

    result = await node(
        {
            "task_run_id": task.taskRunId,
            "decision_context": {
                "lastSceneResult": {
                    "success": True,
                    "sceneCode": "createOrder",
                    "sceneRunId": "scene_run_1",
                    "finalOutputPreview": {"orderId": "O1"},
                }
            },
        },
        {"metadata": {"thread_id": "thread-reflect"}, "tags": ["root"]},
    )

    events = await task_service.list_events(task.taskRunId)

    assert result["current_phase"] == "SCENE_FULFILLMENT"
    assert result["decision_context"]["lastReflection"]["nextAction"] == "SEARCH_NEXT_SCENE"
    assert result["last_llm_decision"]["decisionType"] == "result_reflection"
    assert "LLM_RESULT_REFLECTED" in [event.eventType for event in events]
    assert model.calls[0]["config"]["run_name"] == "gdp_result_reflection"
    assert "node:gdp.progress_reflection" in model.calls[0]["config"]["tags"]


@pytest.mark.anyio
async def test_scene_fulfillment_uses_llm_candidate_selection(task_service, monkeypatch):
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="查询订单"))
    candidates = [_scene_candidate("queryOrderA"), _scene_candidate("queryOrderB")]
    model = _FakeChatModel(
        """
        {
          "decision": "USE_SCENE",
          "sceneCode": "queryOrderB",
          "reason": "queryOrderB 与查询订单目标更匹配。",
          "confidence": 0.91,
          "missingInputs": [],
          "requiresUserConfirmation": false,
          "candidateRank": ["queryOrderB", "queryOrderA"],
          "evidence": ["queryOrderB.score"]
        }
        """
    )

    async def fake_search_scene_contracts(*args, **kwargs):
        return {"candidates": candidates, "queryTerms": ["订单"]}

    async def fake_bind_scene_inputs(*args, **kwargs):
        assert kwargs["scene_code"] == "queryOrderB"
        return {"sceneCode": "queryOrderB", "bindings": {}, "sources": {}, "missingInputs": [], "confidence": 1.0}

    async def fake_run_datagen_scene_for_task(*args, **kwargs):
        assert kwargs["scene_code"] == "queryOrderB"
        return {
            "success": True,
            "taskStepId": "step_scene_b",
            "sceneRunId": "scene_run_b",
            "sceneCode": "queryOrderB",
            "sceneStatus": "SUCCESS",
            "outputKeys": ["orderId"],
            "finalOutputPreview": {"orderId": "O1"},
            "finalOutputSize": {"charCount": 16},
            "errors": [],
        }

    monkeypatch.setattr(scene_fulfillment_module, "search_scene_contracts", fake_search_scene_contracts)
    monkeypatch.setattr(scene_fulfillment_module, "bind_scene_inputs", fake_bind_scene_inputs)
    monkeypatch.setattr(scene_fulfillment_module, "run_datagen_scene_for_task", fake_run_datagen_scene_for_task)
    node = build_scene_fulfillment_node(
        catalog_service=object(),
        task_service=task_service,
        scene_service=object(),
        llm_enabled=True,
        llm_model=model,
    )

    result = await node({"task_run_id": task.taskRunId, "user_inputs": {}}, {"tags": ["root"]})
    events = await task_service.list_events(task.taskRunId)

    assert result["current_phase"] == "PROGRESS_REFLECTION"
    assert result["decision_context"]["selectedSceneCode"] == "queryOrderB"
    assert result["decision_context"]["llmSceneDecision"]["sceneCode"] == "queryOrderB"
    assert result["last_llm_decision"]["decisionType"] == "scene_candidate_selection"
    assert "LLM_SCENE_SELECTED" in [event.eventType for event in events]
    assert model.calls[0]["config"]["run_name"] == "gdp_scene_candidate_selection"
    assert "node:gdp.scene_fulfillment" in model.calls[0]["config"]["tags"]


@pytest.mark.anyio
async def test_scene_design_uses_llm_source_selection_before_publish_approval(task_service, monkeypatch):
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="创建订单"))
    candidates = [_source_candidate("createOrderApi"), _source_candidate("createOrderApiV2")]
    model = _FakeChatModel(
        """
        {
          "decision": "USE_SOURCE",
          "sourceCode": "createOrderApiV2",
          "sourceType": "HTTP",
          "reason": "V2 Source 的能力说明更贴近创建订单。",
          "confidence": 0.93,
          "missingInputs": [],
          "requiresUserConfirmation": false,
          "generationStrategy": "生成单步骤 HTTP 造数场景。",
          "candidateRank": ["createOrderApiV2", "createOrderApi"],
          "evidence": ["createOrderApiV2.agentDescription"]
        }
        """
    )

    async def fake_search_source_contracts(*args, **kwargs):
        return {"candidates": candidates, "queryTerms": ["订单"]}

    monkeypatch.setattr(scene_design_module, "search_source_contracts", fake_search_source_contracts)
    node = build_scene_design_node(
        catalog_service=object(),
        task_service=task_service,
        scene_service=object(),
        http_source_repository=object(),
        sql_source_repository=object(),
        llm_enabled=True,
        llm_model=model,
    )

    result = await node({"task_run_id": task.taskRunId, "user_inputs": {}}, {"tags": ["root"]})
    events = await task_service.list_events(task.taskRunId)

    assert result["current_phase"] == "WAITING_USER"
    assert result["pending_confirmation"]["questionType"] == "SCENE_PUBLISH_APPROVAL"
    assert result["decision_context"]["selectedSourceCode"] == "createOrderApiV2"
    assert result["decision_context"]["llmSourceDecision"]["sourceCode"] == "createOrderApiV2"
    assert result["last_llm_decision"]["decisionType"] == "source_candidate_selection"
    assert "LLM_SOURCE_SELECTED" in [event.eventType for event in events]
    assert model.calls[0]["config"]["run_name"] == "gdp_source_candidate_selection"
    assert "node:gdp.scene_design" in model.calls[0]["config"]["tags"]


@pytest.mark.anyio
async def test_scene_design_asks_confirmation_when_llm_source_code_misses_candidates(task_service, monkeypatch):
    """模型给出的 sourceCode 未命中候选时必须交给用户确认，不允许静默回退到第一个候选。

    正常链路上 ``_validate_source_candidate_decision`` 会先拦截无效 sourceCode；
    本测试故意削弱该校验，锁定节点选择逻辑自身的纵深防御行为。
    """

    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="创建订单"))
    candidates = [_source_candidate("createOrderApi"), _source_candidate("createOrderApiV2")]
    model = _FakeChatModel(
        """
        {
          "decision": "USE_SOURCE",
          "sourceCode": "nonexistentSource",
          "sourceType": "HTTP",
          "reason": "幻觉出来的 Source。",
          "confidence": 0.95,
          "missingInputs": [],
          "requiresUserConfirmation": false,
          "generationStrategy": "生成单步骤 HTTP 造数场景。",
          "candidateRank": [],
          "evidence": []
        }
        """
    )

    async def fake_search_source_contracts(*args, **kwargs):
        return {"candidates": candidates, "queryTerms": ["订单"]}

    monkeypatch.setattr(scene_design_module, "search_source_contracts", fake_search_source_contracts)
    monkeypatch.setattr(scene_design_module, "_validate_source_candidate_decision", lambda *args, **kwargs: None)
    node = build_scene_design_node(
        catalog_service=object(),
        task_service=task_service,
        scene_service=object(),
        http_source_repository=object(),
        sql_source_repository=object(),
        llm_enabled=True,
        llm_model=model,
    )

    result = await node({"task_run_id": task.taskRunId, "user_inputs": {}}, {"tags": ["root"]})

    assert result["current_phase"] == "WAITING_USER"
    assert result["pending_confirmation"]["questionType"] == "SOURCE_CANDIDATE_CONFIRM"
    assert result["pending_confirmation"]["details"]["confirmationReason"] == "LLM_REQUIRES_CONFIRMATION"
    assert result["pending_confirmation"]["details"]["recommended"] == "createOrderApi"


@pytest.mark.anyio
async def test_scene_design_includes_llm_enhanced_scene_draft_preview(task_service, monkeypatch):
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="创建订单"))
    scene_code = f"agent_createOrderApi_{task.taskRunId[-8:]}"
    candidates = [_source_candidate("createOrderApi")]
    model = _FakeChatModel(
        [
            """
            {
              "decision": "USE_SOURCE",
              "sourceCode": "createOrderApi",
              "sourceType": "HTTP",
              "reason": "Source 可以创建订单。",
              "confidence": 0.94,
              "missingInputs": [],
              "requiresUserConfirmation": false,
              "generationStrategy": "生成单步骤 HTTP 场景。",
              "candidateRank": ["createOrderApi"],
              "evidence": ["createOrderApi.agentDescription"]
            }
            """,
            f"""
            {{
              "decision": "ENHANCE_SCENE",
              "sceneDraft": {{
                "sceneCode": "{scene_code}",
                "sceneName": "创建订单造数场景",
                "sceneRemark": "调用交易系统创建一笔测试订单，并把订单号作为后续场景可复用变量。",
                "tags": ["订单", "创建", "自动造数"],
                "businessDomain": "交易",
                "agentDescription": "用于创建测试订单，适合需要 orderId 的后续支付或查询流程。",
                "inputSchema": [
                  {{"name": "env", "label": "环境", "type": "string", "remark": "本次造数使用的目标环境。"}},
                  {{"name": "userId", "label": "用户 ID", "type": "string", "remark": "下单用户的业务标识。"}}
                ],
                "steps": [
                  {{
                    "stepId": "createOrderApi",
                    "type": "HTTP",
                    "stepName": "调用创建订单接口",
                    "description": "向交易系统发起创建订单请求。",
                    "outputMapping": {{"orderId": "${{RES_BODY(data.orderId)}}"}},
                    "outputMeta": {{"orderId": {{"label": "订单号", "remark": "新创建订单的唯一编号。", "semanticType": "ORDER_ID"}}}}
                  }}
                ],
                "resultSchema": [
                  {{"name": "orderId", "label": "订单号", "type": "string", "remark": "新创建订单的唯一编号。"}}
                ],
                "resultMapping": {{"orderId": "${{steps.createOrderApi.outputs.orderId}}"}}
              }},
              "missingInformation": [],
              "confidence": 0.86,
              "reason": "基础草稿已有运行配置，可补全语义说明。",
              "assumptions": ["创建订单接口返回 data.orderId"],
              "evidence": ["Source 输出 orderId"]
            }}
            """,
        ]
    )

    async def fake_search_source_contracts(*args, **kwargs):
        return {"candidates": candidates, "queryTerms": ["订单"]}

    monkeypatch.setattr(scene_design_module, "search_source_contracts", fake_search_source_contracts)
    node = build_scene_design_node(
        catalog_service=object(),
        task_service=task_service,
        scene_service=object(),
        http_source_repository=_FakeHttpSourceRepository(_http_source_response("createOrderApi")),
        sql_source_repository=object(),
        llm_enabled=True,
        llm_model=model,
    )

    result = await node({"task_run_id": task.taskRunId, "user_inputs": {}}, {"tags": ["root"]})
    events = await task_service.list_events(task.taskRunId)
    details = result["pending_confirmation"]["details"]
    preview = details["sceneDraftPreview"]

    assert result["current_phase"] == "WAITING_USER"
    assert details["llmSceneDraftEnhanced"] is True
    assert preview["sceneCode"] == scene_code
    assert preview["sceneRemark"] == "调用交易系统创建一笔测试订单，并把订单号作为后续场景可复用变量。"
    assert preview["inputSchema"][1]["remark"] == "下单用户的业务标识。"
    assert preview["steps"][0]["path"] == "/orders"
    assert preview["steps"][0]["description"] == "向交易系统发起创建订单请求。"
    assert result["decision_context"]["sceneDraftPreviewSummary"]["llmEnhanced"] is True
    assert "LLM_SCENE_DRAFT_ENHANCED" in [event.eventType for event in events]
    assert model.calls[1]["config"]["run_name"] == "gdp_scene_draft_enhancement"
    assert "decision:scene_draft_enhancement" in model.calls[1]["config"]["tags"]


@pytest.mark.anyio
async def test_publish_scene_from_source_uses_llm_enhanced_draft_in_validation_chain(task_service):
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="创建订单"))
    scene_code = f"agent_createOrderApi_{task.taskRunId[-8:]}"
    model = _FakeChatModel(
        f"""
        {{
          "decision": "ENHANCE_SCENE",
          "sceneDraft": {{
            "sceneCode": "{scene_code}",
            "sceneName": "创建订单造数场景",
            "sceneRemark": "调用交易系统创建一笔测试订单，并输出可供后续流程复用的订单号。",
            "tags": ["订单", "创建", "自动造数"],
            "businessDomain": "交易",
            "agentDescription": "创建测试订单并输出 orderId。",
            "inputSchema": [
              {{"name": "env", "label": "环境", "type": "string", "remark": "本次造数使用的目标环境。"}},
              {{"name": "userId", "label": "用户 ID", "type": "string", "remark": "下单用户的业务标识。"}}
            ],
            "steps": [
              {{
                "stepId": "createOrderApi",
                "type": "HTTP",
                "stepName": "调用创建订单接口",
                "description": "向交易系统发起创建订单请求。",
                "outputMapping": {{"orderId": "${{RES_BODY(data.orderId)}}"}},
                "outputMeta": {{"orderId": {{"label": "订单号", "remark": "新创建订单的唯一编号。", "semanticType": "ORDER_ID"}}}}
              }}
            ],
            "resultSchema": [
              {{"name": "orderId", "label": "订单号", "type": "string", "remark": "新创建订单的唯一编号。"}}
            ],
            "resultMapping": {{"orderId": "${{steps.createOrderApi.outputs.orderId}}"}}
          }},
          "missingInformation": [],
          "confidence": 0.89,
          "reason": "补全字段中文说明和 Agent 描述。",
          "assumptions": [],
          "evidence": ["Source 输出 orderId"]
        }}
        """
    )
    scene_service = _ValidatingSceneService()

    result = await publish_scene_from_source(
        task_service=task_service,
        scene_service=scene_service,
        http_source_repository=_FakeHttpSourceRepository(_http_source_response("createOrderApi")),
        sql_source_repository=object(),
        task_run_id=task.taskRunId,
        goal=task.userIntent,
        source_contract=_source_candidate("createOrderApi")["contract"],
        llm_enabled=True,
        llm_model=model,
    )
    events = await task_service.list_events(task.taskRunId)

    assert result["llmEnhanced"] is True
    assert scene_service.created_scene is not None
    assert scene_service.created_scene.sceneRemark == "调用交易系统创建一笔测试订单，并输出可供后续流程复用的订单号。"
    assert scene_service.created_scene.steps[0].path == "/orders"
    assert scene_service.created_scene.steps[0].description == "向交易系统发起创建订单请求。"
    assert "LLM_SCENE_DRAFT_ENHANCED" in [event.eventType for event in events]
    assert "SCENE_DRAFT_COMPOSED" in [event.eventType for event in events]


@pytest.mark.anyio
async def test_source_config_includes_llm_draft_when_waiting_for_user(task_service):
    task = await task_service.create_task_run(DatagenTaskRunCreateRequest(userIntent="创建订单"))
    model = _FakeChatModel(
        """
        {
          "decision": "DRAFT_SOURCE",
          "sourceType": "HTTP",
          "configDraft": {
            "sourceCode": "createOrderApi",
            "sourceName": "创建订单接口",
            "tags": ["订单", "创建"],
            "capabilityType": "CREATE",
            "businessDomain": "交易",
            "sideEffects": [{"effectType": "CREATE_ORDER", "target": "orders"}],
            "agentDescription": "创建一笔测试订单并返回订单号。",
            "sysCode": "TRADE",
            "path": "/orders",
            "method": "POST",
            "outputMapping": {"orderId": "${RES_BODY(data.orderId)}"}
          },
          "infraReadiness": {
            "recommendedSysCode": "TRADE",
            "recommendedDatasourceCode": null,
            "missingInfraFields": ["HTTP.serviceEndpoint"],
            "canUseExistingInfra": false,
            "reason": "系统 TRADE 存在，但 DEV 环境服务端点缺失。"
          },
          "missingInformation": ["服务端点 Base URL"],
          "confidence": 0.82,
          "reason": "用户目标可以推导出创建订单 HTTP Source 草稿。",
          "assumptions": ["系统编码暂按 TRADE 草拟"],
          "evidence": ["用户目标包含创建订单"]
        }
        """
    )
    node = build_source_config_node(
        task_service=task_service,
        base_repository=_FakeBaseConfigRepository(
            systems=[_sys_response("TRADE", "交易系统")],
            environments=[_env_response("DEV", "开发环境")],
            endpoints=[],
            datasources=[_datasource_response("DEV", "TRADE", "ORDER_DB")],
        ),
        http_source_service=object(),
        sql_source_service=object(),
        llm_enabled=True,
        llm_model=model,
    )

    result = await node({"task_run_id": task.taskRunId, "user_inputs": {}}, {"tags": ["root"]})
    events = await task_service.list_events(task.taskRunId)

    assert result["current_phase"] == "WAITING_USER"
    assert result["pending_confirmation"]["questionType"] == "SOURCE_CONFIG_REQUIRED"
    details = result["pending_confirmation"]["details"]
    assert details["suggestedPayload"]["sourceType"] == "HTTP"
    assert details["suggestedPayload"]["config"]["sourceCode"] == "createOrderApi"
    assert details["llmDraft"]["missingInformation"] == ["服务端点 Base URL"]
    assert details["llmDraft"]["infraReadiness"]["missingInfraFields"] == ["HTTP.serviceEndpoint"]
    assert details["infraSummary"]["availableSystems"][0]["sysCode"] == "TRADE"
    assert details["infraSummary"]["availableSystems"][0]["usable"] is True
    assert details["infraSummary"]["availableDatasources"][0]["datasourceCode"] == "ORDER_DB"
    assert details["infraSummary"]["availableDatasources"][0]["usable"] is True
    assert "HTTP.serviceEndpoint" in details["infraMissingFields"]
    assert "TRADE" in model.calls[0]["messages"][1].content
    assert "ORDER_DB" in model.calls[0]["messages"][1].content
    assert "secret" not in model.calls[0]["messages"][1].content
    assert "127.0.0.1" not in model.calls[0]["messages"][1].content
    assert result["decision_context"]["llmSourceConfigDraft"]["sourceType"] == "HTTP"
    assert result["decision_context"]["sourceConfigInfraSummary"]["availableSystemCodes"] == ["TRADE"]
    assert result["last_llm_decision"]["decisionType"] == "source_config_draft"
    assert "LLM_SOURCE_CONFIG_DRAFTED" in [event.eventType for event in events]
    assert "SOURCE_CONFIG_INFRA_BASIS_RESOLVED" in [event.eventType for event in events]
    assert "SOURCE_CONFIG_SAVED" not in [event.eventType for event in events]
    assert model.calls[0]["config"]["run_name"] == "gdp_source_config_draft"
    assert "node:gdp.source_config" in model.calls[0]["config"]["tags"]


class _FakeHttpSourceRepository:
    """返回固定 HTTP Source 的测试仓储。"""

    def __init__(self, source: HttpSourceResponse) -> None:
        self.source = source

    async def get_http_source(self, source_code: str) -> HttpSourceResponse:
        assert source_code == self.source.sourceCode
        return self.source


class _FakeBaseConfigRepository:
    """返回固定基础配置列表的测试仓储。"""

    def __init__(
        self,
        *,
        systems=None,
        environments=None,
        endpoints=None,
        datasources=None,
    ) -> None:
        self.systems = systems or []
        self.environments = environments or []
        self.endpoints = endpoints or []
        self.datasources = datasources or []

    async def list_systems(self):
        return self.systems

    async def list_environments(self):
        return self.environments

    async def list_service_endpoints(self, *, env_code=None, sys_code=None):
        return [
            item
            for item in self.endpoints
            if (env_code is None or item.envCode == env_code) and (sys_code is None or item.sysCode == sys_code)
        ]

    async def list_datasources(self, *, env_code=None, sys_code=None):
        return [
            item
            for item in self.datasources
            if (env_code is None or item.envCode == env_code) and (sys_code is None or item.sysCode == sys_code)
        ]


class _ValidatingSceneService:
    """执行场景保存和发布校验的测试服务。"""

    def __init__(self) -> None:
        self.created_scene = None

    async def create_scene(self, scene, *, operator=None):
        draft_validation = validate_scene_draft(scene)
        assert draft_validation.valid
        self.created_scene = scene
        return SimpleNamespace(sceneCode=scene.sceneCode, versionNo=1, definition=scene)

    async def publish_scene(self, scene_code: str, *, operator=None):
        assert self.created_scene is not None
        assert scene_code == self.created_scene.sceneCode
        publish_validation = validate_scene_publish(self.created_scene)
        assert publish_validation.valid
        return SimpleNamespace(sceneCode=scene_code, versionNo=1, definition=self.created_scene)


def _sys_response(sys_code: str, sys_name: str) -> SysConfigResponse:
    now = datetime.now(UTC)
    return SysConfigResponse(
        id=f"sys-{sys_code}",
        sysCode=sys_code,
        sysName=sys_name,
        status=ConfigStatus.ENABLED,
        remark=f"{sys_name}基础配置",
        createdAt=now,
        updatedAt=now,
    )


def _env_response(env_code: str, env_name: str) -> EnvironmentResponse:
    now = datetime.now(UTC)
    return EnvironmentResponse(
        id=f"env-{env_code}",
        envCode=env_code,
        envName=env_name,
        status=ConfigStatus.ENABLED,
        remark=f"{env_name}基础配置",
        createdAt=now,
        updatedAt=now,
    )


def _endpoint_response(env_code: str, sys_code: str) -> ServiceEndpointResponse:
    now = datetime.now(UTC)
    return ServiceEndpointResponse(
        id=f"endpoint-{env_code}-{sys_code}",
        envCode=env_code,
        sysCode=sys_code,
        baseUrl="https://trade.example.test",
        status=ConfigStatus.ENABLED,
        createdAt=now,
        updatedAt=now,
    )


def _datasource_response(env_code: str, sys_code: str, datasource_code: str) -> DatasourceResponse:
    now = datetime.now(UTC)
    return DatasourceResponse(
        id=f"datasource-{env_code}-{sys_code}-{datasource_code}",
        envCode=env_code,
        sysCode=sys_code,
        datasourceCode=datasource_code,
        datasourceName="订单库",
        dbType="MySQL",
        host="127.0.0.1",
        port=3306,
        databaseName="order_db",
        username="order_user",
        password="secret",
        status=ConfigStatus.ENABLED,
        createdAt=now,
        updatedAt=now,
    )


def _http_source_response(source_code: str) -> HttpSourceResponse:
    now = datetime.now(UTC)
    return HttpSourceResponse(
        id=f"http-{source_code}",
        sourceCode=source_code,
        sourceName="创建订单接口",
        tags=["订单", "创建"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[{"effectType": "CREATE_ORDER", "target": "orders", "description": "创建测试订单。"}],
        agentDescription="创建一笔测试订单，返回订单号。",
        sysCode="TRADE",
        path="/orders",
        method=HttpMethod.POST,
        bodySchema=[
            InputFieldDefinition(
                name="userId",
                label="用户",
                type=InputFieldType.STRING,
                semanticType="USER_ID",
                required=False,
            )
        ],
        requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
        responseSchema=[InputFieldDefinition(name="orderId", label="订单号", type=InputFieldType.STRING, required=False)],
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        outputMeta={"orderId": {"label": "订单号", "remark": "创建后的订单号。", "semanticType": "ORDER_ID"}},
        status=ConfigStatus.ENABLED,
        createdAt=now,
        updatedAt=now,
    )


def _scene_candidate(scene_code: str) -> dict:
    return {
        "contract": {
            "sceneCode": scene_code,
            "sceneName": f"场景-{scene_code}",
            "capabilityType": "QUERY",
            "businessDomain": "交易",
            "hasSideEffects": False,
            "sideEffects": [],
        },
        "score": 0.5,
        "reasons": ["测试候选"],
        "missingInputs": [],
        "requiresConfirmation": False,
    }


def _source_candidate(source_code: str) -> dict:
    return {
        "contract": {
            "sourceType": "HTTP",
            "sourceCode": source_code,
            "sourceName": f"接口-{source_code}",
            "capabilityType": "CREATE",
            "businessDomain": "交易",
            "sysCode": "TRADE",
            "hasSideEffects": True,
            "sideEffects": [{"effectType": "CREATE_ORDER", "target": "orders"}],
        },
        "score": 0.5,
        "reasons": ["测试候选"],
        "missingInputs": [],
        "requiresConfirmation": True,
    }
