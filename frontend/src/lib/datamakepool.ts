import { apiRequest } from "@/lib/api-wrapper"
import { getApiUrl } from "@/lib/utils"

export interface DatamakepoolTemplateSummary {
  template_id: number
  name: string
  description?: string | null
  system_short: string
  owner_user_id: number
  latest_published_revision_id?: number | null
  revisions_count: number
}

export interface DatamakepoolHttpAssetSummary {
  asset_id: number
  name: string
  description?: string | null
  system_short: string
  method: string
  base_url: string
  path_template: string
  enabled: boolean
  owner_user_id: number
  updated_at?: string | null
}

export interface DatamakepoolHttpAssetDetail {
  asset_id: number
  name: string
  description?: string | null
  system_short: string
  method: string
  base_url: string
  path_template: string
  query_template: Record<string, unknown>
  headers_template: Record<string, unknown>
  body_template: Record<string, unknown>
  request_schema: Record<string, unknown>
  auth_type?: string | null
  auth_config_configured: boolean
  response_extraction_rules: Record<string, unknown>
  timeout_seconds: number
  max_response_bytes: number
  enabled: boolean
  owner_user_id: number
  created_at?: string | null
  updated_at?: string | null
}

export interface DatamakepoolSqlAssetSummary {
  asset_id: number
  name: string
  description?: string | null
  system_short: string
  owner_user_id: number
  current_active_version_id?: number | null
  versions_count: number
  latest_version_id?: number | null
  latest_version_no?: number | null
  latest_version_status?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface DatamakepoolSqlAssetVersionSummary {
  version_id: number
  asset_id: number
  version_no: number
  status: string
  mutation_enabled: boolean
  created_by: number
  reviewed_by?: number | null
  review_comment?: string | null
  reviewed_at?: string | null
  created_at?: string | null
}

export interface DatamakepoolTemplateAssetReference {
  asset_type: string
  asset_id: number
  version_id?: number | null
  name?: string | null
  system_short?: string | null
  snapshot_kind?: string | null
  step_ids: string[]
  step_names: string[]
}

export interface DatamakepoolAssetTemplateReference {
  template_id: number
  template_name: string
  template_system_short: string
  revision_id: number
  revision_version_no: number
  revision_status: string
  matched_version_ids: number[]
  step_ids: string[]
  step_names: string[]
}

export interface DatamakepoolConversationSummary {
  conversation_id: number
  task_id: number
  flowdraft_id: number
  title: string
  objective?: string | null
  flowdraft_status: string
  created_at?: string | null
  updated_at?: string | null
}

export interface DatamakepoolFlowdraftIssue {
  issue_type: string
  step_id?: string | null
  message: string
  severity?: string | null
  suggested_action?: string | null
  payload: Record<string, unknown>
}

export interface DatamakepoolFlowdraftPreflightSummary {
  is_runnable: boolean
  issues: DatamakepoolFlowdraftIssue[]
  grouped_by_type: Record<string, DatamakepoolFlowdraftIssue[]>
  grouped_by_step: Record<string, DatamakepoolFlowdraftIssue[]>
  suggested_actions: string[]
}

export interface DatamakepoolConversationMessageResponse {
  conversation_id: number
  message_id: number
  assistant_message_id?: number | null
  flowdraft_id: number
  flowdraft_status: string
  title?: string | null
  objective?: string | null
  assistant_summary?: string | null
  pending_issues: DatamakepoolFlowdraftIssue[]
  latest_snapshot_id?: number | null
}

export interface DatamakepoolFlowdraft {
  id: number
  task_id: number
  status: string
  title?: string | null
  objective?: string | null
  business_graph: Record<string, unknown>
  technical_graph: Record<string, unknown>
  pending_issues: DatamakepoolFlowdraftIssue[]
  preflight_summary?: DatamakepoolFlowdraftPreflightSummary | null
  input_schema_draft?: Record<string, unknown> | null
  output_mapping_draft?: Record<string, unknown> | null
  latest_snapshot_id?: number | null
}

export interface DatamakepoolFlowdraftResolveResponse {
  flowdraft_id: number
  status: string
  resolved_steps: string[]
  blocked_steps: Record<string, unknown>[]
  pending_issues: DatamakepoolFlowdraftIssue[]
  latest_snapshot_id?: number | null
}

export interface DatamakepoolTemplateRevisionSummary {
  revision_id: number
  template_id: number
  version_no: number
  status: string
  source_run_id?: number | null
  created_by: number
  reviewed_by?: number | null
  review_comment?: string | null
  steps_count: number
  asset_references: DatamakepoolTemplateAssetReference[]
}

export interface DatamakepoolTemplateRevisionStepDetail {
  step_id: string
  step_type: string
  name: string
  depends_on: string[]
  design_intent: Record<string, unknown>
  resolution_rationale: Record<string, unknown>
  resolved_execution_plan: Record<string, unknown>
  editable_fields: unknown[]
}

export interface DatamakepoolTemplateRevisionDetail
  extends DatamakepoolTemplateRevisionSummary {
  template_name: string
  template_description?: string | null
  system_short: string
  latest_published_revision_id?: number | null
  is_latest_published: boolean
  business_graph_snapshot: Record<string, unknown>
  technical_graph: Record<string, unknown>
  input_schema: Record<string, unknown>
  output_mapping: Record<string, unknown>
  created_at?: string | null
  reviewed_at?: string | null
  published_at?: string | null
  steps: DatamakepoolTemplateRevisionStepDetail[]
}

export interface DatamakepoolTemplateReviewResponse {
  revision_id: number
  status: string
}

export interface DatamakepoolRunCreatedStep {
  step_id: string
  step_type: string
  step_name: string
}

export interface DatamakepoolRunCreateResponse {
  run_id: number
  entry_type: string
  status: string
  created_steps: DatamakepoolRunCreatedStep[]
  runtime: Record<string, unknown>
  final_output?: Record<string, unknown> | null
  error_summary?: string | null
  steps_summary: Record<string, unknown>[]
}

export interface DatamakepoolRunDetail {
  run_id: number
  entry_type: string
  source_task_id?: number | null
  template_id?: string | null
  template_revision_id?: string | null
  initiator_user_id: number
  system_short?: string | null
  objective?: string | null
  input_payload?: Record<string, unknown> | null
  resolved_input?: Record<string, unknown> | null
  status: string
  final_output?: Record<string, unknown> | null
  error_summary?: string | null
  steps_count: number
}

export interface DatamakepoolRunStep {
  id: number
  run_id: number
  step_id: string
  step_type: string
  step_name: string
  status: string
  depends_on: unknown[]
  resolved_execution_plan_snapshot?: Record<string, unknown> | null
  asset_version_snapshot_ref?: Record<string, unknown> | null
  input_snapshot?: Record<string, unknown> | null
  output_snapshot?: Record<string, unknown> | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface DatamakepoolPendingDangerousSqlItem {
  audit_id: number
  run_step_id?: number | null
  step_id?: string | null
  step_name?: string | null
  risk_level?: string | null
  confirmation_reason?: string | null
  sql_preview?: string | null
  target_objects: Record<string, unknown>[]
  created_at?: string | null
}

export interface DatamakepoolPendingDangerousSqlResponse {
  run_id: number
  pending_count: number
  items: DatamakepoolPendingDangerousSqlItem[]
}

export interface DatamakepoolDangerousSqlConfirmResponse {
  run_id: number
  status: string
  confirmed_count: number
  confirmed_step_ids: string[]
  resumed: boolean
  resume_result?: Record<string, unknown> | null
}

export interface DatamakepoolSqlAuditSummaryItem {
  audit_id: number
  run_id: number
  run_step_id?: number | null
  system_short?: string | null
  audit_type: string
  risk_level?: string | null
  confirmation_mode?: string | null
  status: string
  step_id?: string | null
  step_name?: string | null
  confirmed_by?: number | null
  confirmed_at?: string | null
  confirmation_reason?: string | null
  sql_preview?: string | null
  target_objects: Record<string, unknown>[]
  created_at?: string | null
}

export interface DatamakepoolRunSqlAuditSummaryResponse {
  run_id: number
  total_count: number
  items: DatamakepoolSqlAuditSummaryItem[]
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      return payload.detail
    }
  } catch {
    // 保持最小降级，统一回落到状态码描述。
  }

  return `请求失败（${response.status}）`
}

/**
 * 探索入口前台与模板/资产台共用同一个 datamakepool 真相源文件。
 * 这里补的是聊天探索页 MVP 需要的最小会话与 FlowDraft API。
 */
export async function createDatamakepoolConversation(payload?: {
  title?: string
  objective?: string
}): Promise<DatamakepoolConversationSummary> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/conversations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title: payload?.title,
      objective: payload?.objective,
    }),
  })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolConversationSummary
}

export async function postDatamakepoolConversationMessage(
  conversationId: number,
  payload: {
    content: string
  }
): Promise<DatamakepoolConversationMessageResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/conversations/${conversationId}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        content: payload.content,
      }),
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolConversationMessageResponse
}

export async function getDatamakepoolConversationFlowdraft(
  conversationId: number
): Promise<DatamakepoolFlowdraft> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/conversations/${conversationId}/flowdraft`
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolFlowdraft
}

export async function getDatamakepoolFlowdraft(
  flowdraftId: number
): Promise<DatamakepoolFlowdraft> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/flowdrafts/${flowdraftId}`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolFlowdraft
}

export async function getDatamakepoolFlowdraftPreflight(
  flowdraftId: number
): Promise<DatamakepoolFlowdraftPreflightSummary> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/flowdrafts/${flowdraftId}/preflight`,
    {
      method: "POST",
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolFlowdraftPreflightSummary
}

export async function resolveDatamakepoolFlowdraft(
  flowdraftId: number
): Promise<DatamakepoolFlowdraftResolveResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/flowdrafts/${flowdraftId}/resolve`,
    {
      method: "POST",
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolFlowdraftResolveResponse
}

export async function trialDatamakepoolFlowdraft(
  flowdraftId: number,
  payload?: {
    entry_type?: string
    initiator_user_id?: number
    system_short?: string
  }
): Promise<DatamakepoolRunCreateResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/flowdrafts/${flowdraftId}/trial`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        entry_type: payload?.entry_type ?? "chat",
        initiator_user_id: payload?.initiator_user_id,
        system_short: payload?.system_short,
      }),
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolRunCreateResponse
}

/**
 * datamakepool 前端工作台目前还处在 MVP 首批阶段，
 * 这里先收口模板列表 / 版本列表所需的最小真相源读取。
 */
export async function listDatamakepoolTemplates(): Promise<DatamakepoolTemplateSummary[]> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/templates`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolTemplateSummary[]
}

export async function listDatamakepoolHttpAssets(): Promise<DatamakepoolHttpAssetSummary[]> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/http-assets`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolHttpAssetSummary[]
}

export async function getDatamakepoolHttpAsset(
  assetId: number
): Promise<DatamakepoolHttpAssetDetail> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/http-assets/${assetId}`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolHttpAssetDetail
}

export async function createDatamakepoolHttpAsset(payload: {
  name: string
  description?: string
  system_short: string
  base_url: string
  method: string
  path_template: string
  query_template?: Record<string, unknown>
  headers_template?: Record<string, unknown>
  body_template?: Record<string, unknown>
  request_schema?: Record<string, unknown>
  auth_type?: string
  auth_config_ciphertext?: string
  response_extraction_rules?: Record<string, unknown>
  timeout_seconds?: number
  max_response_bytes?: number
  enabled?: boolean
}): Promise<DatamakepoolHttpAssetSummary> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/http-assets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: payload.name,
      description: payload.description,
      system_short: payload.system_short,
      base_url: payload.base_url,
      method: payload.method,
      path_template: payload.path_template,
      query_template: payload.query_template ?? {},
      headers_template: payload.headers_template ?? {},
      body_template: payload.body_template ?? {},
      request_schema: payload.request_schema ?? {},
      auth_type: payload.auth_type,
      auth_config_ciphertext: payload.auth_config_ciphertext,
      response_extraction_rules: payload.response_extraction_rules ?? {},
      timeout_seconds: payload.timeout_seconds ?? 30,
      max_response_bytes: payload.max_response_bytes ?? 1048576,
      enabled: payload.enabled ?? true,
    }),
  })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolHttpAssetSummary
}

export async function listDatamakepoolSqlAssets(): Promise<DatamakepoolSqlAssetSummary[]> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/sql-assets`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolSqlAssetSummary[]
}

export async function getDatamakepoolSqlAsset(
  assetId: number
): Promise<DatamakepoolSqlAssetSummary> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/sql-assets/${assetId}`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolSqlAssetSummary
}

export async function createDatamakepoolSqlAsset(payload: {
  name: string
  description?: string
  system_short: string
  connection_config?: Record<string, unknown>
  whitelist?: string[]
  blacklist?: string[]
  mutation_enabled?: boolean
}): Promise<{ asset_id: number; version_id: number; version_no: number; status: string }> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/sql-assets`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: payload.name,
      description: payload.description,
      system_short: payload.system_short,
      connection_config: payload.connection_config ?? {},
      whitelist: payload.whitelist ?? [],
      blacklist: payload.blacklist ?? [],
      mutation_enabled: payload.mutation_enabled ?? false,
    }),
  })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as {
    asset_id: number
    version_id: number
    version_no: number
    status: string
  }
}

export async function listDatamakepoolSqlAssetVersions(
  assetId: number
): Promise<DatamakepoolSqlAssetVersionSummary[]> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/sql-assets/${assetId}/versions`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolSqlAssetVersionSummary[]
}

export async function listDatamakepoolTemplateRevisions(
  templateId: number
): Promise<DatamakepoolTemplateRevisionSummary[]> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/templates/${templateId}/revisions`
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolTemplateRevisionSummary[]
}

export async function getDatamakepoolTemplateRevisionDetail(
  revisionId: number
): Promise<DatamakepoolTemplateRevisionDetail> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/templates/revisions/${revisionId}`
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolTemplateRevisionDetail
}

export async function submitDatamakepoolTemplateRevisionReview(
  revisionId: number
): Promise<DatamakepoolTemplateReviewResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/templates/revisions/${revisionId}/submit-review`,
    {
      method: "POST",
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolTemplateReviewResponse
}

export async function approveDatamakepoolTemplateRevision(
  revisionId: number
): Promise<DatamakepoolTemplateReviewResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/templates/revisions/${revisionId}/approve`,
    {
      method: "POST",
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolTemplateReviewResponse
}

export async function createDatamakepoolRunFromTemplate(
  templateRevisionId: number,
  inputPayload?: Record<string, unknown>
): Promise<DatamakepoolRunCreateResponse> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/runs/from-template`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      template_revision_id: templateRevisionId,
      input_payload: inputPayload,
    }),
  })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolRunCreateResponse
}

export async function getDatamakepoolRunDetail(runId: number): Promise<DatamakepoolRunDetail> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/runs/${runId}`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolRunDetail
}

export async function listDatamakepoolRunSteps(runId: number): Promise<DatamakepoolRunStep[]> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/runs/${runId}/steps`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolRunStep[]
}

export async function startDatamakepoolRun(runId: number): Promise<DatamakepoolRunDetail> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/runs/${runId}/start`, {
    method: "POST",
  })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolRunDetail
}

export async function getDatamakepoolPendingDangerousSql(
  runId: number
): Promise<DatamakepoolPendingDangerousSqlResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/runs/${runId}/dangerous-sql-pending`
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolPendingDangerousSqlResponse
}

export async function getDatamakepoolRunSqlAudits(
  runId: number
): Promise<DatamakepoolRunSqlAuditSummaryResponse> {
  const response = await apiRequest(`${getApiUrl()}/api/datamakepool/runs/${runId}/sql-audits`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolRunSqlAuditSummaryResponse
}

export async function confirmDatamakepoolDangerousSql(
  runId: number,
  payload: {
    reason?: string
    run_step_ids?: number[]
    resume_execution?: boolean
  }
): Promise<DatamakepoolDangerousSqlConfirmResponse> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/runs/${runId}/confirm-dangerous-sql`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        reason: payload.reason,
        run_step_ids: payload.run_step_ids ?? [],
        resume_execution: payload.resume_execution ?? true,
      }),
    }
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolDangerousSqlConfirmResponse
}

export async function listDatamakepoolHttpAssetTemplateReferences(
  assetId: number
): Promise<DatamakepoolAssetTemplateReference[]> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/http-assets/${assetId}/template-references`
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolAssetTemplateReference[]
}

export async function listDatamakepoolSqlAssetTemplateReferences(
  assetId: number
): Promise<DatamakepoolAssetTemplateReference[]> {
  const response = await apiRequest(
    `${getApiUrl()}/api/datamakepool/sql-assets/${assetId}/template-references`
  )
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return (await response.json()) as DatamakepoolAssetTemplateReference[]
}
