"""datamakepool API 请求与响应 schema。"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class FlowDraftResponse(BaseModel):
    """FlowDraft 详情响应。

    这里直接对应聊天探索页读到的核心草稿结构。
    """

    id: int
    task_id: int
    status: str
    title: Optional[str] = None
    objective: Optional[str] = None
    business_graph: dict[str, Any] = Field(default_factory=dict)
    technical_graph: dict[str, Any] = Field(default_factory=dict)
    pending_issues: list[dict[str, Any]] = Field(default_factory=list)
    preflight_summary: Optional[dict[str, Any]] = None
    input_schema_draft: Optional[dict[str, Any]] = None
    output_mapping_draft: Optional[dict[str, Any]] = None
    latest_snapshot_id: Optional[int] = None


class TrialRequest(BaseModel):
    """发起 trial run 的最小请求体。"""

    entry_type: str = Field(default="chat")
    initiator_user_id: Optional[int] = None
    system_short: Optional[str] = None


class CreateRunFromTemplateRequest(BaseModel):
    """从已发布模板版本创建正式 Run 的请求体。"""

    template_revision_id: int
    initiator_user_id: Optional[int] = None
    system_short: Optional[str] = None
    input_payload: Optional[dict[str, Any]] = None


class TrialResponse(BaseModel):
    """创建 trial run 后返回的最小执行态信息。"""

    run_id: int
    entry_type: str
    status: str
    created_steps: list[dict[str, Any]] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
    final_output: Optional[dict[str, Any]] = None
    error_summary: Optional[str] = None
    steps_summary: list[dict[str, Any]] = Field(default_factory=list)


class RunDetailResponse(BaseModel):
    """单个 Run 的详情响应。"""

    run_id: int
    entry_type: str
    source_task_id: Optional[int] = None
    template_id: Optional[str] = None
    template_revision_id: Optional[str] = None
    initiator_user_id: int
    system_short: Optional[str] = None
    objective: Optional[str] = None
    input_payload: Optional[dict[str, Any]] = None
    resolved_input: Optional[dict[str, Any]] = None
    status: str
    final_output: Optional[dict[str, Any]] = None
    error_summary: Optional[str] = None
    steps_count: int


class RunStepResponse(BaseModel):
    """单个 RunStep 的响应。"""

    id: int
    run_id: int
    step_id: str
    step_type: str
    step_name: str
    status: str
    depends_on: list[Any] = Field(default_factory=list)
    resolved_execution_plan_snapshot: Optional[dict[str, Any]] = None
    asset_version_snapshot_ref: Optional[dict[str, Any]] = None
    input_snapshot: Optional[dict[str, Any]] = None
    output_snapshot: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class CreateTemplateFromRunRequest(BaseModel):
    """从成功 Run 生成模板草稿的请求体。"""

    run_id: int
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    description: Optional[str] = None
    system_short: Optional[str] = None
    business_graph_snapshot: Optional[dict[str, Any]] = None
    technical_graph: Optional[dict[str, Any]] = None
    input_schema: Optional[dict[str, Any]] = None
    output_mapping: Optional[dict[str, Any]] = None


class TemplateRevisionResponse(BaseModel):
    """模板草稿版本创建成功后的响应。"""

    template_id: int
    revision_id: int
    version_no: int
    status: str
    source_run_id: int


class TemplateSummaryResponse(BaseModel):
    """模板逻辑对象列表项。"""

    template_id: int
    name: str
    description: Optional[str] = None
    system_short: str
    owner_user_id: int
    latest_published_revision_id: Optional[int] = None
    revisions_count: int


class TemplateRevisionSummaryResponse(BaseModel):
    """模板版本列表项。"""

    revision_id: int
    template_id: int
    version_no: int
    status: str
    source_run_id: Optional[int] = None
    created_by: int
    reviewed_by: Optional[int] = None
    review_comment: Optional[str] = None
    steps_count: int


class ReviewResponse(BaseModel):
    """审核动作的最小响应。"""

    revision_id: int
    status: str
