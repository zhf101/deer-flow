"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Database, GitBranch, Loader2, Workflow } from "lucide-react"

import {
  getDatamakepoolSqlAsset,
  listDatamakepoolSqlAssetTemplateReferences,
  listDatamakepoolSqlAssetVersions,
  type DatamakepoolAssetTemplateReference,
  type DatamakepoolSqlAssetSummary,
  type DatamakepoolSqlAssetVersionSummary,
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
import { cn, formatDate } from "@/lib/utils"

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return "未记录"
  }
  return formatDate(value)
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

function getVersionStatusMeta(status?: string | null): { label: string; className: string } {
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
    case "approved":
    case "published":
      return {
        label: "已生效",
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
        <div>
          命中版本：
          {reference.matched_version_ids.length
            ? reference.matched_version_ids.join("、")
            : "逻辑资产视角"}
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

function SqlVersionCard({
  version,
  isActive,
}: {
  version: DatamakepoolSqlAssetVersionSummary
  isActive: boolean
}) {
  const statusMeta = getVersionStatusMeta(version.status)

  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">版本 V{version.version_no}</div>
          <div className="mt-1 text-xs text-muted-foreground">version_id={version.version_id}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {isActive ? (
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
              当前生效
            </Badge>
          ) : null}
          <Badge variant="outline" className={cn("font-medium", statusMeta.className)}>
            {statusMeta.label}
          </Badge>
        </div>
      </div>

      <div className="mt-3 space-y-2 text-sm text-muted-foreground">
        <div>Mutation：{version.mutation_enabled ? "允许" : "关闭"}</div>
        <div>创建人：用户 #{version.created_by}</div>
        <div>
          审核人：
          {version.reviewed_by ? `用户 #${version.reviewed_by}` : "未审核"}
        </div>
        <div>审核备注：{version.review_comment?.trim() || "无"}</div>
        <div>创建时间：{formatDateLabel(version.created_at)}</div>
        <div>审核时间：{formatDateLabel(version.reviewed_at)}</div>
      </div>
    </div>
  )
}

/**
 * F27 SQL 资产详情页聚焦逻辑资产和模板反向引用，不扩成完整资产管理台。
 */
export function SqlAssetDetailConsole({
  assetId,
  returnTemplateId = null,
  returnRevisionId = null,
}: {
  assetId: number
  returnTemplateId?: number | null
  returnRevisionId?: number | null
}) {
  const [assetDetail, setAssetDetail] = useState<DatamakepoolSqlAssetSummary | null>(null)
  const [versions, setVersions] = useState<DatamakepoolSqlAssetVersionSummary[]>([])
  const [templateReferences, setTemplateReferences] = useState<DatamakepoolAssetTemplateReference[]>(
    []
  )
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [detail, nextVersions, references] = await Promise.all([
        getDatamakepoolSqlAsset(assetId),
        listDatamakepoolSqlAssetVersions(assetId),
        listDatamakepoolSqlAssetTemplateReferences(assetId),
      ])
      setAssetDetail(detail)
      setVersions(nextVersions)
      setTemplateReferences(references)
    } catch (nextError) {
      setAssetDetail(null)
      setVersions([])
      setTemplateReferences([])
      setError(nextError instanceof Error ? nextError.message : "SQL 资产详情加载失败")
    } finally {
      setIsLoading(false)
    }
  }, [assetId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const returnHref =
    returnTemplateId && returnRevisionId
      ? `/datamakepool/templates?templateId=${returnTemplateId}&revisionId=${returnRevisionId}`
      : "/datamakepool/templates"

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F27 SQL 资产详情"
      title={`SQL 资产 #${assetId}`}
      description="这里聚焦 SQL 逻辑资产本身、版本概况，以及它被哪些模板版本反向引用。"
      metrics={[
        {
          label: "当前生效版本",
          value: assetDetail?.current_active_version_id ? `#${assetDetail.current_active_version_id}` : "--",
          hint: assetDetail?.system_short || "等待加载",
        },
        {
          label: "版本数",
          value: String(versions.length),
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
                <Database className="h-3.5 w-3.5" />
                逻辑资产
              </div>
              <CardTitle>基础信息</CardTitle>
              <CardDescription>逻辑资产层回答“这是什么资产”，不直接展开版本内部配置。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              {isLoading ? (
                <div className="flex items-center text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载 SQL 资产详情
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
                  <div>资产所有者：用户 #{assetDetail?.owner_user_id ?? "--"}</div>
                  <div>当前生效版本：{assetDetail?.current_active_version_id ? `#${assetDetail.current_active_version_id}` : "无"}</div>
                  <div>最新版本：{assetDetail?.latest_version_no ? `V${assetDetail.latest_version_no}` : "无"}</div>
                  <div>最新状态：{assetDetail?.latest_version_status || "未记录"}</div>
                  <div>创建时间：{formatDateLabel(assetDetail?.created_at)}</div>
                  <div>更新时间：{formatDateLabel(assetDetail?.updated_at)}</div>
                </>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <GitBranch className="h-3.5 w-3.5" />
                版本概况
              </div>
              <CardTitle>版本列表</CardTitle>
              <CardDescription>这里不做编辑，只把逻辑资产下现有版本概况展示清楚。</CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              {isLoading ? (
                <div className="flex items-center px-6 py-10 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载版本列表
                </div>
              ) : error ? (
                <div className="px-6 py-6">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                    {error}
                  </div>
                </div>
              ) : !versions.length ? (
                <div className="px-6 py-10 text-sm text-muted-foreground">
                  当前 SQL 资产还没有可见版本。
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="space-y-4 p-4">
                    {versions.map((version) => (
                      <SqlVersionCard
                        key={version.version_id}
                        version={version}
                        isActive={assetDetail?.current_active_version_id === version.version_id}
                      />
                    ))}
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
            <CardTitle>引用这条 SQL 资产的模板版本</CardTitle>
            <CardDescription>用于回答“这条逻辑资产已经挂在哪些模板版本上”。</CardDescription>
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
                当前权限范围内没有模板版本引用这条 SQL 资产。
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
