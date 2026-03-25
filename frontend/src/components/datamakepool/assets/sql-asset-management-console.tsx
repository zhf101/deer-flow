"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Database, Loader2, Plus, RefreshCw } from "lucide-react"

import {
  createDatamakepoolSqlAsset,
  listDatamakepoolSqlAssets,
  type DatamakepoolSqlAssetSummary,
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
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { cn, formatDate } from "@/lib/utils"

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return "未记录"
  }
  return formatDate(value)
}

function getStatusMeta(status?: string | null): { label: string; className: string } {
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

function parseConnectionConfig(text: string): Record<string, unknown> {
  const normalized = text.trim()
  if (!normalized) {
    throw new Error("连接配置为必填，至少需要提供 url。")
  }

  try {
    const parsed = JSON.parse(normalized)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("连接配置必须是 JSON 对象。")
    }
    return parsed as Record<string, unknown>
  } catch (error) {
    if (error instanceof Error && error.message.includes("必须是 JSON 对象")) {
      throw error
    }
    throw new Error("连接配置需要填写合法 JSON。")
  }
}

function parseLineList(text: string): string[] {
  return text
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
}

export function SqlAssetManagementConsole() {
  const [assets, setAssets] = useState<DatamakepoolSqlAssetSummary[]>([])
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
  const [connectionConfigText, setConnectionConfigText] = useState('{ "url": "" }')
  const [whitelistText, setWhitelistText] = useState("")
  const [blacklistText, setBlacklistText] = useState("")
  const [mutationEnabled, setMutationEnabled] = useState(false)

  const loadAssets = useCallback(async (showRefreshingState: boolean = false) => {
    if (showRefreshingState) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
    }
    setError(null)

    try {
      const nextAssets = await listDatamakepoolSqlAssets()
      setAssets(nextAssets)
    } catch (nextError) {
      setAssets([])
      setError(nextError instanceof Error ? nextError.message : "SQL 资产列表加载失败")
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
        asset.system_short.toLowerCase().includes(normalizedKeyword)
      )
    })
  }, [assets, keyword])

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !systemShort.trim()) {
      setActionError("名称与 system_short 为必填项。")
      setActionFeedback(null)
      return
    }

    setIsCreating(true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const created = await createDatamakepoolSqlAsset({
        name: name.trim(),
        description: description.trim() || undefined,
        system_short: systemShort.trim(),
        connection_config: parseConnectionConfig(connectionConfigText),
        whitelist: parseLineList(whitelistText),
        blacklist: parseLineList(blacklistText),
        mutation_enabled: mutationEnabled,
      })
      setActionFeedback(
        `SQL 资产 #${created.asset_id} 创建成功，初始版本 V${created.version_no} 状态为 ${created.status}。`
      )
      setName("")
      setDescription("")
      setSystemShort("")
      setConnectionConfigText('{ "url": "" }')
      setWhitelistText("")
      setBlacklistText("")
      setMutationEnabled(false)
      await loadAssets(true)
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "SQL 资产创建失败")
    } finally {
      setIsCreating(false)
    }
  }, [
    blacklistText,
    connectionConfigText,
    description,
    loadAssets,
    mutationEnabled,
    name,
    systemShort,
    whitelistText,
  ])

  const activeCount = assets.filter((asset) => Boolean(asset.current_active_version_id)).length

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F23 SQL 资产中心"
      title="SQL 资产工作台"
      description="这一页先承接 SQL 资产中心的前台 MVP：逻辑资产列表、最小创建入口，以及跳到版本与反向引用详情。"
      metrics={[
        {
          label: "资产总数",
          value: String(assets.length),
          hint: "当前权限范围内可见 SQL 逻辑资产",
        },
        {
          label: "已有生效版本",
          value: String(activeCount),
          hint: `未生效 ${assets.length - activeCount}`,
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
              <ArrowLeft className="h-4 w-4" />
              模板台
            </Link>
          </Button>
          <Button asChild variant="outline" className="border-border/80 bg-background/70 backdrop-blur-sm">
            <Link href="/datamakepool/http-assets">
              <ArrowLeft className="h-4 w-4" />
              HTTP 资产
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
              <Database className="h-4 w-4 text-primary" />
              <div>
                <CardTitle>逻辑资产列表</CardTitle>
                <CardDescription>列表先聚焦逻辑资产层，不把版本配置直接摊在主表格里。</CardDescription>
              </div>
            </div>
            <Input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="按名称、system_short 搜索 SQL 资产"
            />
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            {isLoading ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载 SQL 资产
              </div>
            ) : error ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {error}
                </div>
              </div>
            ) : !filteredAssets.length ? (
              <div className="px-6 py-10 text-sm text-muted-foreground">
                当前没有匹配的 SQL 资产。
              </div>
            ) : (
              <ScrollArea className="h-full">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>名称</TableHead>
                      <TableHead>归属</TableHead>
                      <TableHead>版本概况</TableHead>
                      <TableHead>最新状态</TableHead>
                      <TableHead>更新时间</TableHead>
                      <TableHead className="text-right">动作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredAssets.map((asset) => {
                      const statusMeta = getStatusMeta(asset.latest_version_status)

                      return (
                        <TableRow key={asset.asset_id}>
                          <TableCell>
                            <div className="font-medium text-foreground">{asset.name}</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {asset.description?.trim() || "无描述"}
                            </div>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {asset.system_short}
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            <div>版本数：{asset.versions_count}</div>
                            <div>生效版本：{asset.current_active_version_id ? `#${asset.current_active_version_id}` : "无"}</div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className={cn("font-medium", statusMeta.className)}>
                              {statusMeta.label}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {formatDateLabel(asset.updated_at)}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button asChild size="sm" variant="outline">
                              <Link href={`/datamakepool/sql-assets/${asset.asset_id}`}>
                                查看详情
                              </Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
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
            <CardTitle>新建 SQL 资产</CardTitle>
            <CardDescription>当前先收敛在逻辑资产 + 初始版本的最小必填字段，不在这里展开版本编辑器。</CardDescription>
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

            <Textarea
              value={connectionConfigText}
              onChange={(event) => setConnectionConfigText(event.target.value)}
              placeholder='连接配置 JSON，例如 { "url": "postgresql://..." }'
              className="min-h-28 font-mono text-xs"
            />

            <Textarea
              value={whitelistText}
              onChange={(event) => setWhitelistText(event.target.value)}
              placeholder="白名单，每行一个表名或对象名"
              className="min-h-24"
            />

            <Textarea
              value={blacklistText}
              onChange={(event) => setBlacklistText(event.target.value)}
              placeholder="黑名单，每行一个表名或对象名"
              className="min-h-24"
            />

            <div className="flex items-center justify-between rounded-xl border border-border/70 bg-muted/20 px-3 py-3">
              <div>
                <div className="text-sm font-medium text-foreground">允许 Mutation</div>
                <div className="text-xs text-muted-foreground">这里只决定初始版本的 mutation 开关，后续仍走版本审核。</div>
              </div>
              <Switch checked={mutationEnabled} onCheckedChange={setMutationEnabled} disabled={isCreating} />
            </div>

            <Button onClick={() => void handleCreate()} disabled={isCreating} className="w-full">
              {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              创建 SQL 资产
            </Button>
          </CardContent>
        </Card>
      </div>
    </DatamakepoolShell>
  )
}
