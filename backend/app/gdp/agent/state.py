"""GDP 造数 Agent 图状态。

本模块只描述 LangGraph checkpoint 需要保存的轻量运行快照。造数任务的
业务权威事实仍然以 TaskRun、TaskStep、TaskEvent 和 visibleVariables 为准。

设计边界声明
============

``GDPState`` 与通用 LeadAgent 的 ``ThreadState``（``deerflow.agents.thread_state``）
是**两套独立体系**：GDP 业务图不继承 ``sandbox`` / ``thread_data`` / ``artifacts`` /
``todos`` / ``uploaded_files`` / ``viewed_images`` 等字段，也不经过通用沙箱
（``SandboxMiddleware``）。GDP 的执行面是受控业务执行器（HTTP Source 服务、
``SqlExecutionService`` / ``SceneExecutor``），隔离边界由各执行器自身的环境白名单、
超时、脱敏和审计策略保证，**不依赖通用沙箱隔离**。不要假设 GDP 图具备
LeadAgent 的沙箱 / artifact / todo 能力。
"""

from __future__ import annotations

import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

BOUNDED_LIST_LIMIT = 50

# 进度环硬上限：单个业务节点在整条任务生命周期内被重复进入的次数上限。
# 超过即判定为阶段振荡，由 progress_reflection 终止任务，避免无界循环
# （也作为 LangGraph recursion_limit 之外更具业务语义的兜底）。
# human_confirm 不计入：它是中断节点，每次 resume 都会合法地重入一次，
# 其计数随用户交互轮次线性增长，不代表振荡。
NODE_ATTEMPT_CAP = 12
_CAP_EXEMPT_NODES = frozenset({"human_confirm"})


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

    decision_context: Annotated[dict[str, Any], merge_dict]
    normalized_goal: Annotated[dict[str, Any], merge_dict]
    last_llm_decision: Annotated[dict[str, Any], merge_dict]
    llm_decision_refs: Annotated[list[dict[str, Any]], append_bounded_dedupe]
    context_summary: Annotated[dict[str, Any], merge_dict]
    memory_context: Annotated[dict[str, Any], merge_dict]
    memory_trace: Annotated[list[dict[str, Any]], append_bounded_dedupe]
    skill_context: Annotated[dict[str, Any], merge_dict]
    skill_trace: Annotated[list[dict[str, Any]], append_bounded_dedupe]
    last_result_ref: GDPResultRef | None
    result_refs: Annotated[list[GDPResultRef], append_bounded_dedupe]
    errors: Annotated[list[dict[str, Any]], append_bounded]


def node_attempt_cap_exceeded(state: GDPState) -> str | None:
    """检测是否有业务节点重复进入次数超过硬上限。

    返回超限的节点名（用于诊断），未超限返回 None。``human_confirm`` 不计入
    （见 ``NODE_ATTEMPT_CAP`` 说明）。
    """

    attempts = state.get("node_attempts") or {}
    if not isinstance(attempts, dict):
        return None
    for node_name, count in attempts.items():
        if node_name in _CAP_EXEMPT_NODES:
            continue
        try:
            if int(count) > NODE_ATTEMPT_CAP:
                return str(node_name)
        except (TypeError, ValueError):
            continue
    return None


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
        marker = _stable_marker(item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result[-BOUNDED_LIST_LIMIT:]


def _stable_marker(value: Any) -> str:
    """生成稳定去重键，无法 JSON 化时退回字符串。"""

    try:
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
