"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft, ArrowUpRight, Loader2, Play, Workflow } from "lucide-react"

import {
  createDatamakepoolRunFromTemplate,
  getDatamakepoolTemplateRevisionDetail,
  type DatamakepoolTemplateRevisionDetail,
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
import { Textarea } from "@/components/ui/textarea"
import { cn, formatDate } from "@/lib/utils"

type JsonObject = Record<string, unknown>

type NormalizedSchema = {
  type: string
  title?: string
  description?: string
  properties: Record<string, JsonObject>
  required: string[]
}

function getRevisionStatusMeta(status: string): { label: string; className: string } {
  switch (status) {
    case "published":
      return {
        label: "已发布",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      }
    case "pending_review":
      return {
        label: "待审核",
        className: "border-amber-200 bg-amber-50 text-amber-700",
      }
    default:
      return {
        label: status || "未知",
        className: "border-border bg-muted text-muted-foreground",
      }
  }
}

function stringifyPreview(payload: Record<string, unknown> | null | undefined): string | null {
  if (!payload || !Object.keys(payload).length) {
    return null
  }
  return JSON.stringify(payload, null, 2)
}

function normalizeInputSchema(rawSchema: Record<string, unknown> | null | undefined): NormalizedSchema {
  if (!rawSchema || !Object.keys(rawSchema).length) {
    return {
      type: "object",
      title: "执行输入",
      description: "当前模板没有声明输入结构，可直接按空输入创建 Run。",
      properties: {},
      required: [],
    }
  }

  const properties: Record<string, JsonObject> =
    rawSchema.type === "object" && rawSchema.properties && typeof rawSchema.properties === "object"
      ? (rawSchema.properties as Record<string, JsonObject>)
      : Object.fromEntries(
          Object.entries(rawSchema)
            .filter(([, value]) => value && typeof value === "object")
            .map(([key, value]) => [key, value as JsonObject])
        )

  const required =
    rawSchema.type === "object" && Array.isArray(rawSchema.required)
      ? rawSchema.required.filter((item): item is string => typeof item === "string")
      : []

  return {
    type: "object",
    title: typeof rawSchema.title === "string" ? rawSchema.title : "执行输入",
    description: typeof rawSchema.description === "string" ? rawSchema.description : undefined,
    properties,
    required,
  }
}

function buildInitialValue(schema: JsonObject): unknown {
  if (schema.default !== undefined) {
    return schema.default
  }

  switch (schema.type) {
    case "boolean":
      return false
    case "integer":
    case "number":
      return ""
    case "array":
      return []
    case "object":
      return {}
    default:
      return ""
  }
}

function buildInitialFormValues(schema: NormalizedSchema): JsonObject {
  return Object.fromEntries(
    Object.entries(schema.properties).map(([fieldName, fieldSchema]) => [
      fieldName,
      buildInitialValue(fieldSchema),
    ])
  )
}

function formatDateLabel(value?: string | null): string {
  if (!value) {
    return "未记录"
  }
  return formatDate(value)
}

function toDisplayText(value: unknown): string {
  if (typeof value === "string") {
    return value
  }
  if (Array.isArray(value)) {
    return value.join("\n")
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2)
  }
  if (value === null || value === undefined) {
    return ""
  }
  return String(value)
}

function buildSubmitPayload(values: JsonObject, schema: NormalizedSchema): JsonObject {
  const payload: JsonObject = {}

  for (const [fieldName, fieldSchema] of Object.entries(schema.properties)) {
    const rawValue = values[fieldName]

    if (fieldSchema.type === "boolean") {
      payload[fieldName] = Boolean(rawValue)
      continue
    }

    if (fieldSchema.type === "integer" || fieldSchema.type === "number") {
      const textValue = String(rawValue ?? "").trim()
      if (!textValue) {
        continue
      }
      const parsed = Number(textValue)
      if (!Number.isNaN(parsed)) {
        payload[fieldName] = fieldSchema.type === "integer" ? Math.trunc(parsed) : parsed
      }
      continue
    }

    if (fieldSchema.type === "array") {
      const textValue = String(rawValue ?? "").trim()
      if (!textValue) {
        continue
      }
      payload[fieldName] = textValue
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean)
      continue
    }

    if (fieldSchema.type === "object") {
      const textValue = String(rawValue ?? "").trim()
      if (!textValue) {
        continue
      }
      try {
        payload[fieldName] = JSON.parse(textValue) as JsonObject
      } catch {
        payload[fieldName] = textValue
      }
      continue
    }

    const textValue = String(rawValue ?? "").trim()
    if (textValue) {
      payload[fieldName] = textValue
    }
  }

  return payload
}

function validateFormValues(values: JsonObject, schema: NormalizedSchema): string | null {
  for (const fieldName of schema.required) {
    const fieldSchema = schema.properties[fieldName]
    if (!fieldSchema) {
      continue
    }

    const value = values[fieldName]
    if (fieldSchema.type === "boolean") {
      continue
    }

    if (String(value ?? "").trim()) {
      continue
    }

    return `字段“${fieldSchema.title || fieldName}”是必填项。`
  }

  for (const [fieldName, fieldSchema] of Object.entries(schema.properties)) {
    const value = values[fieldName]
    const textValue = String(value ?? "").trim()

    if ((fieldSchema.type === "integer" || fieldSchema.type === "number") && textValue) {
      if (Number.isNaN(Number(textValue))) {
        return `字段“${fieldSchema.title || fieldName}”必须填写数字。`
      }
    }

    if (fieldSchema.type === "object" && textValue) {
      try {
        JSON.parse(textValue)
      } catch {
        return `字段“${fieldSchema.title || fieldName}”需要填写合法 JSON。`
      }
    }
  }

  return null
}

function SchemaField({
  fieldName,
  fieldSchema,
  value,
  required,
  disabled,
  onChange,
}: {
  fieldName: string
  fieldSchema: JsonObject
  value: unknown
  required: boolean
  disabled: boolean
  onChange: (fieldName: string, value: unknown) => void
}) {
  const title = typeof fieldSchema.title === "string" ? fieldSchema.title : fieldName
  const description =
    typeof fieldSchema.description === "string" ? fieldSchema.description : "未提供字段说明"
  const type = typeof fieldSchema.type === "string" ? fieldSchema.type : "string"

  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="font-medium text-foreground">{title}</div>
            {required ? (
              <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                必填
              </Badge>
            ) : (
              <Badge variant="outline" className="border-border bg-muted text-muted-foreground">
                选填
              </Badge>
            )}
          </div>
          <div className="mt-2 text-sm leading-6 text-muted-foreground">{description}</div>
        </div>
        <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
          {type}
        </Badge>
      </div>

      <div className="mt-4">
        {type === "boolean" ? (
          <div className="flex items-center justify-between rounded-xl border border-border/70 bg-muted/20 px-3 py-3">
            <div className="text-sm text-muted-foreground">布尔开关</div>
            <Switch
              checked={Boolean(value)}
              onCheckedChange={(checked) => onChange(fieldName, checked)}
              disabled={disabled}
            />
          </div>
        ) : type === "array" ? (
          <Textarea
            value={toDisplayText(value)}
            onChange={(event) => onChange(fieldName, event.target.value)}
            placeholder="每行一个值"
            disabled={disabled}
          />
        ) : type === "object" ? (
          <Textarea
            value={toDisplayText(value)}
            onChange={(event) => onChange(fieldName, event.target.value)}
            placeholder='请输入 JSON，例如 {"key":"value"}'
            disabled={disabled}
            className="min-h-28 font-mono text-xs"
          />
        ) : (
          <Input
            type={type === "integer" || type === "number" ? "number" : "text"}
            value={toDisplayText(value)}
            onChange={(event) => onChange(fieldName, event.target.value)}
            placeholder={`请输入${title}`}
            disabled={disabled}
          />
        )}
      </div>
    </div>
  )
}

export function TemplateExecutionConsole({
  revisionId,
  templateId = null,
}: {
  revisionId: number
  templateId?: number | null
}) {
  const router = useRouter()
  const [revisionDetail, setRevisionDetail] = useState<DatamakepoolTemplateRevisionDetail | null>(null)
  const [formValues, setFormValues] = useState<JsonObject>({})
  const [pageError, setPageError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const normalizedSchema = useMemo(
    () => normalizeInputSchema(revisionDetail?.input_schema ?? null),
    [revisionDetail]
  )

  const loadRevision = useCallback(async () => {
    setIsLoading(true)
    setPageError(null)

    try {
      const detail = await getDatamakepoolTemplateRevisionDetail(revisionId)
      setRevisionDetail(detail)
      setFormValues(buildInitialFormValues(normalizeInputSchema(detail.input_schema ?? null)))
    } catch (error) {
      setRevisionDetail(null)
      setFormValues({})
      setPageError(error instanceof Error ? error.message : "模板执行入口加载失败")
    } finally {
      setIsLoading(false)
    }
  }, [revisionId])

  useEffect(() => {
    void loadRevision()
  }, [loadRevision])

  const handleFieldChange = useCallback((fieldName: string, value: unknown) => {
    setFormValues((current) => ({
      ...current,
      [fieldName]: value,
    }))
  }, [])

  const handleCreateRun = useCallback(async () => {
    const validationError = validateFormValues(formValues, normalizedSchema)
    if (validationError) {
      setSubmitError(validationError)
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)
    try {
      const payload = buildSubmitPayload(formValues, normalizedSchema)
      const created = await createDatamakepoolRunFromTemplate(revisionId, payload)
      const query = new URLSearchParams({
        revisionId: String(revisionId),
        created: "1",
      })
      if (templateId) {
        query.set("templateId", String(templateId))
      } else if (revisionDetail?.template_id) {
        query.set("templateId", String(revisionDetail.template_id))
      }
      router.push(`/datamakepool/runs/${created.run_id}?${query.toString()}`)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "创建 Run 失败")
    } finally {
      setIsSubmitting(false)
    }
  }, [formValues, normalizedSchema, revisionDetail, revisionId, router, templateId])

  const inputSchemaPreview = stringifyPreview(revisionDetail?.input_schema ?? null)
  const statusMeta = getRevisionStatusMeta(revisionDetail?.status || "")
  const returnHref =
    templateId !== null
      ? `/datamakepool/templates?templateId=${templateId}&revisionId=${revisionId}`
      : `/datamakepool/templates?revisionId=${revisionId}`

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F25 模板执行入口"
      title={`执行模板修订 #${revisionId}`}
      description="这一页只承接设计文档里定义的模板执行入口：读取已发布模板版本的 input_schema，渲染最小输入表单，并创建正式 Run。"
      metrics={[
        {
          label: "模板版本",
          value: revisionDetail ? `V${revisionDetail.version_no}` : "--",
          hint: revisionDetail?.template_name || "等待加载",
        },
        {
          label: "发布状态",
          value: revisionDetail ? statusMeta.label : "--",
          hint: revisionDetail?.system_short || "等待加载",
        },
        {
          label: "输入字段",
          value: String(Object.keys(normalizedSchema.properties).length),
          hint: "来自模板版本 input_schema",
        },
      ]}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" className="border-border/80 bg-background/70 backdrop-blur-sm">
            <Link href={returnHref}>
              <ArrowLeft className="h-4 w-4" />
              返回模板
            </Link>
          </Button>
          <Button
            onClick={() => void handleCreateRun()}
            disabled={isLoading || isSubmitting || revisionDetail?.status !== "published"}
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            创建 Run
          </Button>
        </div>
      }
    >
      <div className="grid h-full min-h-0 gap-6 p-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Workflow className="h-3.5 w-3.5" />
              执行表单
            </div>
            <CardTitle>输入参数</CardTitle>
            <CardDescription>按模板版本的 input_schema 渲染最小可执行表单，不在这里扩展复杂表单引擎。</CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 px-0">
            {isLoading ? (
              <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载模板执行入口
              </div>
            ) : pageError ? (
              <div className="px-6 py-6">
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {pageError}
                </div>
              </div>
            ) : (
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  {submitError ? (
                    <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-3 text-sm text-destructive">
                      {submitError}
                    </div>
                  ) : null}

                  {!Object.keys(normalizedSchema.properties).length ? (
                    <div className="rounded-2xl border border-dashed border-border/80 px-4 py-5 text-sm text-muted-foreground">
                      当前模板没有声明结构化输入字段。你仍然可以直接创建 Run。
                    </div>
                  ) : (
                    Object.entries(normalizedSchema.properties).map(([fieldName, fieldSchema]) => (
                      <SchemaField
                        key={fieldName}
                        fieldName={fieldName}
                        fieldSchema={fieldSchema}
                        value={formValues[fieldName]}
                        required={normalizedSchema.required.includes(fieldName)}
                        disabled={isSubmitting}
                        onChange={handleFieldChange}
                      />
                    ))
                  )}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        <div className="grid min-h-0 gap-6">
          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <ArrowUpRight className="h-3.5 w-3.5" />
                执行上下文
              </div>
              <CardTitle>版本信息</CardTitle>
              <CardDescription>执行入口只允许基于已发布模板版本创建正式 Run。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              <div>模板：{revisionDetail?.template_name || "--"}</div>
              <div>模板版本：{revisionDetail ? `V${revisionDetail.version_no}` : "--"}</div>
              <div>系统域：{revisionDetail?.system_short || "--"}</div>
              <div>来源 Run：{revisionDetail?.source_run_id ? `#${revisionDetail.source_run_id}` : "无"}</div>
              <div>发布时间：{formatDateLabel(revisionDetail?.published_at)}</div>
              <div className={cn("rounded-xl border px-3 py-2 text-sm", statusMeta.className)}>
                当前状态：{statusMeta.label}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Workflow className="h-3.5 w-3.5" />
                表单说明
              </div>
              <CardTitle>执行规则</CardTitle>
              <CardDescription>这里严格贴设计文档的最小边界，不扩复杂执行参数系统。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 pt-4 text-sm text-muted-foreground">
              <div>1. 只允许从已发布模板版本创建 Run。</div>
              <div>2. 输入字段来自模板版本沉淀的 input_schema。</div>
              <div>3. 成功后统一跳到 Run 工作台查看执行状态。</div>
              <div>4. 当前仍不在这里扩动态校验器、条件字段或高级默认值策略。</div>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Workflow className="h-3.5 w-3.5" />
                输入真相源
              </div>
              <CardTitle>Input Schema</CardTitle>
              <CardDescription>用于核对当前表单是否仍然忠实于模板版本的真实契约。</CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              {inputSchemaPreview ? (
                <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                  {inputSchemaPreview}
                </pre>
              ) : (
                <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                  当前模板版本没有记录结构化 input_schema。
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </DatamakepoolShell>
  )
}
