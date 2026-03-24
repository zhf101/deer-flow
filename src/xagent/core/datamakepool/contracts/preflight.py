from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreflightIssue(BaseModel):
    issue_type: str
    step_id: str | None = None
    message: str
    severity: str = "error"
    suggested_action: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PreflightResult(BaseModel):
    is_runnable: bool
    issues: list[PreflightIssue] = Field(default_factory=list)
    grouped_by_type: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    grouped_by_step: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    suggested_actions: list[str] = Field(default_factory=list)
