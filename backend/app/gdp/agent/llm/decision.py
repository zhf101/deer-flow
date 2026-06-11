"""GDP Agent 结构化模型决策:提示词、模型工厂、决策调用与审计事件辅助。

LLM 层是叠加在确定性查表路由之上的可选增强(``gdp_agent.llm_decision_enabled``),
不需要框架式拆分——提示词、模型工厂(原 ``model.py``)、审计摘要(原 ``events.py``)
与决策调用合并在本文件,Pydantic 决策模型见 ``schemas.py``。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.gdp.agent.llm.schemas import (
    GDPGoalNormalizationDecision,
    GDPReflectionDecision,
    GDPSceneCandidateDecision,
    GDPSceneDraftEnhancementDecision,
    GDPSourceCandidateDecision,
    GDPSourceConfigDraftDecision,
)
from deerflow.config.app_config import AppConfig
from deerflow.models import create_chat_model

# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

GDP_LLM_SYSTEM_PROMPT = """你是 GDP Datagen Agent 的业务决策模型。
你只能输出一个 JSON 对象，不能输出 Markdown、代码块或额外解释。
你只负责给出结构化决策建议，不能直接执行 HTTP、SQL、写库或发布场景。
所有判断必须围绕用户造数目标、已有上下文和运行安全边界展开。"""


GDP_GOAL_NORMALIZATION_PROMPT = """请归一化用户造数目标，并抽取可用于后续造数流程的结构化信息。

输出 JSON Schema 语义：
- normalizedIntent: 清晰、完整、中文优先的目标描述，不改变用户原意
- envCode: 仅可填写 DEV、TEST、PRE、PROD 或 null
- taskType: 简短任务类型，例如 CREATE_ORDER、PAY_ORDER、QUERY_ORDER、CUSTOM
- businessDomain: 业务域，例如 交易、支付、会员、营销，无法判断填 null
- userInputs: 只抽取用户明确给出的结构化输入，不要编造
- subGoals: 可执行子目标列表，每项包含 goal、phaseHint、requiredInputs、expectedOutputs
- missingInformation: 缺失但后续可能需要追问的信息
- confidence: 0 到 1
- reason: 中文说明

用户目标：
{user_intent}

已有结构化输入：
{user_inputs}

外部已解析环境：
{env_code}
"""


GDP_REFLECTION_PROMPT = """请判断最近一次造数场景执行结果是否已经满足用户总体目标。

输出 JSON Schema 语义：
- completed: 是否已经满足总体目标
- nextAction: 只能是 FINISH_OR_VERIFY、SEARCH_NEXT_SCENE、FAIL_TASK
- reason: 中文说明
- confidence: 0 到 1
- missingInformation: 未完成时仍缺失的信息
- evidence: 支撑判断的关键字段、状态或错误

用户总体目标：
{goal}

场景执行结果：
{scene_result}

任务上下文摘要：
{context_summary}
"""


GDP_SCENE_CANDIDATE_PROMPT = """请在已有场景候选中判断哪个最适合复用。

输出 JSON Schema 语义：
- decision: 只能是 USE_SCENE、ASK_USER、NO_MATCH
- sceneCode: decision 为 USE_SCENE 或 ASK_USER 时填写候选中的 sceneCode；NO_MATCH 时为 null
- reason: 中文说明
- confidence: 0 到 1
- missingInputs: 该场景仍缺失的必填入参
- requiresUserConfirmation: 候选语义不够明确时为 true；业务写入审批由系统另行处理
- candidateRank: 只包含候选中的 sceneCode，按推荐顺序排序
- evidence: 支撑判断的候选契约字段、规则分数或变量证据

判断规则：
- 只能选择候选列表中存在的 sceneCode，不能编造。
- 如果候选不能覆盖用户总体目标，输出 NO_MATCH。
- 如果多个候选差异不足或置信度低，输出 ASK_USER。
- 不要因为场景有副作用就输出 ASK_USER，副作用会由系统审批链处理。

用户总体目标：
{goal}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

候选场景：
{candidates}

任务上下文摘要：
{context_summary}
"""


GDP_SOURCE_CANDIDATE_PROMPT = """请在 HTTP/SQL Source 候选中判断哪个最适合生成造数场景。

输出 JSON Schema 语义：
- decision: 只能是 USE_SOURCE、ASK_USER、NO_MATCH
- sourceCode: decision 为 USE_SOURCE 或 ASK_USER 时填写候选中的 sourceCode；NO_MATCH 时为 null
- sourceType: HTTP 或 SQL；无法确定时为 null
- reason: 中文说明
- confidence: 0 到 1
- missingInputs: 该 Source 生成场景仍缺失的必填入参
- requiresUserConfirmation: 候选语义不够明确时为 true；配置发布审批由系统另行处理
- generationStrategy: 使用该 Source 生成场景的简短策略
- candidateRank: 只包含候选中的 sourceCode，按推荐顺序排序
- evidence: 支撑判断的候选契约字段、规则分数或变量证据

判断规则：
- 只能选择候选列表中存在的 sourceCode，不能编造。
- 如果候选不能支撑用户总体目标，输出 NO_MATCH。
- 如果多个候选差异不足或置信度低，输出 ASK_USER。
- 不要因为 Source 会生成配置或场景就输出 ASK_USER，配置写入会由系统审批链处理。

用户总体目标：
{goal}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

候选 Source：
{candidates}

任务上下文摘要：
{context_summary}
"""


GDP_SOURCE_CONFIG_DRAFT_PROMPT = """当前没有可复用的 HTTP/SQL Source。请根据用户目标生成一个 Source 配置草稿，或说明需要追问的信息。

输出 JSON Schema 语义：
- decision: 只能是 DRAFT_SOURCE、ASK_USER、NO_DRAFT
- sourceType: DRAFT_SOURCE 时只能是 HTTP 或 SQL；无法判断时为 null
- configDraft: HttpSourceConfig 或 SqlSourceConfig 草稿 JSON；ASK_USER/NO_DRAFT 时可为空对象
- infraReadiness: 基于“基础配置摘要”判断的配置可用性，建议包含 recommendedSysCode、recommendedDatasourceCode、missingInfraFields、canUseExistingInfra、reason
- missingInformation: 仍需要用户补充的信息，例如系统编码、接口路径、请求字段、SQL 文本、数据源编码
- confidence: 0 到 1
- reason: 中文说明
- assumptions: 草稿中做出的假设，必须显式列出
- evidence: 支撑草稿的用户目标、结构化输入或变量证据

草稿边界：
- 只生成配置草稿，不会自动保存、测试、执行 HTTP 或 SQL。
- 不要编造密码、token、Authorization、Cookie 等敏感字段。
- HTTP method 只能是 GET 或 POST。
- sysCode、datasourceCode 必须优先使用基础配置摘要中已存在且启用的配置；基础配置摘要里只有 usable=true 的系统、环境、服务端点、数据源才可视为可直接复用。
- 如果目标配置不存在、未启用或未配置，不要硬编成事实，应写入 missingInformation 和 infraReadiness.missingInfraFields。
- 生成 HTTP 草稿时，必须检查目标 envCode 下是否存在该 sysCode 的 serviceEndpoint；缺失时仍可草拟 Source，但必须提示先补 serviceEndpoint。
- 生成 SQL 草稿时，必须检查目标 envCode + sysCode 下是否存在 datasourceCode；缺失时仍可草拟 Source，但必须提示先补 datasource。
- 如果缺少路径、SQL 文本、系统编码等关键事实，优先输出 ASK_USER，并把可推断字段放入 configDraft。
- HTTP 草稿尽量贴近 HttpSourceConfig：sourceCode、sourceName、tags、capabilityType、businessDomain、sideEffects、agentDescription、sysCode、path、method、requestMapping、bodySchema、responseSchema、outputMapping。
- SQL 草稿尽量贴近 SqlSourceConfig：sourceCode、sourceName、tags、capabilityType、businessDomain、sideEffects、agentDescription、sysCode、datasourceCode、operation、sqlText、parameters、resultFields。

用户总体目标：
{goal}

目标环境：
{env_code}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

任务上下文摘要：
{context_summary}

基础配置摘要：
{infra_summary}

已归一化目标：
{normalized_goal}
"""


GDP_SCENE_DRAFT_ENHANCEMENT_PROMPT = """请基于后端已经生成的 SceneDefinition 草稿，补全面向用户审批、Agent 检索和运行校验更友好的语义信息。

输出 JSON Schema 语义：
- decision: 只能是 ENHANCE_SCENE、KEEP_ORIGINAL、ASK_USER
- sceneDraft: decision 为 ENHANCE_SCENE 时填写完整 SceneDefinition JSON；其他情况可为空对象
- missingInformation: 仍需要用户补充的信息
- confidence: 0 到 1
- reason: 中文说明
- assumptions: 草稿补全中做出的假设，必须显式列出
- evidence: 支撑补全的用户目标、Source 契约、字段或上下文证据

草稿边界：
- 你只生成 SceneDefinition 草稿建议，不会自动保存、发布、执行 HTTP 或 SQL。
- sceneDraft.sceneCode 必须保持为基础草稿中的 sceneCode，不能改名、不能编造新场景编码。
- 不要删除或改写步骤 templateRef、sourceCode、sourceNameAtSnapshot、sourceUpdatedAtSnapshot 等来源快照字段。
- 不要改写 HTTP path、method、requestMapping、bodySchema、SQL 文本、datasourceCode、paramMapping 等运行行为字段。
- HTTP method 只能是 GET 或 POST。
- 不要编造密码、token、Authorization、Cookie、连接串等敏感信息。
- 优先补全 sceneName、sceneRemark、tags、businessDomain、agentDescription、inputSchema/resultSchema 字段中文名和备注、步骤 description、outputMeta。
- 如果基础草稿已经足够或无法可靠补全，输出 KEEP_ORIGINAL。
- 如果缺少关键业务事实，输出 ASK_USER，并把缺失项放入 missingInformation。

用户总体目标：
{goal}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

候选 Source 契约：
{source_contract}

后端基础 SceneDefinition 草稿：
{base_scene_draft}

任务上下文摘要：
{context_summary}

已归一化目标：
{normalized_goal}
"""

# ---------------------------------------------------------------------------
# 决策调用(每个决策一个函数)
# ---------------------------------------------------------------------------


async def normalize_gdp_goal(
    *,
    user_intent: str,
    user_inputs: dict[str, Any] | None = None,
    env_code: str | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    model: Any | None = None,
) -> GDPGoalNormalizationDecision:
    """调用模型归一化用户造数目标。"""

    prompt = GDP_GOAL_NORMALIZATION_PROMPT.format(
        user_intent=user_intent,
        user_inputs=_json_text(user_inputs or {}),
        env_code=env_code or "null",
    )
    return await _invoke_json_decision(
        output_model=GDPGoalNormalizationDecision,
        prompt=prompt,
        config=build_gdp_llm_config(
            config,
            run_name="gdp_goal_normalization",
            node_name="intake",
            decision_name="goal_normalization",
        ),
        app_config=app_config,
        model=model,
    )


async def reflect_gdp_scene_result(
    *,
    goal: str,
    scene_result: dict[str, Any],
    context_summary: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    model: Any | None = None,
) -> GDPReflectionDecision:
    """调用模型判断场景执行结果是否满足总体造数目标。"""

    prompt = GDP_REFLECTION_PROMPT.format(
        goal=goal,
        scene_result=_json_text(scene_result),
        context_summary=_json_text(context_summary or {}),
    )
    return await _invoke_json_decision(
        output_model=GDPReflectionDecision,
        prompt=prompt,
        config=build_gdp_llm_config(
            config,
            run_name="gdp_result_reflection",
            node_name="progress_reflection",
            decision_name="result_reflection",
        ),
        app_config=app_config,
        model=model,
    )


async def select_gdp_scene_candidate(
    *,
    goal: str,
    candidates: list[dict[str, Any]],
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    model: Any | None = None,
) -> GDPSceneCandidateDecision:
    """调用模型在已召回场景候选中选择最合适的场景。"""

    prompt = GDP_SCENE_CANDIDATE_PROMPT.format(
        goal=goal,
        user_inputs=_json_text(user_inputs or {}),
        visible_variables=_json_text(visible_variables or []),
        candidates=_json_text(candidates),
        context_summary=_json_text(context_summary or {}),
    )
    return await _invoke_json_decision(
        output_model=GDPSceneCandidateDecision,
        prompt=prompt,
        config=build_gdp_llm_config(
            config,
            run_name="gdp_scene_candidate_selection",
            node_name="scene_fulfillment",
            decision_name="scene_candidate_selection",
        ),
        app_config=app_config,
        model=model,
    )


async def select_gdp_source_candidate(
    *,
    goal: str,
    candidates: list[dict[str, Any]],
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    model: Any | None = None,
) -> GDPSourceCandidateDecision:
    """调用模型在 HTTP/SQL Source 候选中选择最合适的 Source。"""

    prompt = GDP_SOURCE_CANDIDATE_PROMPT.format(
        goal=goal,
        user_inputs=_json_text(user_inputs or {}),
        visible_variables=_json_text(visible_variables or []),
        candidates=_json_text(candidates),
        context_summary=_json_text(context_summary or {}),
    )
    return await _invoke_json_decision(
        output_model=GDPSourceCandidateDecision,
        prompt=prompt,
        config=build_gdp_llm_config(
            config,
            run_name="gdp_source_candidate_selection",
            node_name="scene_design",
            decision_name="source_candidate_selection",
        ),
        app_config=app_config,
        model=model,
    )


async def draft_gdp_source_config(
    *,
    goal: str,
    env_code: str | None = None,
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    infra_summary: dict[str, Any] | None = None,
    normalized_goal: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    model: Any | None = None,
) -> GDPSourceConfigDraftDecision:
    """调用模型生成 HTTP/SQL Source 配置草稿或追问信息。"""

    prompt = GDP_SOURCE_CONFIG_DRAFT_PROMPT.format(
        goal=goal,
        env_code=env_code or "null",
        user_inputs=_json_text(user_inputs or {}),
        visible_variables=_json_text(visible_variables or []),
        context_summary=_json_text(context_summary or {}),
        infra_summary=_json_text(infra_summary or {}),
        normalized_goal=_json_text(normalized_goal or {}),
    )
    return await _invoke_json_decision(
        output_model=GDPSourceConfigDraftDecision,
        prompt=prompt,
        config=build_gdp_llm_config(
            config,
            run_name="gdp_source_config_draft",
            node_name="source_config",
            decision_name="source_config_draft",
        ),
        app_config=app_config,
        model=model,
    )


async def enhance_gdp_scene_draft(
    *,
    goal: str,
    source_contract: dict[str, Any],
    base_scene_draft: dict[str, Any],
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    context_summary: dict[str, Any] | None = None,
    normalized_goal: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    app_config: AppConfig | None = None,
    model: Any | None = None,
) -> GDPSceneDraftEnhancementDecision:
    """调用模型补全 SceneDefinition 场景草稿。"""

    prompt = GDP_SCENE_DRAFT_ENHANCEMENT_PROMPT.format(
        goal=goal,
        user_inputs=_json_text(user_inputs or {}),
        visible_variables=_json_text(visible_variables or []),
        source_contract=_json_text(source_contract),
        base_scene_draft=_json_text(base_scene_draft),
        context_summary=_json_text(context_summary or {}),
        normalized_goal=_json_text(normalized_goal or {}),
    )
    return await _invoke_json_decision(
        output_model=GDPSceneDraftEnhancementDecision,
        prompt=prompt,
        config=build_gdp_llm_config(
            config,
            run_name="gdp_scene_draft_enhancement",
            node_name="scene_design",
            decision_name="scene_draft_enhancement",
        ),
        app_config=app_config,
        model=model,
    )


# ---------------------------------------------------------------------------
# 模型工厂与子运行配置(原 model.py)
# ---------------------------------------------------------------------------


def create_gdp_chat_model(
    config: RunnableConfig | None = None,
    *,
    app_config: AppConfig | None = None,
):
    """创建 GDP 图内使用的聊天模型，并继承图根追踪配置。"""

    model_name = resolve_gdp_model_name(config)
    return create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=app_config,
        attach_tracing=False,
    )


def resolve_gdp_model_name(config: RunnableConfig | None = None) -> str | None:
    """从运行配置中解析 GDP 本次调用要使用的模型名。"""

    for container_name in ("context", "configurable", "metadata"):
        container = (config or {}).get(container_name)
        if not isinstance(container, dict):
            continue
        for key in ("gdp_model_name", "model_name", "model"):
            value = container.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def build_gdp_llm_config(
    parent_config: RunnableConfig | None,
    *,
    run_name: str,
    node_name: str,
    decision_name: str,
    metadata: dict[str, Any] | None = None,
) -> RunnableConfig:
    """为单次 GDP 模型决策派生子运行配置。"""

    child_config: RunnableConfig = dict(parent_config or {})
    child_config["run_name"] = run_name
    child_config["tags"] = _append_unique(
        _as_list(child_config.get("tags")),
        [
            "gdp-datagen-agent",
            f"node:gdp.{node_name}",
            f"decision:{decision_name}",
        ],
    )
    child_metadata = dict(child_config.get("metadata") or {})
    child_metadata.update(
        {
            "gdp_node": node_name,
            "gdp_decision": decision_name,
        }
    )
    if metadata:
        child_metadata.update(metadata)
    child_config["metadata"] = child_metadata
    return child_config


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _append_unique(existing: list[Any], additions: list[str]) -> list[Any]:
    result = list(existing)
    seen = {item for item in result if isinstance(item, str)}
    for item in additions:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


# ---------------------------------------------------------------------------
# 审计事件辅助(原 events.py)
# ---------------------------------------------------------------------------


def llm_decision_payload(decision: BaseModel, *, source: str = "llm") -> dict[str, Any]:
    """生成可落 DatagenTaskEvent 的轻量模型决策摘要。"""

    payload = decision.model_dump(mode="json")
    payload["decisionSource"] = source
    return payload


def llm_failure_payload(error: Exception) -> dict[str, Any]:
    """生成模型决策失败的审计摘要。"""

    return {
        "decisionSource": "fallback_rule",
        "errorType": type(error).__name__,
        "errorMessage": str(error)[:512],
    }


# ---------------------------------------------------------------------------
# JSON 响应解析
# ---------------------------------------------------------------------------


async def _invoke_json_decision(
    *,
    output_model: type[BaseModel],
    prompt: str,
    config: RunnableConfig,
    app_config: AppConfig | None,
    model: Any | None = None,
) -> Any:
    """调用聊天模型并把 JSON 响应校验为 Pydantic 决策。"""

    chat_model = model or create_gdp_chat_model(config, app_config=app_config)
    response = await chat_model.ainvoke(
        [
            SystemMessage(content=GDP_LLM_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ],
        config=config,
    )
    content = _message_content_text(response)
    payload = _parse_json_object(content)
    return output_model.model_validate(payload)


def _message_content_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(text)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("GDP 模型决策响应必须是 JSON 对象。")
    return value


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
