"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  ArrowLeft,
  Database,
  GitBranch,
  Loader2,
  RefreshCw,
  Workflow,
} from "lucide-react"

import {
  confirmDatamakepoolDangerousSql,
  getDatamakepoolPendingDangerousSql,
  getDatamakepoolRunDetail,
  getDatamakepoolRunSqlAudits,
  listDatamakepoolRunSteps,
  startDatamakepoolRun,
  type DatamakepoolPendingDangerousSqlItem,
  type DatamakepoolRunDetail,
  type DatamakepoolSqlAuditSummaryItem,
  type DatamakepoolRunStep,
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
import { Textarea } from "@/components/ui/textarea"
import { cn, formatDate } from "@/lib/utils"

function getStatusMeta(status: string): { label: string; className: string } {
  switch (status) {
    case "pending":
      return {
        label: "待执行",
        className: "border-slate-200 bg-slate-100 text-slate-700",
      }
    case "running":
      return {
        label: "执行中",
        className: "border-sky-200 bg-sky-50 text-sky-700",
      }
    case "succeeded":
      return {
        label: "成功",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      }
    case "failed":
      return {
        label: "失败",
        className: "border-destructive/30 bg-destructive/5 text-destructive",
      }
    case "blocked":
      return {
        label: "阻塞",
        className: "border-amber-200 bg-amber-50 text-amber-700",
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

function getAuditStatusMeta(status: string): { label: string; className: string } {
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

function formatTargetObjects(targetObjects: Record<string, unknown>[]): string | null {
  if (!targetObjects.length) {
    return null
  }

  return targetObjects
    .map((item) => {
      const assetRef = typeof item.asset_ref === "string" ? item.asset_ref : null
      const lane = typeof item.lane === "string" ? item.lane : null
      return [assetRef, lane].filter(Boolean).join(" / ")
    })
    .filter(Boolean)
    .join("、")
}

function getRecordSizeLabel(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || !Object.keys(payload).length) {
    return "无"
  }
  return `${Object.keys(payload).length} 项`
}

function getConfirmationLabel(step: DatamakepoolRunStep): string {
  const plan = step.resolved_execution_plan_snapshot ?? {}

  if (plan.confirmation_required === true) {
    return "待确认"
  }
  if (plan.confirmation_confirmed === true) {
    return "已确认"
  }
  return "不涉及"
}

function SqlAuditCard({ audit }: { audit: DatamakepoolSqlAuditSummaryItem }) {
  const riskMeta = getRiskMeta(audit.risk_level)
  const statusMeta = getAuditStatusMeta(audit.status)
  const targetObjectsLabel = formatTargetObjects(audit.target_objects)

  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">
            {audit.step_name || audit.step_id || `审计 #${audit.audit_id}`}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {audit.step_id ? `step_id=${audit.step_id}` : "未记录 step_id"} · 审计 #
            {audit.audit_id}
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

      <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
        <div>确认模式：{audit.confirmation_mode || "未记录"}</div>
        <div>确认原因：{audit.confirmation_reason?.trim() || "未记录"}</div>
        <div>目标对象：{targetObjectsLabel || "未记录"}</div>
        <div>创建时间：{formatDateLabel(audit.created_at)}</div>
        <div>
          确认信息：
          {audit.confirmed_by ? `用户 #${audit.confirmed_by} / ${formatDateLabel(audit.confirmed_at)}` : "未确认"}
        </div>
      </div>

      {audit.sql_preview ? (
        <div className="mt-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            SQL Preview
          </div>
          <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
            {audit.sql_preview}
          </pre>
        </div>
      ) : null}
    </div>
  )
}

function RunStepCard({ step }: { step: DatamakepoolRunStep }) {
  const statusMeta = getStatusMeta(step.status)
  const resolvedPlanPreview = stringifyPreview(step.resolved_execution_plan_snapshot ?? null)

  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">{step.step_name}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {step.step_type} · step_id={step.step_id}
          </div>
        </div>
        <Badge variant="outline" className={cn("font-medium", statusMeta.className)}>
          {statusMeta.label}
        </Badge>
      </div>

      <div className="mt-3 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
        <div>依赖步骤：{step.depends_on.length ? step.depends_on.map(String).join("、") : "无"}</div>
        <div>开始时间：{formatDateLabel(step.started_at)}</div>
        <div>结束时间：{formatDateLabel(step.finished_at)}</div>
        <div>错误信息：{step.error_message?.trim() || "无"}</div>
        <div>确认状态：{getConfirmationLabel(step)}</div>
        <div>输入快照：{getRecordSizeLabel(step.input_snapshot ?? null)}</div>
        <div>输出快照：{getRecordSizeLabel(step.output_snapshot ?? null)}</div>
      </div>

      {resolvedPlanPreview ? (
        <div className="mt-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            Resolved Plan
          </div>
          <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
            {resolvedPlanPreview}
          </pre>
        </div>
      ) : null}
    </div>
  )
}

export function RunDetailConsole({
  runId,
  returnTemplateId = null,
  returnRevisionId = null,
  showCreatedNotice = false,
}: {
  runId: number
  returnTemplateId?: number | null
  returnRevisionId?: number | null
  showCreatedNotice?: boolean
}) {
  const [runDetail, setRunDetail] = useState<DatamakepoolRunDetail | null>(null)
  const [runSteps, setRunSteps] = useState<DatamakepoolRunStep[]>([])
  const [pendingDangerousSql, setPendingDangerousSql] = useState<
    DatamakepoolPendingDangerousSqlItem[]
  >([])
  const [sqlAudits, setSqlAudits] = useState<DatamakepoolSqlAuditSummaryItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isStartingRun, setIsStartingRun] = useState(false)
  const [isConfirmingDangerousSql, setIsConfirmingDangerousSql] = useState(false)
  const [confirmReason, setConfirmReason] = useState("")

  const loadRun = useCallback(async (showRefreshingState: boolean = false) => {
    if (showRefreshingState) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
    }
    setError(null)

    try {
      const [detail, steps, pendingSql, runSqlAudits] = await Promise.all([
        getDatamakepoolRunDetail(runId),
        listDatamakepoolRunSteps(runId),
        getDatamakepoolPendingDangerousSql(runId),
        getDatamakepoolRunSqlAudits(runId),
      ])
      setRunDetail(detail)
      setRunSteps(steps)
      setPendingDangerousSql(pendingSql.items)
      setSqlAudits(runSqlAudits.items)
    } catch (nextError) {
      setRunDetail(null)
      setRunSteps([])
      setPendingDangerousSql([])
      setSqlAudits([])
      setError(nextError instanceof Error ? nextError.message : "Run 详情加载失败")
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [runId])

  const handleStartRun = useCallback(async () => {
    setIsStartingRun(true)
    setActionError(null)
    try {
      await startDatamakepoolRun(runId)
      await loadRun(true)
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "启动 Run 失败")
    } finally {
      setIsStartingRun(false)
    }
  }, [loadRun, runId])

  const handleConfirmDangerousSql = useCallback(async () => {
    const runStepIds = pendingDangerousSql
      .map((item) => item.run_step_id)
      .filter((value): value is number => typeof value === "number")

    if (!runStepIds.length) {
      setActionError("当前没有可确认的危险 SQL 步骤。")
      return
    }

    setIsConfirmingDangerousSql(true)
    setActionError(null)
    try {
      await confirmDatamakepoolDangerousSql(runId, {
        reason: confirmReason.trim() || undefined,
        run_step_ids: runStepIds,
        resume_execution: true,
      })
      setConfirmReason("")
      await loadRun(true)
    } catch (nextError) {
      setActionError(
        nextError instanceof Error ? nextError.message : "确认危险 SQL 并恢复执行失败"
      )
    } finally {
      setIsConfirmingDangerousSql(false)
    }
  }, [confirmReason, loadRun, pendingDangerousSql, runId])

  useEffect(() => {
    void loadRun()
  }, [loadRun])

  const runStatusMeta = getStatusMeta(runDetail?.status || "")
  const inputPayloadPreview = stringifyPreview(runDetail?.input_payload ?? null)
  const resolvedInputPreview = stringifyPreview(runDetail?.resolved_input ?? null)
  const finalOutputPreview = stringifyPreview(runDetail?.final_output ?? null)
  const succeededStepsCount = runSteps.filter((step) => step.status === "succeeded").length
  const pendingStepsCount = runSteps.filter((step) => step.status === "pending").length
  const blockedStepsCount = runSteps.filter((step) => step.status === "blocked").length
  const failedStepsCount = runSteps.filter((step) => step.status === "failed").length
  const runningStepsCount = runSteps.filter((step) => step.status === "running").length
  const pendingAuditCount = sqlAudits.filter((audit) => audit.status === "pending_confirmation").length
  const confirmedAuditCount = sqlAudits.filter((audit) => audit.status === "confirmed").length
  const returnTemplateHref =
    returnTemplateId && returnRevisionId
      ? `/datamakepool/templates?templateId=${returnTemplateId}&revisionId=${returnRevisionId}`
      : "/datamakepool/templates"

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F26 Run 工作台"
      title={`Run #${runId}`}
      description="这一页承接模板执行后的运行工作台：查看模板来源、步骤状态、危险 SQL 恢复动作，以及本次执行沉淀下来的输入输出快照。"
      metrics={[
        {
          label: "Run 状态",
          value: runDetail ? runStatusMeta.label : "--",
          hint: runDetail?.system_short || "等待加载",
        },
        {
          label: "模板版本",
          value: runDetail?.template_revision_id || "--",
          hint: runDetail?.template_id ? `模板 #${runDetail.template_id}` : "非模板入口",
        },
        {
          label: "步骤概况",
          value: runDetail ? `${succeededStepsCount}/${runDetail.steps_count}` : "--",
          hint: `待执行 ${pendingStepsCount} · 运行中 ${runningStepsCount} · 阻塞 ${blockedStepsCount} · 失败 ${failedStepsCount}`,
        },
        {
          label: "SQL 审计",
          value: String(sqlAudits.length),
          hint: `待确认 ${pendingAuditCount} · 已确认 ${confirmedAuditCount}`,
        },
      ]}
      actions={
        <div className="flex flex-wrap gap-2">
          {runDetail?.status === "pending" ? (
            <Button
              onClick={() => void handleStartRun()}
              disabled={isLoading || isRefreshing || isStartingRun}
            >
              {isStartingRun ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Workflow className="h-4 w-4" />
              )}
              开始执行
            </Button>
          ) : null}
          <Button
            asChild
            variant="outline"
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            <Link href={returnTemplateHref}>
              <ArrowLeft className="h-4 w-4" />
              返回模板
            </Link>
          </Button>
          <Button
            variant="outline"
            onClick={() => void loadRun(true)}
            disabled={isLoading || isRefreshing}
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            {isRefreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            刷新数据
          </Button>
        </div>
      }
    >
      <div className="grid h-full min-h-0 gap-6 p-6 xl:grid-cols-[minmax(0,1.1fr)_380px]">
        <div className="grid min-h-0 gap-6">
          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <GitBranch className="h-3.5 w-3.5" />
                执行步骤
              </div>
              <CardTitle>步骤列表</CardTitle>
              <CardDescription>最小闭环里先保证步骤状态和基础执行快照可见。</CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              {isLoading ? (
                <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载 Run 详情
                </div>
              ) : error ? (
                <div className="px-6 py-6">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                    {error}
                  </div>
                </div>
              ) : !runSteps.length ? (
                <div className="px-6 py-10 text-sm text-muted-foreground">
                  当前 Run 还没有可见步骤。
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="space-y-4 p-4">
                    {runSteps.map((step) => (
                      <RunStepCard key={step.id} step={step} />
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <AlertTriangle className="h-3.5 w-3.5" />
                SQL 审计摘要
              </div>
              <CardTitle>治理轨迹</CardTitle>
              <CardDescription>按 Run 维度查看本次执行里所有 SQL 审计记录，不只看待确认项。</CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              {isLoading ? (
                <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载 SQL 审计摘要
                </div>
              ) : error ? (
                <div className="px-6 py-6">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                    {error}
                  </div>
                </div>
              ) : !sqlAudits.length ? (
                <div className="px-6 py-10 text-sm text-muted-foreground">
                  当前 Run 还没有命中 SQL 审计记录。
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="space-y-4 p-4">
                    {sqlAudits.map((audit) => (
                      <SqlAuditCard key={audit.audit_id} audit={audit} />
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid min-h-0 gap-6">
          {showCreatedNotice ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
              已从模板版本创建正式 Run。当前页面可继续执行、查看步骤状态，或在阻塞后完成人工确认并恢复执行。
            </div>
          ) : null}

          {actionError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              {actionError}
            </div>
          ) : null}

          {pendingDangerousSql.length ? (
            <Card className="border-amber-200 bg-amber-50/70 backdrop-blur-sm">
              <CardHeader className="border-b border-amber-200/80">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-amber-700">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  危险 SQL 确认
                </div>
                <CardTitle className="text-amber-950">待人工确认</CardTitle>
                <CardDescription className="text-amber-800/80">
                  当前 Run 命中了需要人工确认的 SQL 步骤。确认后会直接恢复执行。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 pt-4">
                <div className="space-y-3">
                  {pendingDangerousSql.map((item) => {
                    const riskMeta = getRiskMeta(item.risk_level)
                    const targetObjectsLabel = formatTargetObjects(item.target_objects)

                    return (
                      <div
                        key={item.audit_id}
                        className="rounded-xl border border-amber-200/80 bg-background/80 p-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <div className="font-medium text-foreground">
                              {item.step_name || item.step_id || `步骤 #${item.run_step_id ?? "--"}`}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {item.step_id ? `step_id=${item.step_id}` : "未记录 step_id"}
                              {item.created_at ? ` · ${formatDate(item.created_at)}` : ""}
                            </div>
                          </div>
                          <Badge
                            variant="outline"
                            className={cn("font-medium", riskMeta.className)}
                          >
                            {riskMeta.label}
                          </Badge>
                        </div>

                        <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                          <div>阻塞原因：{item.confirmation_reason?.trim() || "未记录"}</div>
                          <div>目标对象：{targetObjectsLabel || "未记录"}</div>
                        </div>

                        {item.sql_preview ? (
                          <div className="mt-3">
                            <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                              SQL Preview
                            </div>
                            <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                              {item.sql_preview}
                            </pre>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium text-foreground">补充确认说明</div>
                  <Textarea
                    value={confirmReason}
                    onChange={(event) => setConfirmReason(event.target.value)}
                    placeholder="可选：补充本次人工复核结论，便于后续追溯。"
                    disabled={isConfirmingDangerousSql}
                  />
                </div>

                <Button
                  onClick={() => void handleConfirmDangerousSql()}
                  disabled={isLoading || isRefreshing || isConfirmingDangerousSql}
                  className="w-full"
                >
                  {isConfirmingDangerousSql ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Workflow className="h-4 w-4" />
                  )}
                  确认并恢复执行
                </Button>
              </CardContent>
            </Card>
          ) : null}

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <ArrowLeft className="h-3.5 w-3.5" />
                模板来源
              </div>
              <CardTitle>来源与回跳</CardTitle>
              <CardDescription>这张 Run 是从哪个模板版本创建出来的，以及回到模板台时的最小定位信息。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              <div>模板：{runDetail?.template_id ? `#${runDetail.template_id}` : "无"}</div>
              <div>
                模板版本：
                {runDetail?.template_revision_id ? `#${runDetail.template_revision_id}` : "无"}
              </div>
              <div>系统域：{runDetail?.system_short || "未标注"}</div>
              <div>回跳定位：{returnTemplateId && returnRevisionId ? "已保留" : "仅返回模板列表"}</div>
              <Button asChild variant="outline" className="w-full">
                <Link href={returnTemplateHref}>
                  <ArrowLeft className="h-4 w-4" />
                  回到对应模板版本
                </Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <GitBranch className="h-3.5 w-3.5" />
                执行概况
              </div>
              <CardTitle>状态拆解</CardTitle>
              <CardDescription>这里聚焦当前 Run 还卡在哪、已经跑过哪些步骤，以及是否存在待恢复的治理动作。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              <div>成功步骤：{succeededStepsCount}</div>
              <div>待执行步骤：{pendingStepsCount}</div>
              <div>执行中步骤：{runningStepsCount}</div>
              <div>阻塞步骤：{blockedStepsCount}</div>
              <div>失败步骤：{failedStepsCount}</div>
              <div>SQL 审计记录：{sqlAudits.length}</div>
              <div>待确认危险 SQL：{pendingDangerousSql.length}</div>
              <div>
                恢复提示：
                {pendingDangerousSql.length
                  ? "存在待确认项，确认后会继续执行剩余 pending 步骤"
                  : "当前没有需要人工确认的危险 SQL"}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Workflow className="h-3.5 w-3.5" />
                Run 摘要
              </div>
              <CardTitle>运行信息</CardTitle>
              <CardDescription>这里聚焦创建结果、模板挂载和输入真相源。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              <div>入口类型：{runDetail?.entry_type || "--"}</div>
              <div>系统域：{runDetail?.system_short || "未标注"}</div>
              <div>模板：{runDetail?.template_id ? `#${runDetail.template_id}` : "无"}</div>
              <div>
                模板版本：
                {runDetail?.template_revision_id ? `#${runDetail.template_revision_id}` : "无"}
              </div>
              <div>发起人：用户 #{runDetail?.initiator_user_id ?? "--"}</div>
              <div>任务来源：{runDetail?.source_task_id ? `#${runDetail.source_task_id}` : "无"}</div>
              <div>目标描述：{runDetail?.objective?.trim() || "无"}</div>
              <div>错误摘要：{runDetail?.error_summary?.trim() || "无"}</div>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Database className="h-3.5 w-3.5" />
                输入与结果
              </div>
              <CardTitle>输入快照</CardTitle>
              <CardDescription>创建 Run 时挂进去的输入和系统解析后的输入。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {inputPayloadPreview ? (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Input Payload
                  </div>
                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                    {inputPayloadPreview}
                  </pre>
                </div>
              ) : null}

              {resolvedInputPreview ? (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Resolved Input
                  </div>
                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                    {resolvedInputPreview}
                  </pre>
                </div>
              ) : null}

              {finalOutputPreview ? (
                <div>
                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Final Output
                  </div>
                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                    {finalOutputPreview}
                  </pre>
                </div>
              ) : null}

              {!inputPayloadPreview && !resolvedInputPreview && !finalOutputPreview ? (
                <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                  当前 Run 还没有输入或结果快照。
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </DatamakepoolShell>
  )
}
