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
