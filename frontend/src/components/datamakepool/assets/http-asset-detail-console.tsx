"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Link2, Loader2, Network, Workflow } from "lucide-react"

import {
  getDatamakepoolHttpAsset,
  listDatamakepoolHttpAssetTemplateReferences,
  type DatamakepoolAssetTemplateReference,
  type DatamakepoolHttpAssetDetail,
} from "@/lib/datamakepool"
import { DatamakepoolShell } from "@/components/datamakepool/datamakepool-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { formatDate } from "@/lib/utils"

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return "未记录"
  }
  return formatDate(value)
}

function stringifyPreview(payload: Record<string, unknown> | null | undefined): string | null {
  if (!payload || !Object.keys(payload).length) {
    return null
  }
  return JSON.stringify(payload, null, 2)
}

function getRevisionStatusMeta(status: string): { label: string; className: string } {
  switch (status) {
    case "draft":
      return {
        label: "草稿",
        className: "border-slate-200 bg-slate-100 text-slate-700",
      }
    case "pending_review":
      return {
        label: "待审核",
        className: "border-amber-200 bg-amber-50 text-amber-700",
      }
    case "published":
      return {
        label: "已发布",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      }
    default:
      return {
        label: status || "未知",
        className: "border-border bg-muted text-muted-foreground",
      }
  }
}

function TemplateReferenceCard({
  reference,
}: {
  reference: DatamakepoolAssetTemplateReference
}) {
  const statusMeta = getRevisionStatusMeta(reference.revision_status)

  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">{reference.template_name}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            模板 #{reference.template_id} · 修订 #{reference.revision_id} · V
            {reference.revision_version_no}
          </div>
        </div>
        <Badge variant="outline" className={statusMeta.className}>
          {statusMeta.label}
        </Badge>
      </div>

      <div className="mt-3 space-y-2 text-sm text-muted-foreground">
        <div>系统域：{reference.template_system_short}</div>
        <div>
          命中步骤：
          {reference.step_names.length ? reference.step_names.join("、") : "未记录"}
        </div>
      </div>

      <div className="mt-3">
        <Button asChild size="sm" variant="outline">
          <Link
            href={`/datamakepool/templates?templateId=${reference.template_id}&revisionId=${reference.revision_id}`}
          >
            <Workflow className="h-4 w-4" />
            查看模板版本
          </Link>
        </Button>
      </div>
    </div>
  )
}

/**
 * F27 HTTP 资产详情页只承接两个稳定真相源：
 * 1. 资产本身的定义摘要
 * 2. 被哪些模板版本反向引用
 */
export function HttpAssetDetailConsole({
  assetId,
  returnTemplateId = null,
  returnRevisionId = null,
}: {
  assetId: number
  returnTemplateId?: number | null
  returnRevisionId?: number | null
}) {
  const [assetDetail, setAssetDetail] = useState<DatamakepoolHttpAssetDetail | null>(null)
  const [templateReferences, setTemplateReferences] = useState<DatamakepoolAssetTemplateReference[]>(
    []
  )
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [detail, references] = await Promise.all([
        getDatamakepoolHttpAsset(assetId),
        listDatamakepoolHttpAssetTemplateReferences(assetId),
      ])
      setAssetDetail(detail)
      setTemplateReferences(references)
    } catch (nextError) {
      setAssetDetail(null)
      setTemplateReferences([])
      setError(nextError instanceof Error ? nextError.message : "HTTP 资产详情加载失败")
    } finally {
      setIsLoading(false)
    }
  }, [assetId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const requestSchemaPreview = stringifyPreview(assetDetail?.request_schema ?? null)
  const extractionRulesPreview = stringifyPreview(assetDetail?.response_extraction_rules ?? null)
  const returnHref =
    returnTemplateId && returnRevisionId
      ? `/datamakepool/templates?templateId=${returnTemplateId}&revisionId=${returnRevisionId}`
      : "/datamakepool/templates"

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F27 HTTP 资产详情"
      title={`HTTP 资产 #${assetId}`}
      description="这一页只补设计文档要求的资产反向引用提示：先看资产自身定义，再看哪些模板版本正在引用它。"
      metrics={[
        {
          label: "请求方法",
          value: assetDetail?.method || "--",
          hint: assetDetail?.system_short || "等待加载",
        },
        {
          label: "状态",
          value: assetDetail ? (assetDetail.enabled ? "启用" : "停用") : "--",
          hint: assetDetail?.name || "等待加载",
        },
        {
          label: "反向引用",
          value: String(templateReferences.length),
          hint: "当前权限范围内可见模板版本",
        },
      ]}
      actions={
        <Button asChild variant="outline" className="border-border/80 bg-background/70 backdrop-blur-sm">
          <Link href={returnHref}>
            <ArrowLeft className="h-4 w-4" />
            返回模板
          </Link>
        </Button>
      }
    >
      <div className="grid h-full min-h-0 gap-6 p-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="grid min-h-0 gap-6">
          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Network className="h-3.5 w-3.5" />
                资产摘要
              </div>
              <CardTitle>基础信息</CardTitle>
              <CardDescription>先看这条 HTTP 资产当前绑定的请求定义和运行边界。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              {isLoading ? (
                <div className="flex items-center text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载 HTTP 资产详情
                </div>
              ) : error ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-destructive">
                  {error}
                </div>
              ) : (
                <>
                  <div>名称：{assetDetail?.name || "--"}</div>
                  <div>说明：{assetDetail?.description?.trim() || "无"}</div>
                  <div>系统域：{assetDetail?.system_short || "--"}</div>
                  <div>Base URL：{assetDetail?.base_url || "--"}</div>
                  <div>Path Template：{assetDetail?.path_template || "--"}</div>
                  <div>认证类型：{assetDetail?.auth_type || "未配置"}</div>
                  <div>
                    凭证状态：
                    {assetDetail?.auth_config_configured ? "已配置" : "未配置"}
                  </div>
                  <div>超时：{assetDetail?.timeout_seconds ?? "--"} 秒</div>
                  <div>响应上限：{assetDetail?.max_response_bytes ?? "--"} bytes</div>
                  <div>创建时间：{formatDateLabel(assetDetail?.created_at)}</div>
                  <div>更新时间：{formatDateLabel(assetDetail?.updated_at)}</div>
                </>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Link2 className="h-3.5 w-3.5" />
                契约快照
              </div>
              <CardTitle>请求与提取规则</CardTitle>
              <CardDescription>这里直接展示当前资产详情接口返回的契约真相源。</CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              {isLoading ? (
                <div className="flex items-center px-6 py-10 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载契约快照
                </div>
              ) : error ? (
                <div className="px-6 py-6">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                    {error}
                  </div>
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="space-y-4 p-4">
                    <div>
                      <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                        Request Schema
                      </div>
                      <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                        {requestSchemaPreview || "当前未声明结构化 request_schema。"}
                      </pre>
                    </div>

                    <div>
                      <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                        Response Extraction Rules
                      </div>
                      <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                        {extractionRulesPreview || "当前未声明结构化提取规则。"}
                      </pre>
                    </div>
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Workflow className="h-3.5 w-3.5" />
              模板反向引用
            </div>
            <CardTitle>引用这条资产的模板版本</CardTitle>
            <CardDescription>这就是 F27 资产详情页里的反向引用提示真相源。</CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            {isLoading ? (
              <div className="flex items-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载模板反向引用
              </div>
            ) : error ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {error}
                </div>
              </div>
            ) : !templateReferences.length ? (
              <div className="px-6 py-10 text-sm text-muted-foreground">
                当前权限范围内没有模板版本引用这条 HTTP 资产。
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  {templateReferences.map((reference) => (
                    <TemplateReferenceCard
                      key={`${reference.template_id}-${reference.revision_id}`}
                      reference={reference}
                    />
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </DatamakepoolShell>
  )
}
