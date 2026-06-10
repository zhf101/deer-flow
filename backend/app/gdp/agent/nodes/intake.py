"""GDP Agent 任务入口节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.context_compression import load_gdp_context_summary
from app.gdp.agent.middlewares.memory_context import load_gdp_memory_context
from app.gdp.agent.state import GDPState
from app.gdp.datagen.agent_memory.service import GDPAgentMemoryService
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskRunCreateRequest, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService


def build_intake_node(
    task_service: DatagenTaskService,
    memory_service: GDPAgentMemoryService | None = None,
    subtask_service: DatagenTaskSubtaskService | None = None,
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
                "task_context": _build_task_context(task_run),
                "user_inputs": _extract_user_inputs(state),
                "context_summary": context_summary,
                "memory_context": memory_context,
                "memory_trace": memory_trace,
            }

        user_intent = _extract_user_intent(state)
        user_inputs = _extract_user_inputs(state)
        task_run = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(
                userIntent=user_intent,
                envCode=state.get("env_code") or _extract_env_code_from_intent(user_intent),
                inputs=user_inputs,
            ),
            deerflow_thread_id=runtime_context.get("thread_id"),
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
                **_build_task_context(task_run),
                "status": DatagenTaskStatus.RUNNING.value,
                "phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            },
            "user_inputs": user_inputs,
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
    user_inputs = state.get("user_inputs") or state.get("inputs") or {}
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


def _build_task_context(task_run: Any) -> dict[str, Any]:
    return {
        "task_run_id": task_run.taskRunId,
        "status": task_run.status.value,
        "phase": task_run.phase.value,
        "env_code": task_run.envCode,
        "deerflow_thread_id": task_run.deerflowThreadId,
        "deerflow_run_id": task_run.deerflowRunId,
        "last_checkpoint_id": task_run.lastCheckpointId,
    }
