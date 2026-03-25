"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowUpRight,
  FileSearch,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react"

import {
  getDatamakepoolSqlAuditDetail,
  listDatamakepoolSqlAudits,
  type DatamakepoolSqlAuditDetail,
  type DatamakepoolSqlAuditSummaryItem,
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
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn, formatDate } from "@/lib/utils"

type AuditStatusFilter =
  | "all"
  | "pending_confirmation"
  | "confirmed"
  | "succeeded"
  | "failed"

type AuditRiskFilter = "all" | "critical" | "high" | "medium" | "low"

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

function formatTargetObjects(targetObjects: Record<string, unknown>[]): string[] {
  if (!targetObjects.length) {
    return []
  }

  return targetObjects.map((item) => {
    const assetRef = typeof item.asset_ref === "string" ? item.asset_ref : null
    const lane = typeof item.lane === "string" ? item.lane : null
    const sql = typeof item.sql === "string" ? item.sql : null

    return [assetRef, lane, sql].filter(Boolean).join(" / ") || JSON.stringify(item)
  })
}

function getStatusMeta(status: string): { label: string; className: string } {
  switch (status) {
    case "pending_confirmation":
      return {
        label: "待确认",
        className: "border-amber-200 bg-amber-50 text-amber-700",
      }
    case "confirmed":
      return {
        label: "已确认",
        className: "border-sky-200 bg-sky-50 text-sky-700",
      }
    case "succeeded":
      return {
        label: "已完成",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      }
    case "failed":
      return {
        label: "失败",
        className: "border-destructive/30 bg-destructive/5 text-destructive",
      }
    default:
      return {
        label: status || "未知",
        className: "border-border bg-muted text-muted-foreground",
      }
  }
}

function getRiskMeta(riskLevel?: string | null): { label: string; className: string } {
  switch ((riskLevel || "").toLowerCase()) {
    case "critical":
      return {
        label: "Critical",
        className: "border-destructive/30 bg-destructive/5 text-destructive",
      }
    case "high":
      return {
        label: "High",
        className: "border-amber-300 bg-amber-50 text-amber-800",
      }
    case "medium":
      return {
        label: "Medium",
        className: "border-orange-200 bg-orange-50 text-orange-700",
      }
    case "low":
      return {
        label: "Low",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      }
    default:
      return {
        label: riskLevel || "未知",
        className: "border-border bg-muted text-muted-foreground",
      }
  }
}

function AuditCard({
  audit,
  isSelected,
  onSelect,
}: {
  audit: DatamakepoolSqlAuditSummaryItem
  isSelected: boolean
  onSelect: () => void
}) {
  const statusMeta = getStatusMeta(audit.status)
  const riskMeta = getRiskMeta(audit.risk_level)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-2xl border p-4 text-left transition-all",
        isSelected
          ? "border-primary/35 bg-primary/10 shadow-[0_12px_30px_-20px_hsl(var(--primary)/0.65)]"
          : "border-border/70 bg-background/70 hover:border-primary/20 hover:bg-muted/20"
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">
            {audit.step_name || audit.step_id || `审计 #${audit.audit_id}`}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Run #{audit.run_id} · {audit.system_short || "未标注系统"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className={cn("font-medium", riskMeta.className)}>
            {riskMeta.label}
          </Badge>
          <Badge variant="outline" className={cn("font-medium", statusMeta.className)}>
            {statusMeta.label}
          </Badge>
        </div>
      </div>

      <div className="mt-3 space-y-2 text-sm text-muted-foreground">
        <div>确认模式：{audit.confirmation_mode || "未记录"}</div>
        <div>确认原因：{audit.confirmation_reason?.trim() || "未记录"}</div>
        <div>创建时间：{formatDateLabel(audit.created_at)}</div>
      </div>
    </button>
  )
}

export function SqlAuditConsole({
  initialAuditId = null,
}: {
  initialAuditId?: number | null
}) {
  const [audits, setAudits] = useState<DatamakepoolSqlAuditSummaryItem[]>([])
  const [selectedAuditId, setSelectedAuditId] = useState<number | null>(initialAuditId)
  const [selectedAuditDetail, setSelectedAuditDetail] = useState<DatamakepoolSqlAuditDetail | null>(
    null
  )
  const [keyword, setKeyword] = useState("")
  const [statusFilter, setStatusFilter] = useState<AuditStatusFilter>("all")
  const [riskFilter, setRiskFilter] = useState<AuditRiskFilter>("all")
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [isLoadingList, setIsLoadingList] = useState(true)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const loadAudits = useCallback(
    async (showRefreshingState: boolean = false) => {
      if (showRefreshingState) {
        setIsRefreshing(true)
      } else {
        setIsLoadingList(true)
      }
      setListError(null)

      try {
        const nextAudits = await listDatamakepoolSqlAudits()
        setAudits(nextAudits)
        setSelectedAuditId((current) => {
          if (current !== null && nextAudits.some((item) => item.audit_id === current)) {
            return current
          }
          if (initialAuditId && nextAudits.some((item) => item.audit_id === initialAuditId)) {
            return initialAuditId
          }
          return nextAudits[0]?.audit_id ?? null
        })
      } catch (error) {
        setAudits([])
        setSelectedAuditId(null)
        setSelectedAuditDetail(null)
        setListError(error instanceof Error ? error.message : "审计列表加载失败")
      } finally {
        setIsLoadingList(false)
        setIsRefreshing(false)
      }
    },
    [initialAuditId]
  )

  const loadAuditDetail = useCallback(async (auditId: number) => {
    setIsLoadingDetail(true)
    setDetailError(null)

    try {
      const detail = await getDatamakepoolSqlAuditDetail(auditId)
      setSelectedAuditDetail(detail)
    } catch (error) {
      setSelectedAuditDetail(null)
      setDetailError(error instanceof Error ? error.message : "审计详情加载失败")
    } finally {
      setIsLoadingDetail(false)
    }
  }, [])

  useEffect(() => {
    void loadAudits()
  }, [loadAudits])

  useEffect(() => {
    if (selectedAuditId === null) {
      setSelectedAuditDetail(null)
      setDetailError(null)
      setIsLoadingDetail(false)
      return
    }

    void loadAuditDetail(selectedAuditId)
  }, [loadAuditDetail, selectedAuditId])

  const filteredAudits = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()

    return audits.filter((audit) => {
      if (statusFilter !== "all" && audit.status !== statusFilter) {
        return false
      }
      if (riskFilter !== "all" && (audit.risk_level || "").toLowerCase() !== riskFilter) {
        return false
      }
      if (!normalizedKeyword) {
        return true
      }

      return [
        audit.step_name,
        audit.step_id,
        audit.system_short,
        audit.confirmation_reason,
        audit.sql_preview,
        String(audit.run_id),
        String(audit.audit_id),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedKeyword))
    })
  }, [audits, keyword, riskFilter, statusFilter])

  useEffect(() => {
    if (!filteredAudits.length) {
      setSelectedAuditId(null)
      return
    }

    if (!filteredAudits.some((audit) => audit.audit_id === selectedAuditId)) {
      setSelectedAuditId(filteredAudits[0].audit_id)
    }
  }, [filteredAudits, selectedAuditId])

  const pendingCount = audits.filter((audit) => audit.status === "pending_confirmation").length
  const highRiskCount = audits.filter((audit) =>
    ["critical", "high"].includes((audit.risk_level || "").toLowerCase())
  ).length
  const visibleSystemsCount = new Set(
    audits
      .map((audit) => audit.system_short?.trim())
      .filter((item): item is string => Boolean(item))
  ).size
  const auditPayloadPreview = stringifyPreview(selectedAuditDetail?.payload ?? null)
  const targetObjects = formatTargetObjects(selectedAuditDetail?.target_objects ?? [])
  const selectedAuditSummary =
    audits.find((audit) => audit.audit_id === selectedAuditId) ?? null
  const selectedStatusMeta = getStatusMeta(selectedAuditSummary?.status || "")
  const selectedRiskMeta = getRiskMeta(selectedAuditSummary?.risk_level)
  const runDetailHref =
    selectedAuditDetail?.run_id
      ? `/datamakepool/runs/${selectedAuditDetail.run_id}`
      : selectedAuditSummary?.run_id
        ? `/datamakepool/runs/${selectedAuditSummary.run_id}`
        : null

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F21 审计中心"
      title="SQL 审计工作台"
      description="这一页承接治理与审计设计：按管理员权限查看 SQL 审计列表、定位待确认记录，并回看每条审计的运行与风险上下文。"
      metrics={[
        {
          label: "审计总数",
          value: String(audits.length),
          hint: "当前权限范围内全部 SQL 审计",
        },
        {
          label: "待确认",
          value: String(pendingCount),
          hint: "需要人工确认的危险 SQL",
        },
        {
          label: "高风险",
          value: String(highRiskCount),
          hint: "high / critical 风险等级",
        },
        {
          label: "系统域",
          value: String(visibleSystemsCount),
          hint: "当前可见 system_short 数量",
        },
      ]}
      actions={
        <div className="flex flex-wrap gap-2">
          {runDetailHref ? (
            <Button asChild variant="outline" className="border-border/80 bg-background/70 backdrop-blur-sm">
              <Link href={runDetailHref}>
                <ArrowUpRight className="h-4 w-4" />
                查看 Run
              </Link>
            </Button>
          ) : null}
          <Button
            variant="outline"
            onClick={() => void loadAudits(true)}
            disabled={isLoadingList || isRefreshing}
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            {isRefreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            刷新
          </Button>
        </div>
      }
    >
      <div className="grid h-full min-h-0 gap-6 p-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <FileSearch className="h-3.5 w-3.5" />
              审计列表
            </div>
            <CardTitle>筛选与定位</CardTitle>
            <CardDescription>先按状态、风险和关键字缩小范围，再进入右侧详情面板看具体记录。</CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            <div className="space-y-4 border-b border-border/70 px-4 py-4">
              <Input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索 step、系统域、SQL 片段、Run ID"
              />

              <Tabs
                value={statusFilter}
                onValueChange={(value) => setStatusFilter(value as AuditStatusFilter)}
              >
                <TabsList className="w-full">
                  <TabsTrigger value="all">全部</TabsTrigger>
                  <TabsTrigger value="pending_confirmation">待确认</TabsTrigger>
                  <TabsTrigger value="confirmed">已确认</TabsTrigger>
                  <TabsTrigger value="succeeded">已完成</TabsTrigger>
                  <TabsTrigger value="failed">失败</TabsTrigger>
                </TabsList>
              </Tabs>

              <div className="flex flex-wrap gap-2">
                {[
                  ["all", "全部风险"],
                  ["critical", "Critical"],
                  ["high", "High"],
                  ["medium", "Medium"],
                  ["low", "Low"],
                ].map(([value, label]) => (
                  <Button
                    key={value}
                    size="sm"
                    variant={riskFilter === value ? "default" : "outline"}
                    onClick={() => setRiskFilter(value as AuditRiskFilter)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
            </div>

            {isLoadingList ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载 SQL 审计列表
              </div>
            ) : listError ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {listError}
                </div>
              </div>
            ) : !filteredAudits.length ? (
              <div className="px-6 py-10 text-sm text-muted-foreground">
                当前筛选条件下没有命中任何 SQL 审计记录。
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  {filteredAudits.map((audit) => (
                    <AuditCard
                      key={audit.audit_id}
                      audit={audit}
                      isSelected={audit.audit_id === selectedAuditId}
                      onSelect={() => setSelectedAuditId(audit.audit_id)}
                    />
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <div className="grid min-h-0 gap-6">
          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" />
                审计摘要
              </div>
              <CardTitle>风险与确认状态</CardTitle>
              <CardDescription>先看当前选中记录的状态、风险等级、确认链路和来源 Run。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {detailError ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {detailError}
                </div>
              ) : null}

              {isLoadingDetail && selectedAuditDetail === null ? (
                <div className="flex items-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载审计详情
                </div>
              ) : !selectedAuditSummary ? (
                <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                  先从左侧选择一条 SQL 审计记录。
                </div>
              ) : (
                <>
                  <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.16em] text-primary/80">
                          当前选中
                        </div>
                        <div className="mt-2 text-lg font-semibold text-foreground">
                          {selectedAuditSummary.step_name || selectedAuditSummary.step_id || `审计 #${selectedAuditSummary.audit_id}`}
                        </div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          审计 #{selectedAuditSummary.audit_id} · Run #{selectedAuditSummary.run_id}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <Badge variant="outline" className={cn("font-medium", selectedRiskMeta.className)}>
                          {selectedRiskMeta.label}
                        </Badge>
                        <Badge variant="outline" className={cn("font-medium", selectedStatusMeta.className)}>
                          {selectedStatusMeta.label}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 text-sm text-muted-foreground">
                    <div>系统域：{selectedAuditSummary.system_short || "未标注"}</div>
                    <div>确认模式：{selectedAuditSummary.confirmation_mode || "未记录"}</div>
                    <div>确认原因：{selectedAuditSummary.confirmation_reason?.trim() || "未记录"}</div>
                    <div>
                      确认人：
                      {selectedAuditSummary.confirmed_by
                        ? `用户 #${selectedAuditSummary.confirmed_by} / ${formatDateLabel(selectedAuditSummary.confirmed_at)}`
                        : "未确认"}
                    </div>
                    <div>创建时间：{formatDateLabel(selectedAuditSummary.created_at)}</div>
                  </div>

                  {selectedAuditSummary.sql_preview ? (
                    <div>
                      <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                        SQL Preview
                      </div>
                      <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                        {selectedAuditSummary.sql_preview}
                      </pre>
                    </div>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <AlertTriangle className="h-3.5 w-3.5" />
                目标对象
              </div>
              <CardTitle>影响范围</CardTitle>
              <CardDescription>这里集中看当前审计涉及的 asset_ref、lane 和 SQL 目标对象。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4">
              {!targetObjects.length ? (
                <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                  当前审计没有结构化 target_objects。
                </div>
              ) : (
                targetObjects.map((item, index) => (
                  <div
                    key={`${selectedAuditId ?? "audit"}-target-${index}`}
                    className="rounded-xl border border-border/70 bg-muted/20 px-3 py-3 text-sm text-muted-foreground"
                  >
                    {item}
                  </div>
                ))
              )}

              {selectedAuditDetail?.error_message?.trim() ? (
                <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-3 text-sm text-destructive">
                  错误信息：{selectedAuditDetail.error_message}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <FileSearch className="h-3.5 w-3.5" />
                Payload 真相源
              </div>
              <CardTitle>完整审计载荷</CardTitle>
              <CardDescription>当摘要不够时，直接回到后端序列化后的 payload 真相源排查。</CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              {!auditPayloadPreview ? (
                <div className="px-6 py-10 text-sm text-muted-foreground">
                  当前记录还没有结构化 payload 可展示。
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="p-4">
                    <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                      {auditPayloadPreview}
                    </pre>
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </DatamakepoolShell>
  )
}
