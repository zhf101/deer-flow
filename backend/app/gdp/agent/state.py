"""GDP 造数 Agent 图状态。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GDPState(TypedDict, total=False):
    """GDP 造数业务图的轻量状态。"""

    messages: Annotated[list[BaseMessage], add_messages]
    task_run_id: str
    user_intent: str
    env_code: str
    current_phase: str
    pending_confirmation: dict[str, Any]
    confirmation_result: Any
    last_tool_result: dict[str, Any]
    user_inputs: dict[str, Any]
    inputs: dict[str, Any]
