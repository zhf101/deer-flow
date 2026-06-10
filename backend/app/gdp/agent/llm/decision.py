"""GDP Agent 结构化模型决策调用。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.gdp.agent.llm.model import build_gdp_llm_config, create_gdp_chat_model
from app.gdp.agent.llm.prompts import (
    GDP_GOAL_NORMALIZATION_PROMPT,
    GDP_LLM_SYSTEM_PROMPT,
    GDP_REFLECTION_PROMPT,
    GDP_SCENE_CANDIDATE_PROMPT,
    GDP_SCENE_DRAFT_ENHANCEMENT_PROMPT,
    GDP_SOURCE_CANDIDATE_PROMPT,
    GDP_SOURCE_CONFIG_DRAFT_PROMPT,
)
from app.gdp.agent.llm.schemas import (
    GDPGoalNormalizationDecision,
    GDPReflectionDecision,
    GDPSceneCandidateDecision,
    GDPSceneDraftEnhancementDecision,
    GDPSourceCandidateDecision,
    GDPSourceConfigDraftDecision,
)
from deerflow.config.app_config import AppConfig


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
