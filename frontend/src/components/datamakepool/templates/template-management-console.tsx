"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  ArrowUpRight,
  CheckCheck,
  Database,
  FileSearch,
  Filter,
  GitBranch,
  GitPullRequest,
  Layers,
  ListTree,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  Workflow,
} from "lucide-react"

import {
  approveDatamakepoolTemplateRevision,
  getDatamakepoolTemplateRevisionDetail,
  submitDatamakepoolTemplateRevisionReview,
  type DatamakepoolTemplateAssetReference,
  type DatamakepoolTemplateRevisionDetail,
  type DatamakepoolTemplateRevisionStepDetail,
  type DatamakepoolTemplateRevisionSummary,
  type DatamakepoolTemplateSummary,
  listDatamakepoolTemplateRevisions,
  listDatamakepoolTemplates,
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

function getAssetTypeLabel(assetType: string): string {
  if (assetType === "http") {
    return "HTTP"
  }
  if (assetType === "sql") {
    return "SQL"
  }
  return assetType.toUpperCase()
}

function summarizeStepNames(reference: DatamakepoolTemplateAssetReference): string {
  if (!reference.step_names.length) {
    return "未记录步骤"
  }

  const visibleStepNames = reference.step_names.slice(0, 2).join("、")
  if (reference.step_names.length <= 2) {
    return visibleStepNames
  }
  return `${visibleStepNames} 等 ${reference.step_names.length} 步`
}

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return "未记录"
  }
  return formatDate(value)
}

function getGraphNodeCount(graph: Record<string, unknown> | null | undefined): number {
  const nodes = graph && typeof graph === "object" ? graph.nodes : null
  return Array.isArray(nodes) ? nodes.length : 0
}

function getObjectEntryCount(payload: Record<string, unknown> | null | undefined): number {
  if (!payload) {
    return 0
  }
  return Object.keys(payload).length
}

function stringifyPreview(payload: Record<string, unknown> | null | undefined): string | null {
  if (!payload || !Object.keys(payload).length) {
    return null
  }
  return JSON.stringify(payload, null, 2)
}

function AssetReferencePill({
  reference,
}: {
  reference: DatamakepoolTemplateAssetReference
}) {
  const assetName = reference.name || `资产 #${reference.asset_id}`
  const assetHint = reference.version_id ? `v${reference.version_id}` : `#${reference.asset_id}`

  return (
    <div className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2">
      <div className="flex items-center gap-2 text-sm">
        <Badge variant="outline" className="border-border/70 bg-background text-foreground">
          {getAssetTypeLabel(reference.asset_type)}
        </Badge>
        <span className="font-medium text-foreground">{assetName}</span>
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        {reference.system_short || "未标注系统"} · {assetHint}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{summarizeStepNames(reference)}</div>
    </div>
  )
}

function RevisionCard({
  revision,
  latestPublishedRevisionId,
  isSelected,
  onSelect,
}: {
  revision: DatamakepoolTemplateRevisionSummary
  latestPublishedRevisionId?: number | null
  isSelected: boolean
  onSelect: () => void
}) {
  const statusMeta = getRevisionStatusMeta(revision.status)
  const isLatestPublished = latestPublishedRevisionId === revision.revision_id

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-2xl border p-4 text-left shadow-sm transition-all",
        isSelected
          ? "border-primary/35 bg-primary/10 shadow-[0_12px_30px_-20px_hsl(var(--primary)/0.65)]"
          : "border-border/80 bg-card/90 hover:border-primary/20 hover:bg-muted/30"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className={cn("font-medium", statusMeta.className)}>
            {statusMeta.label}
          </Badge>
          {isLatestPublished ? (
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
              当前发布
            </Badge>
          ) : null}
          <div className="text-sm font-semibold text-foreground">
            V{revision.version_no} / 修订 #{revision.revision_id}
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          步骤 {revision.steps_count} · 来源 Run{" "}
          {revision.source_run_id ? `#${revision.source_run_id}` : "未挂载"}
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
            <Database className="h-4 w-4 text-muted-foreground" />
            资产引用
          </div>
          {revision.asset_references.length ? (
            <div className="grid gap-2 md:grid-cols-2">
              {revision.asset_references.map((reference) => (
                <AssetReferencePill
                  key={`${reference.asset_type}-${reference.asset_id}-${reference.version_id ?? "logic"}`}
                  reference={reference}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
              当前版本还没有沉淀结构化资产引用。
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border/70 bg-muted/20 p-3 text-sm">
          <div className="font-medium text-foreground">版本摘要</div>
          <div className="mt-3 space-y-2 text-muted-foreground">
            <div>创建人：用户 #{revision.created_by}</div>
            <div>
              审核人：
              {revision.reviewed_by ? `用户 #${revision.reviewed_by}` : "未审核"}
            </div>
            <div>
              审核备注：
              {revision.review_comment?.trim() ? revision.review_comment : "无"}
            </div>
            <div>引用资产：{revision.asset_references.length} 项</div>
          </div>
        </div>
      </div>
    </button>
  )
}

function StepDetailCard({ step }: { step: DatamakepoolTemplateRevisionStepDetail }) {
  const dependsOnLabel = step.depends_on.length ? step.depends_on.join("、") : "无"
  const editableFieldsLabel = step.editable_fields.length
    ? step.editable_fields.map((field) => String(field)).join("、")
    : "无"

  return (
    <div className="rounded-xl border border-border/70 bg-muted/20 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">{step.name}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {step.step_type} · step_id={step.step_id}
          </div>
        </div>
        <Badge variant="outline" className="border-border/70 bg-background text-foreground">
          {step.depends_on.length} 依赖
        </Badge>
      </div>
      <div className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
        <div>依赖步骤：{dependsOnLabel}</div>
        <div>可编辑字段：{editableFieldsLabel}</div>
        <div>设计意图字段：{Object.keys(step.design_intent || {}).length} 项</div>
        <div>收敛依据字段：{Object.keys(step.resolution_rationale || {}).length} 项</div>
      </div>
    </div>
  )
}

export function TemplateManagementConsole() {
  const [templates, setTemplates] = useState<DatamakepoolTemplateSummary[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [selectedRevisionId, setSelectedRevisionId] = useState<number | null>(null)
  const [revisions, setRevisions] = useState<DatamakepoolTemplateRevisionSummary[]>([])
  const [selectedRevisionDetail, setSelectedRevisionDetail] =
    useState<DatamakepoolTemplateRevisionDetail | null>(null)
  const [revisionsReloadTick, setRevisionsReloadTick] = useState(0)
  const [templatesError, setTemplatesError] = useState<string | null>(null)
  const [revisionsError, setRevisionsError] = useState<string | null>(null)
  const [revisionDetailError, setRevisionDetailError] = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(true)
  const [isLoadingRevisions, setIsLoadingRevisions] = useState(false)
  const [isLoadingRevisionDetail, setIsLoadingRevisionDetail] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isSubmittingReview, setIsSubmittingReview] = useState(false)
  const [isApprovingRevision, setIsApprovingRevision] = useState(false)
  const [templateKeyword, setTemplateKeyword] = useState("")
  const [revisionStatusFilter, setRevisionStatusFilter] = useState("all")
  const selectedTemplateIdRef = useRef<number | null>(null)
  const selectedRevisionIdRef = useRef<number | null>(null)

  const selectedTemplate =
    templates.find((template) => template.template_id === selectedTemplateId) ?? null
  const selectedRevision =
    revisions.find((revision) => revision.revision_id === selectedRevisionId) ?? null
  const revisionStatus = selectedRevisionDetail?.status ?? selectedRevision?.status ?? ""
  const revisionMeta = getRevisionStatusMeta(revisionStatus)

  useEffect(() => {
    selectedTemplateIdRef.current = selectedTemplateId
  }, [selectedTemplateId])

  useEffect(() => {
    selectedRevisionIdRef.current = selectedRevisionId
  }, [selectedRevisionId])

  const loadTemplates = useCallback(async (showRefreshingState: boolean = false) => {
    if (showRefreshingState) {
      setIsRefreshing(true)
    } else {
      setIsLoadingTemplates(true)
    }
    setTemplatesError(null)

    try {
      const nextTemplates = await listDatamakepoolTemplates()
      const currentTemplateId = selectedTemplateIdRef.current
      const nextSelectedTemplateId =
        currentTemplateId !== null &&
        nextTemplates.some((item) => item.template_id === currentTemplateId)
          ? currentTemplateId
          : nextTemplates[0]?.template_id ?? null

      setTemplates(nextTemplates)
      setSelectedTemplateId(nextSelectedTemplateId)
      if (nextSelectedTemplateId !== null) {
        setRevisionsReloadTick((currentTick) => currentTick + 1)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "模板列表加载失败"
      setTemplates([])
      setSelectedTemplateId(null)
      setTemplatesError(message)
    } finally {
      setIsLoadingTemplates(false)
      setIsRefreshing(false)
    }
  }, [])

  const loadRevisions = useCallback(async (templateId: number) => {
    setIsLoadingRevisions(true)
    setRevisionsError(null)

    try {
      const nextRevisions = await listDatamakepoolTemplateRevisions(templateId)
      const currentRevisionId = selectedRevisionIdRef.current
      const nextSelectedRevisionId =
        currentRevisionId !== null &&
        nextRevisions.some((revision) => revision.revision_id === currentRevisionId)
          ? currentRevisionId
          : nextRevisions[0]?.revision_id ?? null

      setRevisions(nextRevisions)
      setSelectedRevisionId(nextSelectedRevisionId)
    } catch (error) {
      const message = error instanceof Error ? error.message : "模板版本列表加载失败"
      setRevisions([])
      setSelectedRevisionId(null)
      setRevisionsError(message)
    } finally {
      setIsLoadingRevisions(false)
    }
  }, [])

  const loadRevisionDetail = useCallback(async (revisionId: number) => {
    setIsLoadingRevisionDetail(true)
    setRevisionDetailError(null)

    try {
      const detail = await getDatamakepoolTemplateRevisionDetail(revisionId)
      if (selectedRevisionIdRef.current === revisionId) {
        setSelectedRevisionDetail(detail)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "模板版本详情加载失败"
      if (selectedRevisionIdRef.current === revisionId) {
        setSelectedRevisionDetail(null)
        setRevisionDetailError(message)
      }
    } finally {
      if (selectedRevisionIdRef.current === revisionId) {
        setIsLoadingRevisionDetail(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadTemplates()
  }, [loadTemplates])

  useEffect(() => {
    if (selectedTemplateId === null) {
      setRevisions([])
      setRevisionsError(null)
      setSelectedRevisionId(null)
      return
    }

    void loadRevisions(selectedTemplateId)
  }, [selectedTemplateId, revisionsReloadTick, loadRevisions])

  useEffect(() => {
    if (selectedRevisionId === null) {
      setSelectedRevisionDetail(null)
      setRevisionDetailError(null)
      setIsLoadingRevisionDetail(false)
      return
    }

    void loadRevisionDetail(selectedRevisionId)
  }, [selectedRevisionId, loadRevisionDetail])

  const filteredTemplates = templates.filter((template) => {
    if (!templateKeyword.trim()) {
      return true
    }

    const normalizedKeyword = templateKeyword.trim().toLowerCase()
    return (
      template.name.toLowerCase().includes(normalizedKeyword) ||
      (template.description || "").toLowerCase().includes(normalizedKeyword) ||
      template.system_short.toLowerCase().includes(normalizedKeyword)
    )
  })

  const filteredRevisions = revisions.filter((revision) => {
    if (revisionStatusFilter === "all") {
      return true
    }
    return revision.status === revisionStatusFilter
  })

  const totalAssetReferences = revisions.reduce(
    (count, revision) => count + revision.asset_references.length,
    0
  )

  useEffect(() => {
    if (!filteredRevisions.length) {
      setSelectedRevisionId(null)
      return
    }

    if (!filteredRevisions.some((revision) => revision.revision_id === selectedRevisionId)) {
      setSelectedRevisionId(filteredRevisions[0].revision_id)
    }
  }, [filteredRevisions, selectedRevisionId])

  useEffect(() => {
    setActionFeedback(null)
    setActionError(null)
  }, [selectedRevisionId])

  const statusMetrics = [
    {
      label: "可见模板",
      value: String(templates.length),
      hint: "当前权限范围内的逻辑模板数",
    },
    {
      label: "当前版本",
      value: selectedTemplate ? String(selectedTemplate.revisions_count) : "--",
      hint: selectedTemplate ? `模板 #${selectedTemplate.template_id}` : "等待选择模板",
    },
    {
      label: "资产引用",
      value: String(totalAssetReferences),
      hint: "版本列表累计沉淀的结构化引用",
    },
  ]

  const handleSubmitReview = useCallback(async () => {
    if (selectedRevisionId === null || selectedTemplateId === null) {
      return
    }

    setIsSubmittingReview(true)
    setActionFeedback(null)
    setActionError(null)
    try {
      await submitDatamakepoolTemplateRevisionReview(selectedRevisionId)
      setActionFeedback(`修订 #${selectedRevisionId} 已提交审核。`)
      await loadRevisions(selectedTemplateId)
      await loadRevisionDetail(selectedRevisionId)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "模板送审失败")
    } finally {
      setIsSubmittingReview(false)
    }
  }, [loadRevisionDetail, loadRevisions, selectedRevisionId, selectedTemplateId])

  const handleApproveRevision = useCallback(async () => {
    if (selectedRevisionId === null) {
      return
    }

    setIsApprovingRevision(true)
    setActionFeedback(null)
    setActionError(null)
    try {
      await approveDatamakepoolTemplateRevision(selectedRevisionId)
      setActionFeedback(`修订 #${selectedRevisionId} 已审批通过并切换为当前发布版本。`)
      await loadTemplates(true)
      await loadRevisionDetail(selectedRevisionId)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "模板审批失败")
    } finally {
      setIsApprovingRevision(false)
    }
  }, [loadRevisionDetail, loadTemplates, selectedRevisionId])

  const businessGraphNodeCount = getGraphNodeCount(
    selectedRevisionDetail?.business_graph_snapshot ?? null
  )
  const technicalGraphNodeCount = getGraphNodeCount(selectedRevisionDetail?.technical_graph ?? null)
  const inputSchemaPreview = stringifyPreview(selectedRevisionDetail?.input_schema ?? null)
  const outputMappingPreview = stringifyPreview(selectedRevisionDetail?.output_mapping ?? null)

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F24 模板管理台"
      title="模板工作台"
      description="这一批把模板版本详情和审核动作正式接进工作台。交互上仍然坚持扫描效率优先，让审核人能在同一屏里完成查看、判断和状态推进。"
      metrics={statusMetrics}
      actions={
        <Button
          variant="outline"
          onClick={() => void loadTemplates(true)}
          disabled={isLoadingTemplates || isRefreshing}
          className="border-border/80 bg-background/70 backdrop-blur-sm"
        >
          {isRefreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          刷新数据
        </Button>
      }
    >
      <div className="grid h-full min-h-0 gap-6 p-6 2xl:grid-cols-[300px_minmax(0,1fr)_360px]">
        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Layers className="h-3.5 w-3.5" />
              模板检索
            </div>
            <CardTitle>模板列表</CardTitle>
            <CardDescription>以逻辑模板为粒度浏览当前可见范围。</CardDescription>
            <div className="relative mt-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={templateKeyword}
                onChange={(event) => setTemplateKeyword(event.target.value)}
                placeholder="搜索模板名、说明或 system_short"
                className="border-border/80 bg-background/70 pl-9"
              />
            </div>
          </CardHeader>
          <CardContent className="flex-1 min-h-0 px-0">
            {isLoadingTemplates ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载模板列表
              </div>
            ) : templatesError ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {templatesError}
                </div>
              </div>
            ) : filteredTemplates.length === 0 ? (
              <div className="px-6 py-10 text-sm text-muted-foreground">
                没有匹配当前搜索条件的模板。
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-3 p-3">
                  {filteredTemplates.map((template) => {
                    const isActive = template.template_id === selectedTemplateId
                    return (
                      <button
                        key={template.template_id}
                        type="button"
                        onClick={() => setSelectedTemplateId(template.template_id)}
                        className={cn(
                          "w-full rounded-2xl border px-4 py-4 text-left transition-all",
                          isActive
                            ? "border-primary/35 bg-primary/10 shadow-[0_12px_30px_-20px_hsl(var(--primary)/0.65)]"
                            : "border-border/70 bg-background/70 hover:border-primary/20 hover:bg-muted/30"
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-medium text-foreground">{template.name}</div>
                            <div className="mt-2 text-xs text-muted-foreground">
                              模板 #{template.template_id} · 版本 {template.revisions_count}
                            </div>
                          </div>
                          <Badge
                            variant="outline"
                            className="border-border/70 bg-background/70 text-muted-foreground"
                          >
                            {template.system_short}
                          </Badge>
                        </div>
                        <div className="mt-3 text-sm leading-6 text-muted-foreground">
                          {template.description?.trim() || "暂无模板说明"}
                        </div>
                        <div className="mt-3 flex items-center gap-2 text-xs text-primary/80">
                          查看版本
                          <ArrowUpRight className="h-3.5 w-3.5" />
                        </div>
                      </button>
                    )
                  })}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <div className="grid min-h-0 gap-6">
          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
              <CardHeader className="gap-2">
                <CardDescription>当前模板</CardDescription>
                <CardTitle className="text-base">
                  {selectedTemplate?.name || "未选择模板"}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 text-sm text-muted-foreground">
                {selectedTemplate ? (
                  <>
                    <div>系统域：{selectedTemplate.system_short}</div>
                    <div className="mt-1">逻辑模板：#{selectedTemplate.template_id}</div>
                  </>
                ) : (
                  "从左侧选择一个模板后查看版本。"
                )}
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
              <CardHeader className="gap-2">
                <CardDescription>版本数量</CardDescription>
                <CardTitle className="text-base">
                  {selectedTemplate ? `${selectedTemplate.revisions_count} 个版本` : "--"}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 text-sm text-muted-foreground">
                当前批次支持版本详情查看与审核状态推进，不开放复杂编辑。
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
              <CardHeader className="gap-2">
                <CardDescription>当前范围</CardDescription>
                <CardTitle className="text-base">F24 下一批闭环</CardTitle>
              </CardHeader>
              <CardContent className="pt-0 text-sm text-muted-foreground">
                已接入版本详情与审核动作，执行入口仍留在后续批次。
              </CardContent>
            </Card>
          </div>

          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <CardTitle>版本列表</CardTitle>
                  <CardDescription>
                    {selectedTemplate
                      ? `模板 #${selectedTemplate.template_id} 的全部版本`
                      : "请选择左侧模板"}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <GitBranch className="h-4 w-4" />
                  <span>版本列表来自</span>
                  <code>/api/datamakepool/templates/{"{template_id}"}/revisions</code>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <Tabs value={revisionStatusFilter} onValueChange={setRevisionStatusFilter}>
                  <TabsList className="bg-muted/60">
                    <TabsTrigger value="all">全部</TabsTrigger>
                    <TabsTrigger value="draft">草稿</TabsTrigger>
                    <TabsTrigger value="pending_review">待审核</TabsTrigger>
                    <TabsTrigger value="published">已发布</TabsTrigger>
                  </TabsList>
                </Tabs>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Filter className="h-3.5 w-3.5" />
                  当前筛选后 {filteredRevisions.length} 个版本
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex-1 min-h-0 px-0">
              {selectedTemplate === null ? (
                <div className="flex h-full items-center justify-center px-6 py-12 text-sm text-muted-foreground">
                  先从左侧选择一个模板，再查看版本沉淀情况。
                </div>
              ) : isLoadingRevisions ? (
                <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载版本列表
                </div>
              ) : revisionsError ? (
                <div className="px-6 py-6">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                    {revisionsError}
                  </div>
                </div>
              ) : filteredRevisions.length === 0 ? (
                <div className="px-6 py-10 text-sm text-muted-foreground">
                  当前筛选条件下没有匹配版本。
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="space-y-4 p-4">
                    {filteredRevisions.map((revision) => (
                      <RevisionCard
                        key={revision.revision_id}
                        revision={revision}
                        latestPublishedRevisionId={selectedTemplate.latest_published_revision_id}
                        isSelected={revision.revision_id === selectedRevisionId}
                        onSelect={() => setSelectedRevisionId(revision.revision_id)}
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
              <FileSearch className="h-3.5 w-3.5" />
              版本详情与动作
            </div>
            <CardTitle>选中版本详情</CardTitle>
            <CardDescription>详情读取和审核动作共用同一侧栏，减少状态切换成本。</CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            {selectedRevision === null ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                先在中间区域选择一个版本，再查看详情。
              </div>
            ) : isLoadingRevisionDetail && selectedRevisionDetail === null ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载版本详情
              </div>
            ) : revisionDetailError ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {revisionDetailError}
                </div>
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.16em] text-primary/80">
                          当前选中
                        </div>
                        <div className="mt-2 text-lg font-semibold text-foreground">
                          {selectedRevisionDetail?.template_name || selectedTemplate?.name || "模板版本"}
                        </div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          V{selectedRevisionDetail?.version_no ?? selectedRevision.version_no} / 修订 #
                          {selectedRevisionDetail?.revision_id ?? selectedRevision.revision_id}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <Badge variant="outline" className={cn("font-medium", revisionMeta.className)}>
                          {revisionMeta.label}
                        </Badge>
                        {selectedRevisionDetail?.is_latest_published ? (
                          <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
                            当前发布
                          </Badge>
                        ) : null}
                      </div>
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground">
                      系统域：{selectedRevisionDetail?.system_short || selectedTemplate?.system_short || "未标注"}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <GitPullRequest className="h-4 w-4 text-primary" />
                      审核动作
                    </div>
                    <div className="mt-3 space-y-3">
                      {actionFeedback ? (
                        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                          {actionFeedback}
                        </div>
                      ) : null}
                      {actionError ? (
                        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                          {actionError}
                        </div>
                      ) : null}

                      <div className="flex flex-wrap gap-2">
                        {revisionStatus === "draft" ? (
                          <Button
                            size="sm"
                            onClick={() => void handleSubmitReview()}
                            disabled={isSubmittingReview || isApprovingRevision}
                          >
                            {isSubmittingReview ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <GitPullRequest className="h-4 w-4" />
                            )}
                            提交审核
                          </Button>
                        ) : null}

                        {revisionStatus === "pending_review" ? (
                          <Button
                            size="sm"
                            onClick={() => void handleApproveRevision()}
                            disabled={isSubmittingReview || isApprovingRevision}
                          >
                            {isApprovingRevision ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <CheckCheck className="h-4 w-4" />
                            )}
                            审批通过
                          </Button>
                        ) : null}

                        {revisionStatus === "published" ? (
                          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                            当前版本已发布，无需重复审批。
                          </div>
                        ) : null}
                      </div>

                      <div className="text-xs leading-5 text-muted-foreground">
                        审核规则沿用后端治理口径：只有待审核版本可审批，且创建者不能自审。
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Sparkles className="h-4 w-4 text-primary" />
                      审核与沉淀
                    </div>
                    <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                      <div>创建人：用户 #{selectedRevisionDetail?.created_by ?? selectedRevision.created_by}</div>
                      <div>
                        审核人：
                        {selectedRevisionDetail?.reviewed_by
                          ? `用户 #${selectedRevisionDetail.reviewed_by}`
                          : "未审核"}
                      </div>
                      <div>
                        审核备注：
                        {selectedRevisionDetail?.review_comment?.trim()
                          ? selectedRevisionDetail.review_comment
                          : "无"}
                      </div>
                      <div>
                        来源 Run：
                        {selectedRevisionDetail?.source_run_id
                          ? `#${selectedRevisionDetail.source_run_id}`
                          : "未挂载"}
                      </div>
                      <div>创建时间：{formatDateLabel(selectedRevisionDetail?.created_at)}</div>
                      <div>审核时间：{formatDateLabel(selectedRevisionDetail?.reviewed_at)}</div>
                      <div>发布时间：{formatDateLabel(selectedRevisionDetail?.published_at)}</div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      资产关系
                    </div>
                    {(selectedRevisionDetail?.asset_references || selectedRevision.asset_references).length ? (
                      <div className="mt-3 space-y-3">
                        {(selectedRevisionDetail?.asset_references || selectedRevision.asset_references).map(
                          (reference) => (
                            <div
                              key={`${reference.asset_type}-${reference.asset_id}-${reference.version_id ?? "logic"}-inspector`}
                              className="rounded-xl border border-border/70 bg-muted/20 p-3"
                            >
                              <div className="flex items-center gap-2">
                                <Badge
                                  variant="outline"
                                  className="border-border/70 bg-background text-foreground"
                                >
                                  {getAssetTypeLabel(reference.asset_type)}
                                </Badge>
                                <div className="font-medium text-foreground">
                                  {reference.name || `资产 #${reference.asset_id}`}
                                </div>
                              </div>
                              <div className="mt-2 text-xs leading-5 text-muted-foreground">
                                {reference.system_short || "未标注系统"} · 资产 #{reference.asset_id}
                                {reference.version_id ? ` · 版本 ${reference.version_id}` : ""}
                              </div>
                              <div className="mt-2 text-xs leading-5 text-muted-foreground">
                                {reference.step_names.length
                                  ? `命中步骤：${reference.step_names.join("、")}`
                                  : "未记录命中步骤"}
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    ) : (
                      <div className="mt-3 rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                        当前版本还没有结构化资产引用。
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <ListTree className="h-4 w-4 text-muted-foreground" />
                      步骤详情
                    </div>
                    {selectedRevisionDetail?.steps.length ? (
                      <div className="mt-3 space-y-3">
                        {selectedRevisionDetail.steps.map((step) => (
                          <StepDetailCard key={step.step_id} step={step} />
                        ))}
                      </div>
                    ) : (
                      <div className="mt-3 rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                        当前版本未记录结构化步骤详情。
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Workflow className="h-4 w-4 text-primary" />
                      图与契约
                    </div>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-sm text-muted-foreground">
                        <div className="font-medium text-foreground">图快照</div>
                        <div className="mt-2">业务图节点：{businessGraphNodeCount}</div>
                        <div className="mt-1">技术图节点：{technicalGraphNodeCount}</div>
                      </div>
                      <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-sm text-muted-foreground">
                        <div className="font-medium text-foreground">输入输出契约</div>
                        <div className="mt-2">
                          输入结构字段：{getObjectEntryCount(selectedRevisionDetail?.input_schema ?? null)}
                        </div>
                        <div className="mt-1">
                          输出映射字段：{getObjectEntryCount(selectedRevisionDetail?.output_mapping ?? null)}
                        </div>
                      </div>
                    </div>

                    {inputSchemaPreview ? (
                      <div className="mt-3">
                        <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          Input Schema
                        </div>
                        <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                          {inputSchemaPreview}
                        </pre>
                      </div>
                    ) : null}

                    {outputMappingPreview ? (
                      <div className="mt-3">
                        <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          Output Mapping
                        </div>
                        <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                          {outputMappingPreview}
                        </pre>
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                    当前批次聚焦“模板版本详情 + 审核动作”闭环，不在这里扩展版本编辑和执行入口。
                  </div>
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </DatamakepoolShell>
  )
}
