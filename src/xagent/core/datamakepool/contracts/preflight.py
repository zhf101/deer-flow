from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreflightIssue(BaseModel):
    """单个预检问题。

    预检问题既用于阻塞试跑，也用于驱动前台“回聊天修正 / 去节点详情修正”的推荐路径。
    """

    issue_type: str
    step_id: str | None = None
    message: str
    severity: str = "error"
    suggested_action: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PreflightResult(BaseModel):
    """FlowDraft 进入 trial 前的整体收敛检查结果。"""

    is_runnable: bool
    issues: list[PreflightIssue] = Field(default_factory=list)
    grouped_by_type: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    grouped_by_step: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)
