"""datamakepool API 请求与响应 schema。"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """创建探索态会话的最小请求体。"""

    title: Optional[str] = None
    objective: Optional[str] = None


class ConversationResponse(BaseModel):
    """探索态会话摘要。"""

    conversation_id: int
    task_id: int
    flowdraft_id: int
    title: str
    objective: Optional[str] = None
    flowdraft_status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationMessageRequest(BaseModel):
    """探索态会话追加消息请求。"""

    content: str = Field(min_length=1)


class ConversationMessageResponse(BaseModel):
    """探索态会话追加消息后的最小响应。"""

    conversation_id: int
    message_id: int
    assistant_message_id: Optional[int] = None
    flowdraft_id: int
    flowdraft_status: str
    title: Optional[str] = None
    objective: Optional[str] = None
    assistant_summary: Optional[str] = None
    pending_issues: list[dict[str, Any]] = Field(default_factory=list)
    latest_snapshot_id: Optional[int] = None


class HTTPAssetCreateRequest(BaseModel):
    """创建 HTTP 资产请求。"""

    name: str = Field(min_length=1)
    description: Optional[str] = None
    system_short: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    method: str = Field(min_length=1)
    path_template: str = Field(min_length=1)
    query_template: dict[str, Any] = Field(default_factory=dict)
    headers_template: dict[str, Any] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)
    request_schema: dict[str, Any] = Field(default_factory=dict)
    auth_type: Optional[str] = None
    auth_config_ciphertext: Optional[str] = None
    response_extraction_rules: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, gt=0)
    max_response_bytes: int = Field(default=1048576, gt=0)
    enabled: bool = True


class HTTPAssetUpdateRequest(BaseModel):
    """更新 HTTP 资产请求。

    当前按完整更新口径处理，避免在第一版资产管理动作里引入复杂 patch 语义。
    """

    name: str = Field(min_length=1)
    description: Optional[str] = None
    system_short: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    method: str = Field(min_length=1)
    path_template: str = Field(min_length=1)
    query_template: dict[str, Any] = Field(default_factory=dict)
    headers_template: dict[str, Any] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)
    request_schema: dict[str, Any] = Field(default_factory=dict)
    auth_type: Optional[str] = None
    auth_config_ciphertext: Optional[str] = None
    response_extraction_rules: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, gt=0)
    max_response_bytes: int = Field(default=1048576, gt=0)
    enabled: bool = True


class HTTPAssetSummaryResponse(BaseModel):
    """HTTP 资产列表项 / 创建结果。"""

    asset_id: int
    name: str
    description: Optional[str] = None
    system_short: str
    method: str
    base_url: str
    path_template: str
    enabled: bool
    owner_user_id: int
    updated_at: Optional[str] = None


class HTTPAssetDetailResponse(HTTPAssetSummaryResponse):
    """HTTP 资产详情。"""

    query_template: dict[str, Any] = Field(default_factory=dict)
    headers_template: dict[str, Any] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)
    request_schema: dict[str, Any] = Field(default_factory=dict)
    auth_type: Optional[str] = None
    auth_config_configured: bool = False
    response_extraction_rules: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int
    max_response_bytes: int
    created_at: Optional[str] = None


class HTTPAssetTestRequest(BaseModel):
    """HTTP 资产测试请求。"""

    query_params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, Any] = Field(default_factory=dict)
    body: Optional[Any] = None
    response_extraction_rules: dict[str, Any] = Field(default_factory=dict)


class HTTPAssetTestResponse(BaseModel):
    """HTTP 资产测试结果。"""

    asset_id: int
    execution_status: str
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    response_snapshot: Optional[dict[str, Any]] = None
    extracted_outputs: dict[str, Any] = Field(default_factory=dict)
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    error_info: Optional[dict[str, Any]] = None


class AssetDeleteResponse(BaseModel):
    """资产删除结果。"""

    asset_id: int
    deleted: bool = True


class SQLAssetCreateRequest(BaseModel):
    """创建 SQL 资产及初始版本请求。"""

    name: str = Field(min_length=1)
    description: Optional[str] = None
    system_short: str = Field(min_length=1)
    connection_config: dict[str, Any] = Field(default_factory=dict)
    whitelist: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    mutation_enabled: bool = False


class SQLAssetCreateResponse(BaseModel):
    """创建 SQL 资产后的最小响应。"""

    asset_id: int
    version_id: int
    version_no: int
    status: str


class SQLAssetVersionCreateRequest(BaseModel):
    """创建 SQL 资产新版本请求。"""

    connection_config: dict[str, Any] = Field(default_factory=dict)
    whitelist: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    mutation_enabled: bool = False


class SQLAssetVersionUpdateRequest(BaseModel):
    """更新 SQL 资产草稿版本请求。"""

    connection_config: Optional[dict[str, Any]] = None
    whitelist: Optional[list[str]] = None
    blacklist: Optional[list[str]] = None
    mutation_enabled: Optional[bool] = None


class SQLAssetVersionCreateResponse(BaseModel):
    """SQL 资产版本新增 / 复制结果。"""

    asset_id: int
    version_id: int
    version_no: int
    status: str
    copied_from_version_id: Optional[int] = None


class SQLAssetSummaryResponse(BaseModel):
    """SQL 资产逻辑对象列表项。"""

    asset_id: int
    name: str
    description: Optional[str] = None
    system_short: str
    owner_user_id: int
    current_active_version_id: Optional[int] = None
    versions_count: int
    latest_version_id: Optional[int] = None
    latest_version_no: Optional[int] = None
    latest_version_status: Optional[str] = None
    updated_at: Optional[str] = None


class SQLAssetVersionReviewResponse(BaseModel):
    """SQL 资产版本审核动作响应。"""

    asset_id: int
    version_id: int
    version_no: int
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None


class SQLAssetVersionSummaryResponse(BaseModel):
    """SQL 资产版本列表项。"""

    version_id: int
    asset_id: int
    version_no: int
    status: str
    mutation_enabled: bool
    created_by: int
    reviewed_by: Optional[int] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None


class SQLAssetVersionDetailResponse(SQLAssetVersionSummaryResponse):
    """SQL 资产版本详情。"""

    system_short: str
    connection_config: dict[str, Any] = Field(default_factory=dict)
    whitelist: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    is_active_version: bool = False


class SQLAssetVersionTestRequest(BaseModel):
    """SQL 资产版本测试请求。"""

    test_mode: Literal["connection", "sql"] = "connection"
    sql: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class SQLAssetVersionTestResponse(BaseModel):
    """SQL 资产版本测试结果。"""

    asset_id: int
    version_id: int
    test_mode: str
    execution_status: str
    connection_summary: Optional[dict[str, Any]] = None
    sql_snapshot: Optional[dict[str, Any]] = None
    result_preview: Optional[dict[str, Any]] = None
    execution_metrics: dict[str, Any] = Field(default_factory=dict)
    error_info: Optional[dict[str, Any]] = None


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


class FlowDraftSnapshotResponse(BaseModel):
    """FlowDraft 快照列表项。"""

    snapshot_id: int
    flowdraft_id: int
    snapshot_type: str
    created_by: int
    created_at: Optional[str] = None


class FlowDraftDiffChunkResponse(BaseModel):
    """单块 diff 结果。"""

    changed: bool
    changed_count: int
    changed_paths: list[str] = Field(default_factory=list)
    changed_step_ids: list[str] = Field(default_factory=list)


class FlowDraftDiffResponse(BaseModel):
    """FlowDraft diff 响应。"""

    flowdraft_id: int
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    business_graph_diff: FlowDraftDiffChunkResponse
    technical_graph_diff: FlowDraftDiffChunkResponse
    preflight_summary_diff: FlowDraftDiffChunkResponse


class FlowDraftStepPatchRequest(BaseModel):
    """单步 patch 请求。"""

    changes: dict[str, Any] = Field(default_factory=dict)


class FlowDraftStepPatchResponse(BaseModel):
    """单步 patch 结果。"""

    flowdraft_id: int
    step_id: str
    status: str
    direct_updates: list[str] = Field(default_factory=list)
    needs_resolution_fields: list[str] = Field(default_factory=list)
    pending_issues: list[dict[str, Any]] = Field(default_factory=list)
    latest_snapshot_id: Optional[int] = None


class FlowDraftStepResolveResponse(BaseModel):
    """单步局部重收敛结果。"""

    flowdraft_id: int
    step_id: str
    status: str
    resolution_status: str
    blocking_issues: list[dict[str, Any]] = Field(default_factory=list)
    pending_issues: list[dict[str, Any]] = Field(default_factory=list)
    latest_snapshot_id: Optional[int] = None


class FlowDraftResolveResponse(BaseModel):
    """整份 FlowDraft 重收敛结果。"""

    flowdraft_id: int
    status: str
    resolved_steps: list[str] = Field(default_factory=list)
    blocked_steps: list[dict[str, Any]] = Field(default_factory=list)
    pending_issues: list[dict[str, Any]] = Field(default_factory=list)
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


class DangerousSQLConfirmRequest(BaseModel):
    """危险 SQL 确认请求。"""

    reason: Optional[str] = None
    run_step_ids: list[int] = Field(default_factory=list)
    resume_execution: bool = True


class DangerousSQLConfirmResponse(BaseModel):
    """危险 SQL 确认结果。"""

    run_id: int
    status: str
    confirmed_count: int
    confirmed_step_ids: list[str] = Field(default_factory=list)
    resumed: bool = False
    resume_result: Optional[dict[str, Any]] = None


class SQLAuditSummaryResponse(BaseModel):
    """SQL 审计列表项。"""

    audit_id: int
    run_id: int
    run_step_id: Optional[int] = None
    system_short: Optional[str] = None
    audit_type: str
    risk_level: Optional[str] = None
    confirmation_mode: Optional[str] = None
    status: str
    step_id: Optional[str] = None
    step_name: Optional[str] = None
    created_at: Optional[str] = None


class SQLAuditDetailResponse(BaseModel):
    """SQL 审计详情。"""

    audit_id: int
    run_id: int
    run_step_id: Optional[int] = None
    actor_user_id: int
    system_short: Optional[str] = None
    audit_type: str
    risk_level: Optional[str] = None
    confirmation_mode: Optional[str] = None
    confirmed_by: Optional[int] = None
    confirmed_at: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    target_objects: list[dict[str, Any]] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


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
