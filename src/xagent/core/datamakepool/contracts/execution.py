from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EditableFieldSpec(BaseModel):
    name: str
    mode: Literal["direct_edit", "needs_resolution"]
    editor: Optional[str] = None
    validation_rules: list[dict[str, Any]] = Field(default_factory=list)


class ResolverOutput(BaseModel):
    resolution_status: str
    blocking_issues: list[dict[str, Any]] = Field(default_factory=list)
    resolution_rationale: dict[str, Any] = Field(default_factory=dict)
    resolved_execution_plan: dict[str, Any] = Field(default_factory=dict)
    editable_fields: list[EditableFieldSpec] = Field(default_factory=list)


class ExecutorInput(BaseModel):
    resolved_execution_plan: dict[str, Any]
    runtime_values: dict[str, Any] = Field(default_factory=dict)


class ExecutorOutput(BaseModel):
    execution_status: str
    extracted_outputs: dict[str, Any] = Field(default_factory=dict)
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    error_info: Optional[dict[str, Any]] = None
    audit_payload: Optional[dict[str, Any]] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
