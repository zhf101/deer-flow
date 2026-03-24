from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EditableFieldSpec(BaseModel):
    """模板草稿中单个可编辑字段的元信息。"""

    name: str
    # direct_edit 表示允许直接改；needs_resolution 表示修改后必须重新收敛。
    mode: Literal["direct_edit", "needs_resolution"]
    editor: Optional[str] = None
    validation_rules: list[dict[str, Any]] = Field(default_factory=list)


class ResolverOutput(BaseModel):
    """Resolver 的统一输出。

    这里不是单纯返回最终方案，而是要同时返回阻塞项、收敛依据和可编辑字段，
    供预检、模板草稿和审核展示共同使用。
    """

    resolution_status: str
    blocking_issues: list[dict[str, Any]] = Field(default_factory=list)
    resolution_rationale: dict[str, Any] = Field(default_factory=dict)
    resolved_execution_plan: dict[str, Any] = Field(default_factory=dict)
    editable_fields: list[EditableFieldSpec] = Field(default_factory=list)


class ExecutorInput(BaseModel):
    """Executor 的统一输入。

    执行层只消费已经固化的执行方案和运行时值，
    不再回看 design_intent，避免设计层与执行层重新耦合。
    """

    resolved_execution_plan: dict[str, Any]
    runtime_values: dict[str, Any] = Field(default_factory=dict)


class ExecutorOutput(BaseModel):
    """Executor 的统一输出。

    输出不仅要有执行状态，还要有可回放、可审计、可展示的运行结果快照。
    """

    execution_status: str
    extracted_outputs: dict[str, Any] = Field(default_factory=dict)
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    error_info: Optional[dict[str, Any]] = None
    audit_payload: Optional[dict[str, Any]] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
