"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  ArrowRight,
  Bot,
  Database,
  GitBranch,
  Layers,
  Loader2,
  Play,
  RefreshCw,
  Send,
  Sparkles,
  Workflow,
} from "lucide-react"

import {
  createDatamakepoolConversation,
  getDatamakepoolConversationFlowdraft,
  getDatamakepoolFlowdraft,
  getDatamakepoolFlowdraftDiff,
  getDatamakepoolFlowdraftPreflight,
  listDatamakepoolFlowdraftSnapshots,
  patchDatamakepoolFlowdraftStep,
  postDatamakepoolConversationMessage,
  resolveDatamakepoolFlowdraft,
  resolveDatamakepoolFlowdraftStep,
  trialDatamakepoolFlowdraft,
  type DatamakepoolConversationSummary,
  type DatamakepoolEditableFieldSpec,
  type DatamakepoolFlowdraft,
  type DatamakepoolFlowdraftDiff,
  type DatamakepoolFlowdraftDiffChunk,
  type DatamakepoolFlowdraftIssue,
  type DatamakepoolFlowdraftPreflightSummary,
  type DatamakepoolFlowdraftSnapshot,
  type DatamakepoolFlowdraftStepNode,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { cn, formatDate } from "@/lib/utils"

interface ChatTimelineMessage {
  id: string
  role: "user" | "assistant" | "system"
  content: string
  createdAt?: string
}

type StepEditorValue = string | boolean

const STEP_JSON_FIELDS = new Set([
  "query_template",
  "headers_template",
  "body_template",
  "output_mapping",
  "mapping",
  "param_template",
])
const STEP_BOOLEAN_FIELDS = new Set(["confirmation_required", "auto_confirm"])
const STEP_MULTILINE_FIELDS = new Set(["sql"])

function getFlowdraftStatusMeta(status: string): { label: string; className: string } {
  switch (status) {
    case "draft":
      return {
        label: "草稿",
        className: "border-slate-200 bg-slate-100 text-slate-700",
      }
    case "needs_resolution":
      return {
        label: "待收敛",
        className: "border-amber-200 bg-amber-50 text-amber-700",
      }
    case "ready_for_trial":
      return {
        label: "可试跑",
        className: "border-sky-200 bg-sky-50 text-sky-700",
      }
    case "trial_running":
      return {
        label: "试跑中",
        className: "border-indigo-200 bg-indigo-50 text-indigo-700",
      }
    case "trial_succeeded":
      return {
        label: "试跑成功",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      }
    case "trial_failed":
      return {
        label: "试跑失败",
        className: "border-destructive/30 bg-destructive/5 text-destructive",
      }
    default:
      return {
        label: status || "未知",
        className: "border-border bg-muted text-muted-foreground",
      }
  }
}

function getIssueTypeLabel(issueType: string): string {
  const labels: Record<string, string> = {
    route_pending: "技术路线待确认",
    asset_pending: "执行资产待绑定",
    param_pending: "关键参数待补全",
    mapping_incomplete: "输出映射未完整",
    resolution_missing: "执行方案未收敛",
    dependency_incomplete: "依赖关系不完整",
    governance_blocked: "治理规则阻塞",
    needs_resolution: "步骤变更待重新收敛",
    confirmation_required: "危险 SQL 待人工确认",
  }
  return labels[issueType] ?? issueType
}

function getSuggestedActionLabel(action: string): string {
  const labels: Record<string, string> = {
    return_to_chat: "回聊天补充",
    edit_step_design: "补充设计/映射",
    resolve_step: "执行收敛",
    review_governance: "查看治理阻塞",
  }
  return labels[action] ?? action
}

function getStepTypeLabel(stepType: string): string {
  const labels: Record<string, string> = {
    start: "开始",
    mapping: "映射",
    http_step: "HTTP",
    sql_step: "SQL",
    confirm: "确认",
    end: "结束",
  }
  return labels[stepType] ?? stepType
}

function getSnapshotTypeLabel(snapshotType: string): string {
  const labels: Record<string, string> = {
    manual_edit: "人工修改",
    re_resolved: "重新收敛",
    pre_trial: "试跑前",
    trial_success: "试跑成功",
    trial_failed: "试跑失败",
  }
  return labels[snapshotType] ?? snapshotType
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

function stringifyPreview(payload: unknown): string | null {
  if (payload == null) {
    return null
  }
  if (Array.isArray(payload)) {
    return payload.length ? JSON.stringify(payload, null, 2) : null
  }
  if (typeof payload === "object") {
    return Object.keys(payload).length ? JSON.stringify(payload, null, 2) : null
  }
  return JSON.stringify(payload, null, 2)
}

function getIssueSummary(preflight?: DatamakepoolFlowdraftPreflightSummary | null): string {
  if (!preflight) {
    return "尚未执行预检"
  }
  if (preflight.is_runnable) {
    return "当前草稿已满足最小试跑条件"
  }
  return `存在 ${preflight.issues.length} 个阻塞问题`
}

function getStepStatusLabel(step: DatamakepoolFlowdraftStepNode): string {
  if (step.pending_flags?.length) {
    return `${step.pending_flags.length} 个待处理标记`
  }
  return "当前无待处理标记"
}

function normalizeEditableFields(step: DatamakepoolFlowdraftStepNode): DatamakepoolEditableFieldSpec[] {
  if (Array.isArray(step.editable_fields) && step.editable_fields.length) {
    return step.editable_fields
      .filter((item): item is DatamakepoolEditableFieldSpec => Boolean(item?.name))
      .map((item) => ({
        name: item.name,
        mode: item.mode,
        editor: item.editor ?? null,
        widget: item.widget ?? null,
        required: item.required,
        validation_rules: Array.isArray(item.validation_rules) ? item.validation_rules : [],
      }))
  }

  switch (step.step_type) {
    case "http_step":
      return [
        { name: "query_template", mode: "direct_edit" },
        { name: "headers_template", mode: "direct_edit" },
        { name: "body_template", mode: "direct_edit" },
        { name: "output_mapping", mode: "direct_edit" },
        { name: "asset_ref", mode: "needs_resolution" },
      ]
    case "sql_step":
      return [
        { name: "param_template", mode: "direct_edit" },
        { name: "output_mapping", mode: "direct_edit" },
        { name: "asset_ref", mode: "needs_resolution" },
        { name: "sql", mode: "needs_resolution" },
      ]
    case "mapping":
      return [
        { name: "mapping", mode: "direct_edit" },
        { name: "output_mapping", mode: "direct_edit" },
      ]
    case "confirm":
      return [
        { name: "confirmation_required", mode: "direct_edit" },
        { name: "auto_confirm", mode: "direct_edit" },
      ]
    default:
      return []
  }
}

function getTechnicalSteps(flowdraft: DatamakepoolFlowdraft | null): DatamakepoolFlowdraftStepNode[] {
  const nodes = flowdraft?.technical_graph?.nodes
  if (!Array.isArray(nodes)) {
    return []
  }

  return nodes
    .filter((node): node is Record<string, unknown> => Boolean(node && typeof node === "object"))
    .map((node) => ({
      ...node,
      step_id: String(node.step_id ?? node.id ?? ""),
      step_type: String(node.step_type ?? node.type ?? ""),
      step_name:
        typeof node.step_name === "string"
          ? node.step_name
          : String(node.step_id ?? node.id ?? "未命名步骤"),
      depends_on: Array.isArray(node.depends_on) ? node.depends_on.map(String) : [],
      pending_flags: Array.isArray(node.pending_flags) ? node.pending_flags.map(String) : [],
      editable_fields: Array.isArray(node.editable_fields)
        ? (node.editable_fields as DatamakepoolEditableFieldSpec[])
        : [],
    }))
    .filter((step) => step.step_id)
}

function getPreferredSelectedStepId(
  steps: DatamakepoolFlowdraftStepNode[],
  currentStepId: string | null
): string | null {
  if (currentStepId && steps.some((step) => step.step_id === currentStepId)) {
    return currentStepId
  }

  const preferred = steps.find((step) => !["start", "end"].includes(step.step_type))
  return preferred?.step_id ?? steps[0]?.step_id ?? null
}

function readStepFieldValue(step: DatamakepoolFlowdraftStepNode, fieldName: string): unknown {
  const resolvedPlan =
    step.resolved_execution_plan && typeof step.resolved_execution_plan === "object"
      ? step.resolved_execution_plan
      : {}

  if (Object.prototype.hasOwnProperty.call(resolvedPlan, fieldName)) {
    return resolvedPlan[fieldName]
  }
  return step[fieldName]
}

function serializeStepEditorValue(fieldName: string, value: unknown): StepEditorValue {
  if (STEP_BOOLEAN_FIELDS.has(fieldName)) {
    return Boolean(value)
  }
  if (typeof value === "string") {
    return value
  }
  if (value === null || value === undefined) {
    return ""
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2)
  }
  return String(value)
}

function buildStepEditorValues(step: DatamakepoolFlowdraftStepNode): Record<string, StepEditorValue> {
  return Object.fromEntries(
    normalizeEditableFields(step).map((field) => [
      field.name,
      serializeStepEditorValue(field.name, readStepFieldValue(step, field.name)),
    ])
  )
}

function parseStepEditorValue(fieldName: string, rawValue: StepEditorValue): unknown {
  if (STEP_BOOLEAN_FIELDS.has(fieldName)) {
    return Boolean(rawValue)
  }

  const textValue = String(rawValue ?? "").trim()

  if (STEP_JSON_FIELDS.has(fieldName)) {
    if (!textValue) {
      return {}
    }
    try {
      return JSON.parse(textValue) as Record<string, unknown>
    } catch {
      throw new Error(`字段“${fieldName}”需要填写合法 JSON`)
    }
  }

  if (fieldName === "asset_ref") {
    if (!textValue) {
      throw new Error("字段“asset_ref”不能为空")
    }
    if (textValue.startsWith("{") || textValue.startsWith("[")) {
      try {
        return JSON.parse(textValue) as Record<string, unknown>
      } catch {
        throw new Error("字段“asset_ref”如果填写结构化内容，必须是合法 JSON")
      }
    }
    return textValue
  }

  return textValue
}

function DiffSummaryCard({
  title,
  chunk,
}: {
  title: string
  chunk: DatamakepoolFlowdraftDiffChunk
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/70 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium text-foreground">{title}</div>
        <Badge
          variant="outline"
          className={cn(
            "font-medium",
            chunk.changed
              ? "border-amber-200 bg-amber-50 text-amber-700"
              : "border-emerald-200 bg-emerald-50 text-emerald-700"
          )}
        >
          {chunk.changed ? "有变化" : "无变化"}
        </Badge>
      </div>

      <div className="mt-3 space-y-2 text-sm text-muted-foreground">
        <div>变化数：{chunk.changed_count}</div>
        <div>变化路径：{chunk.changed_paths.length ? chunk.changed_paths.join("、") : "无"}</div>
        <div>
          命中步骤：{chunk.changed_step_ids.length ? chunk.changed_step_ids.join("、") : "无"}
        </div>
      </div>
    </div>
  )
}

function TimelineBubble({ message }: { message: ChatTimelineMessage }) {
  const isUser = message.role === "user"
  const isAssistant = message.role === "assistant"

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-6",
          isUser
            ? "bg-primary text-primary-foreground"
            : isAssistant
              ? "border border-border/70 bg-background text-foreground"
              : "border border-dashed border-border/80 bg-muted/20 text-muted-foreground"
        )}
      >
        <div className="mb-1 text-[11px] uppercase tracking-[0.16em] opacity-80">
          {isUser ? "用户输入" : isAssistant ? "系统摘要" : "系统提示"}
        </div>
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
        {message.createdAt ? (
          <div className="mt-2 text-[11px] opacity-70">{formatDateLabel(message.createdAt)}</div>
        ) : null}
      </div>
    </div>
  )
}

function PendingIssueCard({ issue }: { issue: DatamakepoolFlowdraftIssue }) {
  return (
    <div className="rounded-xl border border-border/70 bg-background/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium text-foreground">{getIssueTypeLabel(issue.issue_type)}</div>
        {issue.step_id ? (
          <Badge variant="outline" className="border-border/70 bg-background text-foreground">
            {issue.step_id}
          </Badge>
        ) : null}
      </div>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">{issue.message}</div>
      {issue.suggested_action ? (
        <div className="mt-2 text-xs text-muted-foreground">
          建议动作：{getSuggestedActionLabel(issue.suggested_action)}
        </div>
      ) : null}
    </div>
  )
}

function StepEditorField({
  field,
  value,
  disabled,
  onChange,
}: {
  field: DatamakepoolEditableFieldSpec
  value: StepEditorValue
  disabled: boolean
  onChange: (fieldName: string, value: StepEditorValue) => void
}) {
  const isBoolean = STEP_BOOLEAN_FIELDS.has(field.name)
  const isTextArea = STEP_JSON_FIELDS.has(field.name) || STEP_MULTILINE_FIELDS.has(field.name)

  return (
    <div className="rounded-xl border border-border/70 bg-background/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium text-foreground">{field.name}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {field.mode === "needs_resolution"
              ? "保存后会把当前步骤重新标记为待收敛"
              : "可直接写回当前步骤执行方案"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge
            variant="outline"
            className={cn(
              "font-medium",
              field.mode === "needs_resolution"
                ? "border-amber-200 bg-amber-50 text-amber-700"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
            )}
          >
            {field.mode === "needs_resolution" ? "需重收敛" : "直接编辑"}
          </Badge>
          {field.required ? (
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary">
              必填
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="mt-3">
        {isBoolean ? (
          <div className="flex items-center justify-between rounded-xl border border-border/70 bg-muted/20 px-3 py-3">
            <div className="text-sm text-muted-foreground">布尔开关</div>
            <Switch
              checked={Boolean(value)}
              onCheckedChange={(checked) => onChange(field.name, checked)}
              disabled={disabled}
            />
          </div>
        ) : isTextArea ? (
          <Textarea
            value={String(value ?? "")}
            onChange={(event) => onChange(field.name, event.target.value)}
            disabled={disabled}
            className={cn(
              "font-mono text-xs",
              STEP_MULTILINE_FIELDS.has(field.name) ? "min-h-28" : "min-h-24"
            )}
          />
        ) : (
          <Input
            value={String(value ?? "")}
            onChange={(event) => onChange(field.name, event.target.value)}
            disabled={disabled}
          />
        )}
      </div>
    </div>
  )
}

/**
 * 探索入口先做独立工作台，不复用全局聊天上下文。
 * 这样能严格贴住 datamakepool 的会话 + FlowDraft 主线，而不是扩成另一套通用聊天系统。
 */
export function DatamakepoolChatConsole({
  initialConversationId = null,
  initialFlowdraftId = null,
}: {
  initialConversationId?: number | null
  initialFlowdraftId?: number | null
}) {
  const router = useRouter()
  const [conversation, setConversation] = useState<DatamakepoolConversationSummary | null>(null)
  const [flowdraft, setFlowdraft] = useState<DatamakepoolFlowdraft | null>(null)
  const [timeline, setTimeline] = useState<ChatTimelineMessage[]>([])

  const [titleInput, setTitleInput] = useState("")
  const [objectiveInput, setObjectiveInput] = useState("")
  const [messageInput, setMessageInput] = useState("")

  const [activeConversationId, setActiveConversationId] = useState<number | null>(
    initialConversationId
  )
  const [activeFlowdraftId, setActiveFlowdraftId] = useState<number | null>(initialFlowdraftId)

  const [snapshots, setSnapshots] = useState<DatamakepoolFlowdraftSnapshot[]>([])
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<number | null>(null)
  const [flowdraftDiff, setFlowdraftDiff] = useState<DatamakepoolFlowdraftDiff | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [stepEditorValues, setStepEditorValues] = useState<Record<string, StepEditorValue>>({})
  const [stepEditorDefaults, setStepEditorDefaults] = useState<Record<string, StepEditorValue>>({})
  const [detailTab, setDetailTab] = useState("step")

  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)
  const [snapshotError, setSnapshotError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(Boolean(initialConversationId || initialFlowdraftId))
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isCreatingConversation, setIsCreatingConversation] = useState(false)
  const [isSendingMessage, setIsSendingMessage] = useState(false)
  const [isRunningPreflight, setIsRunningPreflight] = useState(false)
  const [isResolvingFlowdraft, setIsResolvingFlowdraft] = useState(false)
  const [isStartingTrial, setIsStartingTrial] = useState(false)
  const [isLoadingSnapshots, setIsLoadingSnapshots] = useState(false)
  const [isLoadingDiff, setIsLoadingDiff] = useState(false)
  const [isPatchingStep, setIsPatchingStep] = useState(false)
  const [isResolvingStep, setIsResolvingStep] = useState(false)

  const syncUrl = useCallback(
    (conversationId: number | null, flowdraftId: number | null) => {
      const params = new URLSearchParams()
      if (conversationId) {
        params.set("conversationId", String(conversationId))
      }
      if (flowdraftId) {
        params.set("flowdraftId", String(flowdraftId))
      }
      const nextHref = params.toString()
        ? `/datamakepool/chat?${params.toString()}`
        : "/datamakepool/chat"
      router.replace(nextHref)
    },
    [router]
  )

  const appendTimelineMessage = useCallback(
    (role: ChatTimelineMessage["role"], content: string, createdAt?: string) => {
      setTimeline((current) => [
        ...current,
        {
          id: `${role}-${Date.now()}-${current.length}`,
          role,
          content,
          createdAt,
        },
      ])
    },
    []
  )

  const ensureResumeNotice = useCallback((conversationId: number, flowdraftId: number) => {
    setTimeline((current) => {
      if (current.length) {
        return current
      }
      return [
        {
          id: `resume-${conversationId}-${flowdraftId}`,
          role: "system",
          content: `已接入探索会话 #${conversationId}，当前使用 FlowDraft #${flowdraftId}。历史消息本轮不回放，可继续追加输入。`,
        },
      ]
    })
  }, [])

  const loadFlowdraftDiff = useCallback(async (flowdraftId: number, snapshotId: number | null) => {
    if (!snapshotId) {
      setFlowdraftDiff(null)
      return
    }

    setIsLoadingDiff(true)
    setSnapshotError(null)
    try {
      const diff = await getDatamakepoolFlowdraftDiff(flowdraftId, {
        beforeSnapshotId: snapshotId,
      })
      setFlowdraftDiff(diff)
    } catch (nextError) {
      setFlowdraftDiff(null)
      setSnapshotError(nextError instanceof Error ? nextError.message : "FlowDraft diff 加载失败")
    } finally {
      setIsLoadingDiff(false)
    }
  }, [])

  const loadFlowdraftArtifacts = useCallback(
    async (flowdraftId: number, preferredSnapshotId?: number | null) => {
      setIsLoadingSnapshots(true)
      setSnapshotError(null)

      try {
        const nextSnapshots = await listDatamakepoolFlowdraftSnapshots(flowdraftId)
        setSnapshots(nextSnapshots)

        const fallbackSnapshotId =
          preferredSnapshotId && nextSnapshots.some((item) => item.snapshot_id === preferredSnapshotId)
            ? preferredSnapshotId
            : nextSnapshots[0]?.snapshot_id ?? null

        setSelectedSnapshotId(fallbackSnapshotId)
        await loadFlowdraftDiff(flowdraftId, fallbackSnapshotId)
      } catch (nextError) {
        setSnapshots([])
        setSelectedSnapshotId(null)
        setFlowdraftDiff(null)
        setSnapshotError(nextError instanceof Error ? nextError.message : "FlowDraft 快照加载失败")
      } finally {
        setIsLoadingSnapshots(false)
      }
    },
    [loadFlowdraftDiff]
  )

  const loadFlowdraft = useCallback(
    async (
      options?: {
        conversationId?: number | null
        flowdraftId?: number | null
        showRefreshingState?: boolean
      }
    ) => {
      const conversationId = options?.conversationId ?? activeConversationId
      const flowdraftId = options?.flowdraftId ?? activeFlowdraftId

      if (!conversationId && !flowdraftId) {
        setFlowdraft(null)
        setConversation(null)
        setSnapshots([])
        setFlowdraftDiff(null)
        setSelectedSnapshotId(null)
        setIsLoading(false)
        setIsRefreshing(false)
        return
      }

      if (options?.showRefreshingState) {
        setIsRefreshing(true)
      } else {
        setIsLoading(true)
      }
      setError(null)

      try {
        const nextFlowdraft = conversationId
          ? await getDatamakepoolConversationFlowdraft(conversationId)
          : await getDatamakepoolFlowdraft(flowdraftId as number)

        setFlowdraft(nextFlowdraft)
        setActiveFlowdraftId(nextFlowdraft.id)
        if (conversationId) {
          setConversation((current) => ({
            conversation_id: conversationId,
            task_id: nextFlowdraft.task_id,
            flowdraft_id: nextFlowdraft.id,
            title: nextFlowdraft.title || current?.title || "探索会话",
            objective: nextFlowdraft.objective ?? current?.objective ?? null,
            flowdraft_status: nextFlowdraft.status,
            created_at: current?.created_at ?? null,
            updated_at: current?.updated_at ?? null,
          }))
          ensureResumeNotice(conversationId, nextFlowdraft.id)
          syncUrl(conversationId, nextFlowdraft.id)
        } else {
          syncUrl(null, nextFlowdraft.id)
        }

        await loadFlowdraftArtifacts(nextFlowdraft.id, nextFlowdraft.latest_snapshot_id ?? null)
      } catch (nextError) {
        setFlowdraft(null)
        setSnapshots([])
        setFlowdraftDiff(null)
        setSelectedSnapshotId(null)
        setError(nextError instanceof Error ? nextError.message : "FlowDraft 加载失败")
      } finally {
        setIsLoading(false)
        setIsRefreshing(false)
      }
    },
    [
      activeConversationId,
      activeFlowdraftId,
      ensureResumeNotice,
      loadFlowdraftArtifacts,
      syncUrl,
    ]
  )

  useEffect(() => {
    if (!initialConversationId && !initialFlowdraftId) {
      setIsLoading(false)
      return
    }

    void loadFlowdraft({
      conversationId: initialConversationId,
      flowdraftId: initialFlowdraftId,
    })
  }, [initialConversationId, initialFlowdraftId, loadFlowdraft])

  const technicalSteps = useMemo(() => getTechnicalSteps(flowdraft), [flowdraft])
  const selectedStep = useMemo(
    () => technicalSteps.find((step) => step.step_id === selectedStepId) ?? null,
    [selectedStepId, technicalSteps]
  )
  const selectedStepEditableFields = useMemo(
    () => (selectedStep ? normalizeEditableFields(selectedStep) : []),
    [selectedStep]
  )

  useEffect(() => {
    setSelectedStepId((current) => getPreferredSelectedStepId(technicalSteps, current))
  }, [technicalSteps])

  useEffect(() => {
    if (!selectedStep) {
      setStepEditorValues({})
      setStepEditorDefaults({})
      return
    }

    const nextValues = buildStepEditorValues(selectedStep)
    setStepEditorValues(nextValues)
    setStepEditorDefaults(nextValues)
  }, [selectedStep])

  const handleCreateConversation = useCallback(async () => {
    setIsCreatingConversation(true)
    setActionError(null)
    setActionFeedback(null)

    try {
      const created = await createDatamakepoolConversation({
        title: titleInput.trim() || undefined,
        objective: objectiveInput.trim() || undefined,
      })
      setConversation(created)
      setActiveConversationId(created.conversation_id)
      setActiveFlowdraftId(created.flowdraft_id)
      setTimeline([
        {
          id: `created-${created.conversation_id}`,
          role: "system",
          content: `已创建探索会话 #${created.conversation_id}，现在可以继续输入需求，让系统刷新初版 FlowDraft。`,
          createdAt: created.created_at ?? undefined,
        },
      ])
      setActionFeedback(`探索会话 #${created.conversation_id} 已创建。`)
      await loadFlowdraft({
        conversationId: created.conversation_id,
        flowdraftId: created.flowdraft_id,
      })
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "探索会话创建失败")
    } finally {
      setIsCreatingConversation(false)
    }
  }, [loadFlowdraft, objectiveInput, titleInput])

  const handleSendMessage = useCallback(async () => {
    if (!activeConversationId) {
      setActionError("请先创建探索会话，再继续发送消息。")
      return
    }

    const normalizedMessage = messageInput.trim()
    if (!normalizedMessage) {
      setActionError("消息内容不能为空。")
      return
    }

    setIsSendingMessage(true)
    setActionError(null)
    setActionFeedback(null)

    try {
      const result = await postDatamakepoolConversationMessage(activeConversationId, {
        content: normalizedMessage,
      })
      appendTimelineMessage("user", normalizedMessage, new Date().toISOString())
      setMessageInput("")
      setConversation((current) => ({
        conversation_id: result.conversation_id,
        task_id: current?.task_id ?? result.conversation_id,
        flowdraft_id: result.flowdraft_id,
        title: result.title || current?.title || "探索会话",
        objective: result.objective ?? current?.objective ?? null,
        flowdraft_status: result.flowdraft_status,
        created_at: current?.created_at ?? null,
        updated_at: new Date().toISOString(),
      }))
      setActiveFlowdraftId(result.flowdraft_id)
      appendTimelineMessage(
        "assistant",
        result.assistant_summary?.trim() || "已刷新初版 FlowDraft。",
        new Date().toISOString()
      )
      await loadFlowdraft({
        conversationId: activeConversationId,
        flowdraftId: result.flowdraft_id,
      })
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "探索消息发送失败")
    } finally {
      setIsSendingMessage(false)
    }
  }, [activeConversationId, appendTimelineMessage, loadFlowdraft, messageInput])

  const handleRunPreflight = useCallback(async () => {
    if (!activeFlowdraftId) {
      setActionError("当前没有可预检的 FlowDraft。")
      return
    }

    setIsRunningPreflight(true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const preflight = await getDatamakepoolFlowdraftPreflight(activeFlowdraftId)
      setFlowdraft((current) =>
        current
          ? {
              ...current,
              preflight_summary: preflight,
              pending_issues: preflight.issues,
            }
          : current
      )
      setActionFeedback(
        preflight.is_runnable ? "预检通过，可进入试跑。" : "预检已刷新，当前仍有阻塞项。"
      )
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "FlowDraft 预检失败")
    } finally {
      setIsRunningPreflight(false)
    }
  }, [activeFlowdraftId])

  const handleResolveFlowdraft = useCallback(async () => {
    if (!activeFlowdraftId) {
      setActionError("当前没有可收敛的 FlowDraft。")
      return
    }

    setIsResolvingFlowdraft(true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const result = await resolveDatamakepoolFlowdraft(activeFlowdraftId)
      setActionFeedback(
        `已完成整份收敛，处理步骤 ${result.resolved_steps.length} 个，阻塞步骤 ${result.blocked_steps.length} 个。`
      )
      await loadFlowdraft({
        conversationId: activeConversationId,
        flowdraftId: activeFlowdraftId,
      })
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "FlowDraft 收敛失败")
    } finally {
      setIsResolvingFlowdraft(false)
    }
  }, [activeConversationId, activeFlowdraftId, loadFlowdraft])

  const handlePatchSelectedStep = useCallback(async () => {
    if (!activeFlowdraftId || !selectedStep) {
      setActionError("当前没有可编辑的 FlowDraft 步骤。")
      return
    }

    const changedEntries = Object.entries(stepEditorValues).filter(([fieldName, value]) => {
      const originalValue = stepEditorDefaults[fieldName]
      return JSON.stringify(value) !== JSON.stringify(originalValue)
    })

    if (!changedEntries.length) {
      setActionError("当前步骤没有待保存改动。")
      return
    }

    setIsPatchingStep(true)
    setActionError(null)
    setActionFeedback(null)

    try {
      const changes = Object.fromEntries(
        changedEntries.map(([fieldName, value]) => [fieldName, parseStepEditorValue(fieldName, value)])
      )
      const result = await patchDatamakepoolFlowdraftStep(
        activeFlowdraftId,
        selectedStep.step_id,
        changes
      )
      setActionFeedback(
        `步骤 ${selectedStep.step_id} 已保存，直接写回 ${result.direct_updates.length} 项，需重收敛 ${result.needs_resolution_fields.length} 项。`
      )
      await loadFlowdraft({
        conversationId: activeConversationId,
        flowdraftId: activeFlowdraftId,
      })
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "步骤编辑保存失败")
    } finally {
      setIsPatchingStep(false)
    }
  }, [
    activeConversationId,
    activeFlowdraftId,
    loadFlowdraft,
    selectedStep,
    stepEditorDefaults,
    stepEditorValues,
  ])

  const handleResolveSelectedStep = useCallback(async () => {
    if (!activeFlowdraftId || !selectedStep) {
      setActionError("当前没有可局部收敛的步骤。")
      return
    }

    setIsResolvingStep(true)
    setActionError(null)
    setActionFeedback(null)

    try {
      const result = await resolveDatamakepoolFlowdraftStep(activeFlowdraftId, selectedStep.step_id)
      setActionFeedback(
        `步骤 ${selectedStep.step_id} 已重新收敛，当前状态 ${result.resolution_status === "resolved" ? "正常" : "仍有阻塞"}。`
      )
      await loadFlowdraft({
        conversationId: activeConversationId,
        flowdraftId: activeFlowdraftId,
      })
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "步骤局部收敛失败")
    } finally {
      setIsResolvingStep(false)
    }
  }, [activeConversationId, activeFlowdraftId, loadFlowdraft, selectedStep])

  const handleStartTrial = useCallback(async () => {
    if (!activeFlowdraftId) {
      setActionError("当前没有可试跑的 FlowDraft。")
      return
    }

    setIsStartingTrial(true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const created = await trialDatamakepoolFlowdraft(activeFlowdraftId, {
        entry_type: "chat",
      })
      const query = new URLSearchParams({
        created: "1",
        returnTo: "chat",
      })
      if (activeConversationId) {
        query.set("conversationId", String(activeConversationId))
      }
      query.set("flowdraftId", String(activeFlowdraftId))
      router.push(`/datamakepool/runs/${created.run_id}?${query.toString()}`)
    } catch (nextError) {
      setActionError(nextError instanceof Error ? nextError.message : "FlowDraft 试跑失败")
    } finally {
      setIsStartingTrial(false)
    }
  }, [activeConversationId, activeFlowdraftId, router])

  const handleSelectSnapshot = useCallback(
    async (snapshotId: number) => {
      if (!activeFlowdraftId) {
        return
      }
      setSelectedSnapshotId(snapshotId)
      await loadFlowdraftDiff(activeFlowdraftId, snapshotId)
    },
    [activeFlowdraftId, loadFlowdraftDiff]
  )

  const pendingIssues = useMemo(() => {
    if (!flowdraft) {
      return []
    }
    return flowdraft.pending_issues.length
      ? flowdraft.pending_issues
      : flowdraft.preflight_summary?.issues ?? []
  }, [flowdraft])

  const preflight = flowdraft?.preflight_summary ?? null
  const flowdraftStatusMeta = getFlowdraftStatusMeta(
    flowdraft?.status || conversation?.flowdraft_status || ""
  )
  const businessGraphPreview = stringifyPreview(flowdraft?.business_graph ?? null)
  const technicalGraphPreview = stringifyPreview(flowdraft?.technical_graph ?? null)
  const inputSchemaPreview = stringifyPreview(flowdraft?.input_schema_draft ?? null)
  const outputMappingPreview = stringifyPreview(flowdraft?.output_mapping_draft ?? null)
  const selectedStepDesignIntentPreview = stringifyPreview(selectedStep?.design_intent ?? null)
  const selectedStepRationalePreview = stringifyPreview(
    selectedStep?.resolution_rationale ?? null
  )
  const selectedStepPlanPreview = stringifyPreview(selectedStep?.resolved_execution_plan ?? null)
  const selectedStepAssetSnapshotPreview = stringifyPreview(
    selectedStep?.asset_version_snapshot_ref ?? null
  )
  const canStartTrial =
    Boolean(preflight?.is_runnable) || flowdraft?.status === "ready_for_trial"

  return (
    <DatamakepoolShell
      eyebrow="datamakepool / F1 F2 F4 F5 探索入口"
      title="聊天探索工作台"
      description="这一页承接统一造数平台的聊天探索入口：创建会话、追加需求、刷新当前 FlowDraft，并把步骤编辑、快照差异、预检、收敛与试跑接到同一条探索主链上。"
      metrics={[
        {
          label: "探索会话",
          value: activeConversationId ? `#${activeConversationId}` : "未创建",
          hint: activeConversationId ? "探索态会话宿主复用 Task" : "先创建会话",
        },
        {
          label: "草稿状态",
          value: flowdraft ? flowdraftStatusMeta.label : "--",
          hint: flowdraft?.id ? `FlowDraft #${flowdraft.id}` : "等待生成",
        },
        {
          label: "待处理项",
          value: String(pendingIssues.length),
          hint: pendingIssues.length ? "来自 pending_issues / preflight" : "当前无阻塞项",
        },
        {
          label: "试跑条件",
          value: canStartTrial ? "已满足" : "未满足",
          hint: getIssueSummary(preflight),
        },
      ]}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button
            asChild
            variant="outline"
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            <Link href="/datamakepool/templates">
              <Layers className="h-4 w-4" />
              模板台
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            <Link href="/datamakepool/http-assets">
              <Database className="h-4 w-4" />
              HTTP 资产
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            <Link href="/datamakepool/sql-assets">
              <ArrowRight className="h-4 w-4" />
              SQL 资产
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            className="border-border/80 bg-background/70 backdrop-blur-sm"
          >
            <Link href="/datamakepool/audits">
              <GitBranch className="h-4 w-4" />
              审计台
            </Link>
          </Button>
          <Button
            variant="outline"
            onClick={() => void loadFlowdraft({ showRefreshingState: true })}
            disabled={isLoading || isRefreshing || (!activeConversationId && !activeFlowdraftId)}
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
      <div className="grid h-full min-h-0 gap-6 p-6 xl:grid-cols-[minmax(0,1.1fr)_430px]">
        <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
          <CardHeader className="border-b border-border/70">
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              <Bot className="h-3.5 w-3.5" />
              探索会话
            </div>
            <CardTitle>聊天输入与系统摘要</CardTitle>
            <CardDescription>
              当前 MVP 仍不回放完整历史消息，但已经把 FlowDraft 真相、步骤编辑和快照差异挂到同一条探索链上。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-col px-0">
            {!activeConversationId ? (
              <div className="space-y-4 p-4">
                <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4 text-sm text-muted-foreground">
                  先创建一个探索会话，再继续输入你的造数目标。当前后端会根据完整用户转录生成确定性 bootstrap FlowDraft。
                </div>

                {actionError ? (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                    {actionError}
                  </div>
                ) : null}

                <Input
                  value={titleInput}
                  onChange={(event) => setTitleInput(event.target.value)}
                  placeholder="会话标题（可选）"
                  disabled={isCreatingConversation}
                />
                <Textarea
                  value={objectiveInput}
                  onChange={(event) => setObjectiveInput(event.target.value)}
                  placeholder="先写一句探索目标，例如：我要生成某系统近 7 天的活跃用户样本，并补齐标签。"
                  className="min-h-28"
                  disabled={isCreatingConversation}
                />
                <Button
                  onClick={() => void handleCreateConversation()}
                  disabled={isCreatingConversation}
                  className="w-full"
                >
                  {isCreatingConversation ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  创建探索会话
                </Button>
              </div>
            ) : (
              <>
                <div className="border-b border-border/70 px-4 py-4">
                  <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.16em] text-primary/80">
                          当前会话
                        </div>
                        <div className="mt-2 text-lg font-semibold text-foreground">
                          {flowdraft?.title || conversation?.title || "探索会话"}
                        </div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          会话 #{activeConversationId} · FlowDraft #{flowdraft?.id ?? activeFlowdraftId ?? "--"}
                        </div>
                      </div>
                      <Badge
                        variant="outline"
                        className={cn("font-medium", flowdraftStatusMeta.className)}
                      >
                        {flowdraftStatusMeta.label}
                      </Badge>
                    </div>
                    <div className="mt-3 text-sm leading-6 text-muted-foreground">
                      {flowdraft?.objective?.trim() ||
                        conversation?.objective?.trim() ||
                        "还没有沉淀出明确目标，建议继续补充输入范围、系统域和预期输出。"}
                    </div>
                  </div>
                </div>

                <ScrollArea className="flex-1">
                  <div className="space-y-4 p-4">
                    {timeline.length ? (
                      timeline.map((message) => <TimelineBubble key={message.id} message={message} />)
                    ) : (
                      <div className="rounded-xl border border-dashed border-border/80 px-4 py-8 text-sm text-muted-foreground">
                        当前还没有本轮会话时间线，先发一条消息，让系统生成或刷新 FlowDraft。
                      </div>
                    )}
                  </div>
                </ScrollArea>

                <div className="border-t border-border/70 p-4">
                  {actionFeedback ? (
                    <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
                      {actionFeedback}
                    </div>
                  ) : null}
                  {actionError ? (
                    <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                      {actionError}
                    </div>
                  ) : null}
                  <div className="grid gap-3">
                    <Textarea
                      value={messageInput}
                      onChange={(event) => setMessageInput(event.target.value)}
                      placeholder="继续补充你的需求、约束、输入参数和预期输出。"
                      className="min-h-28"
                      disabled={isSendingMessage}
                    />
                    <Button onClick={() => void handleSendMessage()} disabled={isSendingMessage}>
                      {isSendingMessage ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                      发送并刷新 FlowDraft
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <div className="grid min-h-0 gap-6 xl:grid-rows-[auto_auto_minmax(0,1fr)]">
          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Workflow className="h-3.5 w-3.5" />
                FlowDraft 动作
              </div>
              <CardTitle>预检、收敛与试跑</CardTitle>
              <CardDescription>先保证 FlowDraft 真相可读，再把最小动作接到稳定后端接口。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {error ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                  {error}
                </div>
              ) : null}

              <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-sm text-muted-foreground">
                <div>业务图节点：{getGraphNodeCount(flowdraft?.business_graph ?? null)}</div>
                <div className="mt-1">技术图节点：{technicalSteps.length}</div>
                <div className="mt-1">最新快照：{flowdraft?.latest_snapshot_id ? `#${flowdraft.latest_snapshot_id}` : "未记录"}</div>
                <div className="mt-1">
                  最近更新时间：{formatDateLabel(conversation?.updated_at ?? conversation?.created_at)}
                </div>
              </div>

              <div className="grid gap-2">
                <Button
                  variant="outline"
                  onClick={() => void handleRunPreflight()}
                  disabled={!flowdraft || isRunningPreflight || isResolvingFlowdraft || isStartingTrial}
                >
                  {isRunningPreflight ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  执行预检
                </Button>
                <Button
                  variant="outline"
                  onClick={() => void handleResolveFlowdraft()}
                  disabled={!flowdraft || isResolvingFlowdraft || isRunningPreflight || isStartingTrial}
                >
                  {isResolvingFlowdraft ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Workflow className="h-4 w-4" />
                  )}
                  整份收敛
                </Button>
                <Button
                  onClick={() => void handleStartTrial()}
                  disabled={!flowdraft || !canStartTrial || isStartingTrial || isResolvingFlowdraft}
                >
                  {isStartingTrial ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  发起试跑
                </Button>
              </div>

              <div className="text-xs leading-5 text-muted-foreground">
                当前实现仍是“稳定主链优先”：聊天刷新草稿、步骤可编辑、快照可回看、预检后可试跑，不在这里展开复杂的多轮智能澄清策略。
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Sparkles className="h-3.5 w-3.5" />
                预检摘要
              </div>
              <CardTitle>待确认项</CardTitle>
              <CardDescription>这里优先展示阻塞原因、问题类型和建议动作，帮助继续补充聊天输入或局部修改步骤。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              <div className="rounded-xl border border-border/70 bg-muted/20 p-3 text-sm text-muted-foreground">
                <div>结论：{getIssueSummary(preflight)}</div>
                <div className="mt-1">
                  建议动作：
                  {preflight?.suggested_actions?.length
                    ? preflight.suggested_actions.map(getSuggestedActionLabel).join("、")
                    : "无"}
                </div>
              </div>

              {preflight?.grouped_by_type && Object.keys(preflight.grouped_by_type).length ? (
                <div className="flex flex-wrap gap-2">
                  {Object.entries(preflight.grouped_by_type).map(([issueType, items]) => (
                    <Badge
                      key={issueType}
                      variant="outline"
                      className="border-border/70 bg-background text-foreground"
                    >
                      {getIssueTypeLabel(issueType)} · {items.length}
                    </Badge>
                  ))}
                </div>
              ) : null}

              {!pendingIssues.length ? (
                <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                  当前没有待处理阻塞项。
                </div>
              ) : (
                <div className="space-y-3">
                  {pendingIssues.map((issue, index) => (
                    <PendingIssueCard
                      key={`${issue.issue_type}-${issue.step_id ?? "global"}-${index}`}
                      issue={issue}
                    />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="min-h-0 overflow-hidden border-border/70 bg-card/80 backdrop-blur-sm">
            <CardHeader className="border-b border-border/70 pb-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                <Database className="h-3.5 w-3.5" />
                设计与版本
              </div>
              <CardTitle>FlowDraft 细节工作台</CardTitle>
              <CardDescription>把步骤设计、快照差异和图契约放进同一块工作区，避免前台只剩原始 JSON。</CardDescription>
              <Tabs value={detailTab} onValueChange={setDetailTab}>
                <TabsList className="mt-4 w-full">
                  <TabsTrigger value="step">FlowStepDesign</TabsTrigger>
                  <TabsTrigger value="snapshot">Snapshot / Diff</TabsTrigger>
                  <TabsTrigger value="graph">Graph / Contract</TabsTrigger>
                </TabsList>
              </Tabs>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              <Tabs value={detailTab} onValueChange={setDetailTab} className="h-full min-h-0">
                <TabsContent value="step" className="h-full min-h-0">
                  <ScrollArea className="h-full">
                    <div className="space-y-4 p-4">
                      {!technicalSteps.length ? (
                        <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                          当前 FlowDraft 还没有可编辑的技术步骤。
                        </div>
                      ) : (
                        <>
                          <div className="grid gap-2">
                            {technicalSteps.map((step) => (
                              <button
                                key={step.step_id}
                                type="button"
                                onClick={() => setSelectedStepId(step.step_id)}
                                className={cn(
                                  "rounded-2xl border p-3 text-left transition-all",
                                  step.step_id === selectedStepId
                                    ? "border-primary/35 bg-primary/10"
                                    : "border-border/70 bg-background/70 hover:border-primary/20 hover:bg-muted/20"
                                )}
                              >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <div className="font-medium text-foreground">
                                      {step.step_name}
                                    </div>
                                    <div className="mt-1 text-xs text-muted-foreground">
                                      {getStepTypeLabel(step.step_type)} · step_id={step.step_id}
                                    </div>
                                  </div>
                                  <Badge
                                    variant="outline"
                                    className={cn(
                                      "font-medium",
                                      step.pending_flags?.length
                                        ? "border-amber-200 bg-amber-50 text-amber-700"
                                        : "border-emerald-200 bg-emerald-50 text-emerald-700"
                                    )}
                                  >
                                    {getStepStatusLabel(step)}
                                  </Badge>
                                </div>
                              </button>
                            ))}
                          </div>

                          {selectedStep ? (
                            <>
                              <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <div className="text-xs uppercase tracking-[0.16em] text-primary/80">
                                      当前步骤
                                    </div>
                                    <div className="mt-2 text-lg font-semibold text-foreground">
                                      {selectedStep.step_name}
                                    </div>
                                    <div className="mt-2 text-sm text-muted-foreground">
                                      {getStepTypeLabel(selectedStep.step_type)} · step_id=
                                      {selectedStep.step_id}
                                    </div>
                                  </div>
                                  <div className="flex flex-wrap gap-2">
                                    {selectedStep.pending_flags?.length ? (
                                      selectedStep.pending_flags.map((flag) => (
                                        <Badge
                                          key={`${selectedStep.step_id}-${flag}`}
                                          variant="outline"
                                          className="border-amber-200 bg-amber-50 text-amber-700"
                                        >
                                          {flag}
                                        </Badge>
                                      ))
                                    ) : (
                                      <Badge
                                        variant="outline"
                                        className="border-emerald-200 bg-emerald-50 text-emerald-700"
                                      >
                                        当前无阻塞
                                      </Badge>
                                    )}
                                  </div>
                                </div>

                                <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
                                  <div>
                                    依赖步骤：
                                    {selectedStep.depends_on?.length
                                      ? selectedStep.depends_on.join("、")
                                      : "无"}
                                  </div>
                                  <div>可编辑字段：{selectedStepEditableFields.length}</div>
                                </div>
                              </div>

                              {selectedStepEditableFields.length ? (
                                <>
                                  <div className="space-y-3">
                                    {selectedStepEditableFields.map((field) => (
                                      <StepEditorField
                                        key={`${selectedStep.step_id}-${field.name}`}
                                        field={field}
                                        value={stepEditorValues[field.name] ?? ""}
                                        disabled={isPatchingStep || isResolvingStep}
                                        onChange={(fieldName, value) =>
                                          setStepEditorValues((current) => ({
                                            ...current,
                                            [fieldName]: value,
                                          }))
                                        }
                                      />
                                    ))}
                                  </div>

                                  <div className="grid gap-2 sm:grid-cols-2">
                                    <Button
                                      variant="outline"
                                      onClick={() => void handlePatchSelectedStep()}
                                      disabled={isPatchingStep || isResolvingStep}
                                    >
                                      {isPatchingStep ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                      ) : (
                                        <Database className="h-4 w-4" />
                                      )}
                                      保存步骤改动
                                    </Button>
                                    <Button
                                      onClick={() => void handleResolveSelectedStep()}
                                      disabled={isResolvingStep || isPatchingStep}
                                    >
                                      {isResolvingStep ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                      ) : (
                                        <Workflow className="h-4 w-4" />
                                      )}
                                      局部收敛
                                    </Button>
                                  </div>
                                </>
                              ) : (
                                <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                                  当前步骤没有开放结构化可编辑字段。
                                </div>
                              )}

                              {selectedStepDesignIntentPreview ? (
                                <div>
                                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                    Design Intent
                                  </div>
                                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                                    {selectedStepDesignIntentPreview}
                                  </pre>
                                </div>
                              ) : null}

                              {selectedStepRationalePreview ? (
                                <div>
                                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                    Resolution Rationale
                                  </div>
                                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                                    {selectedStepRationalePreview}
                                  </pre>
                                </div>
                              ) : null}

                              {selectedStepPlanPreview ? (
                                <div>
                                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                    Resolved Execution Plan
                                  </div>
                                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                                    {selectedStepPlanPreview}
                                  </pre>
                                </div>
                              ) : null}

                              {selectedStepAssetSnapshotPreview ? (
                                <div>
                                  <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                    Asset Version Snapshot
                                  </div>
                                  <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                                    {selectedStepAssetSnapshotPreview}
                                  </pre>
                                </div>
                              ) : null}
                            </>
                          ) : null}
                        </>
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="snapshot" className="h-full min-h-0">
                  <ScrollArea className="h-full">
                    <div className="space-y-4 p-4">
                      {snapshotError ? (
                        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                          {snapshotError}
                        </div>
                      ) : null}

                      {isLoadingSnapshots ? (
                        <div className="flex items-center rounded-xl border border-border/70 bg-muted/20 px-3 py-4 text-sm text-muted-foreground">
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          正在加载 FlowDraft 快照
                        </div>
                      ) : !snapshots.length ? (
                        <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                          当前 FlowDraft 还没有关键快照可比较。
                        </div>
                      ) : (
                        <>
                          <div className="space-y-2">
                            {snapshots.map((snapshot) => (
                              <button
                                key={snapshot.snapshot_id}
                                type="button"
                                onClick={() => void handleSelectSnapshot(snapshot.snapshot_id)}
                                className={cn(
                                  "w-full rounded-2xl border p-3 text-left transition-all",
                                  snapshot.snapshot_id === selectedSnapshotId
                                    ? "border-primary/35 bg-primary/10"
                                    : "border-border/70 bg-background/70 hover:border-primary/20 hover:bg-muted/20"
                                )}
                              >
                                <div className="flex flex-wrap items-center justify-between gap-3">
                                  <div>
                                    <div className="font-medium text-foreground">
                                      快照 #{snapshot.snapshot_id}
                                    </div>
                                    <div className="mt-1 text-xs text-muted-foreground">
                                      {getSnapshotTypeLabel(snapshot.snapshot_type)} · 创建者 #
                                      {snapshot.created_by}
                                    </div>
                                  </div>
                                  <div className="text-xs text-muted-foreground">
                                    {formatDateLabel(snapshot.created_at)}
                                  </div>
                                </div>
                              </button>
                            ))}
                          </div>

                          {isLoadingDiff ? (
                            <div className="flex items-center rounded-xl border border-border/70 bg-muted/20 px-3 py-4 text-sm text-muted-foreground">
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              正在加载版本差异
                            </div>
                          ) : flowdraftDiff ? (
                            <>
                              <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4 text-sm text-muted-foreground">
                                <div>比较基线：{flowdraftDiff.before.label}</div>
                                <div className="mt-1">对比目标：{flowdraftDiff.after.label}</div>
                                <div className="mt-1">
                                  当前默认把选中快照与“当前草稿”做差异比较。
                                </div>
                              </div>

                              <DiffSummaryCard
                                title="Business Graph Diff"
                                chunk={flowdraftDiff.business_graph_diff}
                              />
                              <DiffSummaryCard
                                title="Technical Graph Diff"
                                chunk={flowdraftDiff.technical_graph_diff}
                              />
                              <DiffSummaryCard
                                title="Preflight Summary Diff"
                                chunk={flowdraftDiff.preflight_summary_diff}
                              />
                            </>
                          ) : (
                            <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                              选择一个快照后，这里会显示与当前 FlowDraft 的差异摘要。
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                <TabsContent value="graph" className="h-full min-h-0">
                  <ScrollArea className="h-full">
                    <div className="space-y-4 p-4">
                      {businessGraphPreview ? (
                        <div>
                          <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                            Business Graph
                          </div>
                          <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                            {businessGraphPreview}
                          </pre>
                        </div>
                      ) : null}

                      {technicalGraphPreview ? (
                        <div>
                          <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                            Technical Graph
                          </div>
                          <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                            {technicalGraphPreview}
                          </pre>
                        </div>
                      ) : null}

                      {inputSchemaPreview ? (
                        <div>
                          <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                            Input Schema Draft
                          </div>
                          <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                            {inputSchemaPreview}
                          </pre>
                        </div>
                      ) : null}

                      {outputMappingPreview ? (
                        <div>
                          <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                            Output Mapping Draft
                          </div>
                          <pre className="overflow-x-auto rounded-xl border border-border/70 bg-muted/20 p-3 text-xs leading-5 text-muted-foreground">
                            {outputMappingPreview}
                          </pre>
                        </div>
                      ) : null}

                      {!businessGraphPreview &&
                      !technicalGraphPreview &&
                      !inputSchemaPreview &&
                      !outputMappingPreview ? (
                        <div className="rounded-xl border border-dashed border-border/80 px-3 py-4 text-sm text-muted-foreground">
                          当前 FlowDraft 还没有可展示的结构化图或契约快照。
                        </div>
                      ) : null}
                    </div>
                  </ScrollArea>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>
      </div>
    </DatamakepoolShell>
  )
}
