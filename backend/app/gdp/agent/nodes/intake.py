"""GDP Agent 任务入口节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from app.gdp.agent.state import GDPState
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskRunCreateRequest, DatagenTaskStatus
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_intake_node(task_service: DatagenTaskService):
    """构造任务入口节点。"""

    async def intake(state: GDPState, config: RunnableConfig) -> GDPState:
        task_run_id = state.get("task_run_id")
        if task_run_id:
            task_run = await task_service.get_task_run(task_run_id)
            return {
                "task_run_id": task_run.taskRunId,
                "user_intent": task_run.userIntent,
                "env_code": task_run.envCode,
                "current_phase": task_run.phase.value,
                "user_inputs": _extract_user_inputs(state),
            }

        user_intent = _extract_user_intent(state)
        user_inputs = _extract_user_inputs(state)
        task_run = await task_service.create_task_run(
            DatagenTaskRunCreateRequest(
                userIntent=user_intent,
                envCode=state.get("env_code") or _extract_env_code_from_intent(user_intent),
                inputs=user_inputs,
            ),
            deerflow_thread_id=_extract_thread_id(config),
        )
        await task_service.move_to_phase(
            task_run.taskRunId,
            status=DatagenTaskStatus.RUNNING,
            phase=DatagenTaskPhase.SCENE_FULFILLMENT,
            event_type="PHASE_CHANGED",
            message="造数任务进入已有场景满足阶段。",
            payload={"from": DatagenTaskPhase.INTAKE.value, "to": DatagenTaskPhase.SCENE_FULFILLMENT.value},
        )
        return {
            "task_run_id": task_run.taskRunId,
            "user_intent": task_run.userIntent,
            "env_code": task_run.envCode,
            "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
            "user_inputs": user_inputs,
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


def _extract_thread_id(config: RunnableConfig) -> str | None:
    for container_name in ("configurable", "context"):
        container = config.get(container_name)
        if isinstance(container, dict) and container.get("thread_id"):
            return str(container["thread_id"])
    return None
