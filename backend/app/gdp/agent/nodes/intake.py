"""GDP Agent 任务入口节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from app.gdp.agent.llm.decision import normalize_gdp_goal
from app.gdp.agent.llm.events import llm_decision_payload, llm_failure_payload
from app.gdp.agent.llm.schemas import GDPGoalNormalizationDecision
from app.gdp.agent.middlewares.context_compression import load_gdp_context_summary
from app.gdp.agent.middlewares.memory_context import load_gdp_memory_context
from app.gdp.agent.middlewares.task_run_sync import build_gdp_task_context
from app.gdp.agent.state import GDPState
from app.gdp.datagen.agent_memory.service import GDPAgentMemoryService
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskRunCreateRequest, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from deerflow.config.app_config import AppConfig


def build_intake_node(
    task_service: DatagenTaskService,
    memory_service: GDPAgentMemoryService | None = None,
    subtask_service: DatagenTaskSubtaskService | None = None,
    *,
    app_config: AppConfig | None = None,
    llm_enabled: bool = False,
    llm_model: Any | None = None,
):
    """构造任务入口节点。"""

    async def intake(state: GDPState, config: RunnableConfig) -> GDPState:
        task_run_id = state.get("task_run_id")
        runtime_context = _extract_runtime_context(config)
        if task_run_id:
            task_run = await task_service.get_task_run(task_run_id)
            memory_context, memory_trace = await load_gdp_memory_context(
                memory_service,
                user_id=runtime_context.get("user_id"),
                user_intent=task_run.userIntent,
                env_code=task_run.envCode,
                phase=task_run.phase.value,
            )
            context_summary = await load_gdp_context_summary(task_service, subtask_service, task_run.taskRunId)
            return {
                "task_run_id": task_run.taskRunId,
                "user_intent": task_run.userIntent,
                "env_code": task_run.envCode,
                "current_phase": task_run.phase.value,
                "runtime_context": runtime_context,
                "task_context": build_gdp_task_context(task_run),
                "normalized_goal": task_run.normalizedGoal,
                "user_inputs": _extract_user_inputs(state),
                "context_summary": context_summary,
                "memory_context": memory_context,
                "memory_trace": memory_trace,
            }

        user_intent = _extract_user_intent(state)
        user_inputs = _extract_user_inputs(state)
        rule_env_code = state.get("env_code") or _extract_env_code_from_intent(user_intent)
        llm_decision, llm_error = await _try_normalize_goal_with_llm(
            enabled=llm_enabled,
            user_intent=user_intent,
            user_inputs=user_inputs,
            env_code=rule_env_code,
            config=config,
            app_config=app_config,
            model=llm_model,
        )
        effective_inputs = _merge_llm_inputs(user_inputs, llm_decision)
        effective_env_code = _select_env_code(state.get("env_code"), llm_decision, rule_env_code)
        normalized_goal = _build_normalized_goal(llm_decision)
        task_run = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(
                userIntent=user_intent,
                envCode=effective_env_code,
                inputs=effective_inputs,
                normalizedGoal=normalized_goal,
            ),
            deerflow_thread_id=runtime_context.get("thread_id"),
        )
        llm_state_update = await _record_llm_goal_event(
            task_service,
            task_run.taskRunId,
            llm_decision=llm_decision,
            llm_error=llm_error,
        )
        await task_service.move_to_phase(
            task_run.taskRunId,
            status=DatagenTaskStatus.RUNNING,
            phase=DatagenTaskPhase.SCENE_FULFILLMENT,
            event_type="PHASE_CHANGED",
            message="造数任务进入已有场景满足阶段。",
            payload={"from": DatagenTaskPhase.INTAKE.value, "to": DatagenTaskPhase.SCENE_FULFILLMENT.value},
        )
        memory_context, memory_trace = await load_gdp_memory_context(
            memory_service,
            user_id=runtime_context.get("user_id"),
            user_intent=task_run.userIntent,
            env_code=task_run.envCode,
            phase=DatagenTaskPhase.SCENE_FULFILLMENT.value,
        )
        context_summary = await load_gdp_context_summary(task_service, subtask_service, task_run.taskRunId)
        return {
            "task_run_id": task_run.taskRunId,
            "user_intent": task_run.userIntent,
            "env_code": task_run.envCode,
            "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            "runtime_context": runtime_context,
            "task_context": {
                **build_gdp_task_context(task_run),
                "status": DatagenTaskStatus.RUNNING.value,
                "phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            },
            "user_inputs": effective_inputs,
            "normalized_goal": task_run.normalizedGoal,
            **llm_state_update,
            "context_summary": context_summary,
            "memory_context": memory_context,
            "memory_trace": memory_trace,
        }

    return intake


def _extract_user_intent(state: GDPState) -> str:
    explicit = state.get("user_intent")
    if explicit and str(explicit).strip():
        return str(explicit).strip()

    messages = state.get("messages") or []
    for message in reversed(messages):
        text = _message_to_text(message)
        if text:
            return text
    raise ValueError("GDP 造数任务缺少用户目标。")


def _message_to_text(message: BaseMessage | Any) -> str:
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
        return " ".join(parts).strip()
    return str(content).strip() if content is not None else ""


def _extract_user_inputs(state: GDPState) -> dict[str, Any]:
    user_inputs = state.get("user_inputs") or {}
    return dict(user_inputs) if isinstance(user_inputs, dict) else {}


def _extract_env_code_from_intent(user_intent: str) -> str | None:
    normalized = user_intent.lower()
    env_aliases = (
        ("PROD", ("生产", "线上", "prod", "production")),
        ("PRE", ("预发", "灰度", "pre", "staging")),
        ("TEST", ("测试服", "测试环境", "测试", "test", "qa")),
        ("DEV", ("开发环境", "开发", "dev", "local")),
    )
    for env_code, aliases in env_aliases:
        if any(alias in normalized for alias in aliases):
            return env_code
    return None


async def _try_normalize_goal_with_llm(
    *,
    enabled: bool,
    user_intent: str,
    user_inputs: dict[str, Any],
    env_code: str | None,
    config: RunnableConfig,
    app_config: AppConfig | None,
    model: Any | None,
) -> tuple[GDPGoalNormalizationDecision | None, Exception | None]:
    """调用模型归一化目标，异常时交给规则路径兜底。"""

    if not enabled:
        return None, None
    try:
        decision = await normalize_gdp_goal(
            user_intent=user_intent,
            user_inputs=user_inputs,
            env_code=env_code,
            config=config,
            app_config=app_config,
            model=model,
        )
        return decision, None
    except Exception as exc:
        return None, exc


def _merge_llm_inputs(
    user_inputs: dict[str, Any],
    decision: GDPGoalNormalizationDecision | None,
) -> dict[str, Any]:
    """合并模型抽取输入和用户显式输入，用户显式输入优先。"""

    if decision is None:
        return dict(user_inputs)
    return {**decision.userInputs, **user_inputs}


def _select_env_code(
    explicit_env_code: str | None,
    decision: GDPGoalNormalizationDecision | None,
    rule_env_code: str | None,
) -> str | None:
    """按显式输入、模型识别、规则识别的顺序选择环境。"""

    if explicit_env_code:
        return str(explicit_env_code)
    if decision is not None and _valid_env_code(decision.envCode):
        return str(decision.envCode).upper()
    return rule_env_code


def _valid_env_code(value: str | None) -> bool:
    return bool(value and value.upper() in {"DEV", "TEST", "PRE", "PROD"})


def _build_normalized_goal(decision: GDPGoalNormalizationDecision | None) -> dict[str, Any]:
    """把模型归一化结果整理为 TaskRun.normalizedGoal 的扩展字段。"""

    if decision is None:
        return {}
    payload = decision.model_dump(mode="json")
    return {
        "normalizedIntent": decision.normalizedIntent,
        "taskType": decision.taskType,
        "businessDomain": decision.businessDomain,
        "subGoals": payload["subGoals"],
        "missingInformation": payload["missingInformation"],
        "llmDecision": payload,
    }


async def _record_llm_goal_event(
    task_service: DatagenTaskService,
    task_run_id: str,
    *,
    llm_decision: GDPGoalNormalizationDecision | None,
    llm_error: Exception | None,
) -> dict[str, Any]:
    """记录 intake 模型决策事件，并返回 checkpoint 轻量摘要。"""

    if llm_decision is not None:
        event = await task_service.record_event(
            task_run_id,
            event_type="LLM_GOAL_NORMALIZED",
            phase=DatagenTaskPhase.INTAKE,
            message="模型已归一化用户造数目标。",
            payload=llm_decision_payload(llm_decision),
        )
        decision_payload = llm_decision_payload(llm_decision)
        return {
            "last_llm_decision": {
                "decisionType": "goal_normalization",
                "confidence": decision_payload.get("confidence"),
                "reason": decision_payload.get("reason"),
            },
            "llm_decision_refs": [
                {
                    "eventId": event.eventId,
                    "eventType": event.eventType,
                    "decisionType": "goal_normalization",
                }
            ],
        }
    if llm_error is None:
        return {}
    event = await task_service.record_event(
        task_run_id,
        event_type="LLM_GOAL_NORMALIZATION_FAILED",
        phase=DatagenTaskPhase.INTAKE,
        message="模型归一化用户造数目标失败，已回退到规则解析。",
        payload=llm_failure_payload(llm_error),
    )
    return {
        "last_llm_decision": {
            "decisionType": "goal_normalization",
            "decisionSource": "fallback_rule",
            "errorType": type(llm_error).__name__,
        },
        "llm_decision_refs": [
            {
                "eventId": event.eventId,
                "eventType": event.eventType,
                "decisionType": "goal_normalization",
            }
        ],
    }


def _extract_runtime_context(config: RunnableConfig | None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if config is None:
        context.setdefault("assistant_id", "gdp_agent")
        return context
    for container_name in ("configurable", "context"):
        container = config.get(container_name)
        if not isinstance(container, dict):
            continue
        for key in ("thread_id", "run_id", "user_id", "operator", "assistant_id"):
            if container.get(key) is not None and key not in context:
                context[key] = str(container[key])
    context.setdefault("assistant_id", "gdp_agent")
    return context
