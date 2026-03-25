"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  ArrowUpRight,
  Database,
  FileSearch,
  Filter,
  GitBranch,
  Layers3,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react"

import {
  type DatamakepoolTemplateAssetReference,
  type DatamakepoolTemplateRevisionSummary,
  type DatamakepoolTemplateSummary,
  listDatamakepoolTemplateRevisions,
  listDatamakepoolTemplates,
} from "@/lib/datamakepool"
import { DatamakepoolShell } from "@/components/datamakepool/datamakepool-shell"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
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
import { cn } from "@/lib/utils"

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

export function TemplateManagementConsole() {
  const [templates, setTemplates] = useState<DatamakepoolTemplateSummary[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [selectedRevisionId, setSelectedRevisionId] = useState<number | null>(null)
  const [revisions, setRevisions] = useState<DatamakepoolTemplateRevisionSummary[]>([])
  const [revisionsReloadTick, setRevisionsReloadTick] = useState(0)
  const [templatesError, setTemplatesError] = useState<string | null>(null)
  const [revisionsError, setRevisionsError] = useState<string | null>(null)
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(true)
  const [isLoadingRevisions, setIsLoadingRevisions] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [templateKeyword, setTemplateKeyword] = useState("")
  const [revisionStatusFilter, setRevisionStatusFilter] = useState("all")
  const selectedTemplateIdRef = useRef<number | null>(null)

  const selectedTemplate =
    templates.find((template) => template.template_id === selectedTemplateId) ?? null
  const selectedRevision =
    revisions.find((revision) => revision.revision_id === selectedRevisionId) ?? null

  useEffect(() => {
    selectedTemplateIdRef.current = selectedTemplateId
  }, [selectedTemplateId])

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
      setRevisions(nextRevisions)
      setSelectedRevisionId(nextRevisions[0]?.revision_id ?? null)
    } catch (error) {
      const message = error instanceof Error ? error.message : "模板版本列表加载失败"
      setRevisions([])
      setSelectedRevisionId(null)
      setRevisionsError(message)
    } finally {
      setIsLoadingRevisions(false)
    }
  }, [])

  useEffect(() => {
    void loadTemplates()
  }, [loadTemplates])

  useEffect(() => {
    if (selectedTemplateId === null) {
      setRevisions([])
      setRevisionsError(null)
      return
    }

    void loadRevisions(selectedTemplateId)
  }, [selectedTemplateId, revisionsReloadTick, loadRevisions])

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

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F24 模板管理台"
      title="模板工作台"
      description="先把模板列表、版本沉淀和资产引用关系统一收进一个工作台视图里。视觉上保持站点主题一致，交互上优先保障扫描效率、状态可见性和后续页面复用。"
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
      <div className="grid h-full min-h-0 gap-6 p-6 2xl:grid-cols-[300px_minmax(0,1fr)_320px]">
        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Layers3 className="h-3.5 w-3.5" />
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
                当前页面保留版本概览和右侧检查面板，不做复杂编辑。
              </CardContent>
            </Card>

            <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
              <CardHeader className="gap-2">
                <CardDescription>当前范围</CardDescription>
                <CardTitle className="text-base">F24 首批 MVP</CardTitle>
              </CardHeader>
              <CardContent className="pt-0 text-sm text-muted-foreground">
                不包含审核动作、模板详情编辑、执行入口。
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
                  版本列表来自 `/api/datamakepool/templates/{template_id}/revisions`
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
              版本检查面板
            </div>
            <CardTitle>选中版本摘要</CardTitle>
            <CardDescription>把审核状态、资产引用和步骤命中集中在一个侧栏里，减少来回切换。</CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            {selectedRevision ? (
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.16em] text-primary/80">
                          当前选中
                        </div>
                        <div className="mt-2 text-lg font-semibold text-foreground">
                          V{selectedRevision.version_no}
                        </div>
                      </div>
                      <Badge
                        variant="outline"
                        className={cn(
                          "font-medium",
                          getRevisionStatusMeta(selectedRevision.status).className
                        )}
                      >
                        {getRevisionStatusMeta(selectedRevision.status).label}
                      </Badge>
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground">
                      修订 #{selectedRevision.revision_id} · 步骤 {selectedRevision.steps_count}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Sparkles className="h-4 w-4 text-primary" />
                      审核与沉淀
                    </div>
                    <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                      <div>创建人：用户 #{selectedRevision.created_by}</div>
                      <div>
                        审核人：
                        {selectedRevision.reviewed_by
                          ? `用户 #${selectedRevision.reviewed_by}`
                          : "未审核"}
                      </div>
                      <div>
                        审核备注：
                        {selectedRevision.review_comment?.trim()
                          ? selectedRevision.review_comment
                          : "无"}
                      </div>
                      <div>
                        来源 Run：
                        {selectedRevision.source_run_id
                          ? `#${selectedRevision.source_run_id}`
                          : "未挂载"}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
                    <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      资产关系
                    </div>
                    {selectedRevision.asset_references.length ? (
                      <div className="mt-3 space-y-3">
                        {selectedRevision.asset_references.map((reference) => (
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
                        ))}
                      </div>
                    ) : (
                      <div className="mt-3 rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                        当前版本还没有结构化资产引用。
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                    本批仍保持在 F24 首批 MVP，只做模板工作台的浏览与检查，不做审核提交、版本编辑和执行入口。
                  </div>
                </div>
              </ScrollArea>
            ) : (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                先在中间区域选择一个版本，再查看详情。
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DatamakepoolShell>
  )
}
