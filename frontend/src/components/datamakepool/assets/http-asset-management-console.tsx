"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowRight, Layers, Loader2, Network, Plus, RefreshCw } from "lucide-react"

import {
  createDatamakepoolHttpAsset,
  listDatamakepoolHttpAssets,
  type DatamakepoolHttpAssetSummary,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { formatDate } from "@/lib/utils"

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return "未记录"
  }
  return formatDate(value)
}

function parseOptionalJson(text: string, fieldLabel: string): Record<string, unknown> {
  const normalized = text.trim()
  if (!normalized) {
    return {}
  }

  try {
    const parsed = JSON.parse(normalized)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`${fieldLabel} 必须是 JSON 对象。`)
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    if (error instanceof Error && error.message.includes("必须是 JSON 对象")) {
      throw error
    }
    throw new Error(`${fieldLabel} 需要填写合法 JSON。`)
  }
}

const HTTP_METHOD_OPTIONS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const

export function HttpAssetManagementConsole() {
  const [assets, setAssets] = useState<DatamakepoolHttpAssetSummary[]>([])
  const [keyword, setKeyword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isCreating, setIsCreating] = useState(false)

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [systemShort, setSystemShort] = useState("")
  const [method, setMethod] = useState<(typeof HTTP_METHOD_OPTIONS)[number]>("GET")
  const [baseUrl, setBaseUrl] = useState("")
  const [pathTemplate, setPathTemplate] = useState("")
  const [requestSchemaText, setRequestSchemaText] = useState("")
  const [extractionRulesText, setExtractionRulesText] = useState("")
  const [enabled, setEnabled] = useState(true)

  const loadAssets = useCallback(async (showRefreshingState: boolean = false) => {
    if (showRefreshingState) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
    }
    setError(null)

    try {
      const nextAssets = await listDatamakepoolHttpAssets()
      setAssets(nextAssets)
    } catch (nextError) {
      setAssets([])
      setError(nextError instanceof Error ? nextError.message : "HTTP 资产列表加载失败")
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void loadAssets()
  }, [loadAssets])

  const filteredAssets = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    if (!normalizedKeyword) {
      return assets
    }

    return assets.filter((asset) => {
      return (
        asset.name.toLowerCase().includes(normalizedKeyword) ||
        (asset.description || "").toLowerCase().includes(normalizedKeyword) ||
        asset.system_short.toLowerCase().includes(normalizedKeyword) ||
        asset.base_url.toLowerCase().includes(normalizedKeyword)
      )
    })
  }, [assets, keyword])

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !systemShort.trim() || !baseUrl.trim() || !pathTemplate.trim()) {
      setActionError("名称、system_short、Base URL、Path Template 为必填项。")
      setActionFeedback(null)
      return
    }

    setIsCreating(true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const requestSchema = parseOptionalJson(requestSchemaText, "Request Schema")
      const extractionRules = parseOptionalJson(extractionRulesText, "Response Extraction Rules")
      const created = await createDatamakepoolHttpAsset({
        name: name.trim(),
        description: description.trim() || undefined,
        system_short: systemShort.trim(),
        method,
        base_url: baseUrl.trim(),
        path_template: pathTemplate.trim(),
        request_schema: requestSchema,
        response_extraction_rules: extractionRules,
        enabled,
      })
      setActionFeedback(`HTTP 资产 #${created.asset_id} 创建成功。`)
      setName("")
      setDescription("")
      setSystemShort("")
      setMethod("GET")
      setBaseUrl("")
      setPathTemplate("")
      setRequestSchemaText("")
      setExtractionRulesText("")
      setEnabled(true)
      await loadAssets(true)
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "HTTP 资产创建失败")
    } finally {
      setIsCreating(false)
    }
  }, [
    baseUrl,
    description,
    enabled,
    extractionRulesText,
    loadAssets,
    method,
    name,
    pathTemplate,
    requestSchemaText,
    systemShort,
  ])

  const enabledCount = assets.filter((asset) => asset.enabled).length

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F22 HTTP 资产中心"
      title="HTTP 资产工作台"
      description="这一页先承接 HTTP 资产中心的前台 MVP：列表、最小创建入口，以及跳转到资产详情和模板反向引用视图。"
      metrics={[
        {
          label: "资产总数",
          value: String(assets.length),
          hint: "当前权限范围内可见 HTTP 资产",
        },
        {
          label: "启用中",
          value: String(enabledCount),
          hint: `停用 ${assets.length - enabledCount}`,
        },
        {
          label: "搜索结果",
          value: String(filteredAssets.length),
          hint: keyword.trim() ? `关键词：${keyword.trim()}` : "未过滤",
        },
      ]}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" className="border-border/80 bg-background/70 backdrop-blur-sm">
            <Link href="/datamakepool/templates">
              <Layers className="h-4 w-4" />
              模板台
            </Link>
          </Button>
          <Button asChild variant="outline" className="border-border/80 bg-background/70 backdrop-blur-sm">
            <Link href="/datamakepool/sql-assets">
              <ArrowRight className="h-4 w-4" />
              SQL 资产
            </Link>
          </Button>
          <Button
            variant="outline"
            onClick={() => void loadAssets(true)}
            disabled={isLoading || isRefreshing}
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
      <div className="grid h-full min-h-0 gap-6 p-6 xl:grid-cols-[minmax(0,1.2fr)_420px]">
        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-3">
              <Network className="h-4 w-4 text-primary" />
              <div>
                <CardTitle>资产列表</CardTitle>
                <CardDescription>先承接可见资产检索和详情跳转，后续再补更多管理动作。</CardDescription>
              </div>
            </div>
            <Input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="按名称、system_short、Base URL 搜索"
            />
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            {isLoading ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载 HTTP 资产
              </div>
            ) : error ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {error}
                </div>
              </div>
            ) : !filteredAssets.length ? (
              <div className="px-6 py-10 text-sm text-muted-foreground">
                当前没有匹配的 HTTP 资产。
              </div>
            ) : (
              <ScrollArea className="h-full">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>名称</TableHead>
                      <TableHead>请求</TableHead>
                      <TableHead>归属</TableHead>
                      <TableHead>状态</TableHead>
                      <TableHead>更新时间</TableHead>
                      <TableHead className="text-right">动作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredAssets.map((asset) => (
                      <TableRow key={asset.asset_id}>
                        <TableCell>
                          <div className="font-medium text-foreground">{asset.name}</div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {asset.description?.trim() || "无描述"}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm text-foreground">
                            {asset.method} {asset.path_template}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">{asset.base_url}</div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {asset.system_short}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={
                              asset.enabled
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : "border-slate-200 bg-slate-100 text-slate-700"
                            }
                          >
                            {asset.enabled ? "启用" : "停用"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDateLabel(asset.updated_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button asChild size="sm" variant="outline">
                            <Link href={`/datamakepool/http-assets/${asset.asset_id}`}>
                              查看详情
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Plus className="h-3.5 w-3.5" />
              最小创建入口
            </div>
            <CardTitle>新建 HTTP 资产</CardTitle>
            <CardDescription>当前先收敛在最小必填字段和两个结构化 JSON 契约上。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            {actionFeedback ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
                {actionFeedback}
              </div>
            ) : null}
            {actionError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                {actionError}
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="资产名称" />
              <Input
                value={systemShort}
                onChange={(event) => setSystemShort(event.target.value)}
                placeholder="system_short"
              />
            </div>

            <Input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="描述（可选）"
            />

            <div className="grid gap-3 sm:grid-cols-[140px_minmax(0,1fr)]">
              <select
                value={method}
                onChange={(event) => setMethod(event.target.value as (typeof HTTP_METHOD_OPTIONS)[number])}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                disabled={isCreating}
              >
                {HTTP_METHOD_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <Input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="Base URL，例如 https://api.example.com"
              />
            </div>

            <Input
              value={pathTemplate}
              onChange={(event) => setPathTemplate(event.target.value)}
              placeholder="Path Template，例如 /reports/{date}"
            />

            <Textarea
              value={requestSchemaText}
              onChange={(event) => setRequestSchemaText(event.target.value)}
              placeholder='Request Schema JSON，可留空，例如 {"date":{"type":"string"}}'
              className="min-h-28 font-mono text-xs"
            />

            <Textarea
              value={extractionRulesText}
              onChange={(event) => setExtractionRulesText(event.target.value)}
              placeholder='Response Extraction Rules JSON，可留空，例如 {"report_id":"$.id"}'
              className="min-h-28 font-mono text-xs"
            />

            <div className="flex items-center justify-between rounded-xl border border-border/70 bg-muted/20 px-3 py-3">
              <div>
                <div className="text-sm font-medium text-foreground">启用状态</div>
                <div className="text-xs text-muted-foreground">关闭后仍可保留详情和关系查看。</div>
              </div>
              <Switch checked={enabled} onCheckedChange={setEnabled} disabled={isCreating} />
            </div>

            <Button onClick={() => void handleCreate()} disabled={isCreating} className="w-full">
              {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              创建 HTTP 资产
            </Button>
          </CardContent>
        </Card>
      </div>
    </DatamakepoolShell>
  )
}
