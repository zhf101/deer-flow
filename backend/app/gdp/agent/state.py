"""GDP 造数 Agent 图状态。

本模块只描述 LangGraph checkpoint 需要保存的轻量运行快照。造数任务的
业务权威事实仍然以 TaskRun、TaskStep、TaskEvent 和 visibleVariables 为准。
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


BOUNDED_LIST_LIMIT = 50


class GDPRuntimeContext(TypedDict, total=False):
    """本次图运行的外部运行时上下文。"""

    thread_id: str
    run_id: str
    user_id: str | None
    operator: str | None
    assistant_id: str


class GDPTaskContext(TypedDict, total=False):
    """当前造数任务在业务控制面的轻量上下文。"""

    task_run_id: str
    status: str
    phase: str
    env_code: str | None
    deerflow_thread_id: str | None
    deerflow_run_id: str | None
    last_checkpoint_id: str | None


class GDPConfirmation(TypedDict, total=False):
    """等待用户确认时写入 checkpoint 的中断摘要。"""

    taskRunId: str
    phase: str
    resumePhase: str | None
    questionType: str
    question: str
    details: dict[str, Any]
    emitted: bool


class GDPResultRef(TypedDict, total=False):
    """节点结果引用，避免把大结果长期塞进 checkpoint。"""

    ref_type: str
    task_step_id: str | None
    scene_run_id: str | None
    scene_code: str | None
    source_code: str | None
    artifact_id: str | None
    summary: dict[str, Any]


class GDPState(TypedDict, total=False):
    """GDP 造数业务图的轻量状态。"""

    messages: Annotated[list[BaseMessage], add_messages]

    runtime_context: Annotated[GDPRuntimeContext, merge_dict]
    task_context: Annotated[GDPTaskContext, merge_dict]

    task_run_id: str
    user_intent: str
    env_code: str
    current_phase: str
    phase_history: Annotated[list[dict[str, Any]], append_bounded_dedupe]
    node_attempts: Annotated[dict[str, int], merge_counter]

    pending_confirmation: GDPConfirmation | None
    confirmation_result: Any
    user_inputs: Annotated[dict[str, Any], merge_user_inputs]
    inputs: dict[str, Any]

    decision_context: Annotated[dict[str, Any], merge_dict]
    context_summary: Annotated[dict[str, Any], merge_dict]
    memory_context: Annotated[dict[str, Any], merge_dict]
    memory_trace: Annotated[list[dict[str, Any]], append_bounded_dedupe]
    last_result_ref: GDPResultRef | None
    result_refs: Annotated[list[GDPResultRef], append_bounded_dedupe]
    errors: Annotated[list[dict[str, Any]], append_bounded]


def merge_dict(existing: dict | None, new: dict | None) -> dict:
    """合并普通字典，适合轻量上下文增量写入。"""

    if existing is None:
        return dict(new or {})
    if new is None:
        return existing
    return {**existing, **new}


def merge_user_inputs(existing: dict | None, new: dict | None) -> dict:
    """合并用户输入，新的显式回复覆盖旧值。"""

    merged = dict(existing or {})
    merged.update(new or {})
    return merged


def merge_counter(existing: dict[str, int] | None, new: dict[str, int] | None) -> dict[str, int]:
    """合并节点尝试次数计数。"""

    result = dict(existing or {})
    for key, value in (new or {}).items():
        result[key] = result.get(key, 0) + int(value)
    return result


def append_bounded(existing: list | None, new: list | None) -> list:
    """追加列表并限制 checkpoint 中的历史长度。"""

    result = list(existing or [])
    result.extend(new or [])
    return result[-BOUNDED_LIST_LIMIT:]


def append_bounded_dedupe(existing: list | None, new: list | None) -> list:
    """追加列表并按 JSON 形态去重，保留最近的轻量历史。"""

    result: list[Any] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(new or []):
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result[-BOUNDED_LIST_LIMIT:]
