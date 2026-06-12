"use client";

import {
  AlertTriangleIcon,
  BanIcon,
  CheckCircle2Icon,
  ClipboardListIcon,
  DatabaseIcon,
  FileJsonIcon,
  Loader2Icon,
  MessageSquareReplyIcon,
  PlayIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SendIcon,
  ShieldCheckIcon,
  SquareActivityIcon,
  TerminalSquareIcon,
  XCircleIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  cancelAgentRuntimeTaskRun,
  createAgentRuntimeTaskRun,
  getAgentRuntimeTaskRun,
  getAgentRuntimeTimeline,
  listEnvironments,
  listScenes,
  replyAgentRuntimeTaskRun,
  startAgentRuntimeTaskRun,
} from "../common/lib/api";
import type {
  AgentRuntimeAction,
  AgentRuntimeActionAttempt,
  AgentRuntimeEvidence,
  AgentRuntimeObservation,
  AgentRuntimePlanStep,
  AgentRuntimeTaskRunResponse,
  AgentRuntimeTaskRunStatus,
  AgentRuntimeTimelineResponse,
  AgentRuntimeVariable,
  AgentRuntimeVerdict,
  EnvironmentResponse,
  SceneSummary,
} from "../common/lib/types";

type TimelineKind =
  | "step"
  | "action"
  | "attempt"
  | "observation"
  | "evidence"
  | "verdict"
  | "variable";

interface TimelineItem {
  key: string;
  kind: TimelineKind;
  title: string;
  subtitle: string;
  status?: string;
  payload:
    | AgentRuntimePlanStep
    | AgentRuntimeAction
    | AgentRuntimeActionAttempt
    | AgentRuntimeObservation
    | AgentRuntimeEvidence
    | AgentRuntimeVerdict
    | AgentRuntimeVariable;
}

const TERMINAL_STATUSES = new Set<AgentRuntimeTaskRunStatus>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);

const DEFAULT_INPUTS = `{
  "buyer_id": "U1"
}`;

function parseJsonObject(text: string): Record<string, unknown> {
  if (!text.trim()) return {};
  const parsed = JSON.parse(text) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("输入必须是 JSON 对象。");
  }
  return parsed as Record<string, unknown>;
}

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusTone(status?: string) {
  switch (status) {
    case "COMPLETED":
    case "DONE":
    case "SUCCEEDED":
    case "SUCCESS":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "FAILED":
    case "CANCELLED":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    case "WAITING_USER":
    case "BLOCKED":
    case "UNKNOWN_STATE":
    case "NEED_USER":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "RUNNING":
      return "border-sky-200 bg-sky-50 text-sky-700";
    default:
      return "border-border bg-muted/40 text-muted-foreground";
  }
}

function statusIcon(status?: string) {
  switch (status) {
    case "COMPLETED":
    case "DONE":
    case "SUCCEEDED":
    case "SUCCESS":
      return CheckCircle2Icon;
    case "FAILED":
      return XCircleIcon;
    case "CANCELLED":
      return BanIcon;
    case "WAITING_USER":
    case "BLOCKED":
    case "NEED_USER":
      return MessageSquareReplyIcon;
    case "UNKNOWN_STATE":
      return AlertTriangleIcon;
    case "RUNNING":
      return Loader2Icon;
    default:
      return SquareActivityIcon;
  }
}

function StatusBadge({ status }: { status?: string }) {
  const Icon = statusIcon(status);
  return (
    <Badge variant="outline" className={cn("gap-1 rounded-md", statusTone(status))}>
      <Icon className={cn("size-3", status === "RUNNING" ? "animate-spin" : "")} />
      {status ?? "NONE"}
    </Badge>
  );
}

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="grid grid-cols-[92px_1fr] gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all font-mono text-foreground">{value ?? "-"}</span>
    </div>
  );
}

function buildTimeline(timeline: AgentRuntimeTimelineResponse | null): TimelineItem[] {
  if (!timeline) return [];
  return [
    ...timeline.steps.map((step) => ({
      key: `step:${step.step_id}`,
      kind: "step" as const,
      title: `Step #${step.step_no}`,
      subtitle: step.goal,
      status: step.status,
      payload: step,
    })),
    ...timeline.actions.map((action) => ({
      key: `action:${action.action_id}`,
      kind: "action" as const,
      title: "Action",
      subtitle: action.scene_code,
      status: action.status,
      payload: action,
    })),
    ...timeline.attempts.map((attempt) => ({
      key: `attempt:${attempt.attempt_id}`,
      kind: "attempt" as const,
      title: `Attempt #${attempt.attempt_no}`,
      subtitle: attempt.error_message ?? attempt.request_ref,
      status: attempt.status,
      payload: attempt,
    })),
    ...timeline.observations.map((observation) => ({
      key: `observation:${observation.observation_id}`,
      kind: "observation" as const,
      title: "Observation",
      subtitle: observation.raw_ref,
      payload: observation,
    })),
    ...timeline.evidences.map((evidence) => ({
      key: `evidence:${evidence.evidence_id}`,
      kind: "evidence" as const,
      title: "Evidence",
      subtitle: `${evidence.facts.length} facts / ${evidence.missing_facts.length} missing / ${evidence.unknown_facts.length} unknown`,
      status:
        evidence.unknown_facts.length > 0
          ? "UNKNOWN_STATE"
          : evidence.missing_facts.length > 0
            ? "NEED_USER"
            : evidence.facts.every((fact) => fact.passed)
              ? "DONE"
              : "FAILED",
      payload: evidence,
    })),
    ...timeline.verdicts.map((verdict) => ({
      key: `verdict:${verdict.verdict_id}`,
      kind: "verdict" as const,
      title: "Verdict",
      subtitle: verdict.reason,
      status: verdict.verdict_type,
      payload: verdict,
    })),
    ...timeline.variables.map((variable) => ({
      key: `variable:${variable.variable_id}`,
      kind: "variable" as const,
      title: variable.name,
      subtitle: variable.semantic_type,
      status: variable.tainted ? "FAILED" : variable.sensitive ? "NEED_USER" : "DONE",
      payload: variable,
    })),
  ];
}

export function AgentRuntimePage() {
  const [userGoal, setUserGoal] = useState("造一笔已支付订单");
  const [envCode, setEnvCode] = useState("");
  const [sceneCode, setSceneCode] = useState("");
  const [inputsText, setInputsText] = useState(DEFAULT_INPUTS);
  const [replyText, setReplyText] = useState("");
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [loadingScenes, setLoadingScenes] = useState(false);
  const [taskRun, setTaskRun] = useState<AgentRuntimeTaskRunResponse | null>(null);
  const [timeline, setTimeline] = useState<AgentRuntimeTimelineResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const timelineItems = useMemo(() => buildTimeline(timeline), [timeline]);
  const selectedItem = useMemo(
    () => timelineItems.find((item) => item.key === selectedKey) ?? timelineItems.at(-1) ?? null,
    [selectedKey, timelineItems],
  );

  const canCancel = taskRun ? !TERMINAL_STATUSES.has(taskRun.status) : false;
  const canReply = taskRun?.status === "WAITING_USER" && replyText.trim().length > 0;
  const canStartRun = !busy && !loadingScenes && sceneCode.trim().length > 0;

  useEffect(() => {
    listEnvironments()
      .then((items) => {
        const enabled = items.filter((item) => item.status === "ENABLED");
        setEnvironments(enabled);
        setEnvCode((current) => (current.length > 0 ? current : (enabled[0]?.envCode ?? "")));
      })
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : "加载环境失败");
      });

    setLoadingScenes(true);
    listScenes({ status: "PUBLISHED", limit: 200 })
      .then((items) => {
        setScenes(items);
        setSceneCode((current) => {
          if (items.some((scene) => scene.sceneCode === current)) return current;
          return items[0]?.sceneCode ?? "";
        });
      })
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : "加载场景失败");
      })
      .finally(() => setLoadingScenes(false));
  }, []);

  const loadTimeline = useCallback(async (taskRunId: string) => {
    const nextTimeline = await getAgentRuntimeTimeline(taskRunId);
    setTimeline(nextTimeline);
    setSelectedKey((current) => {
      if (current && buildTimeline(nextTimeline).some((item) => item.key === current)) {
        return current;
      }
      return buildTimeline(nextTimeline).at(-1)?.key ?? null;
    });
  }, []);

  const refresh = useCallback(
    async (targetTaskRunId?: string) => {
      const taskRunId = targetTaskRunId ?? taskRun?.task_run_id;
      if (!taskRunId) return;
      setRefreshing(true);
      try {
        const [nextTaskRun] = await Promise.all([
          getAgentRuntimeTaskRun(taskRunId),
          loadTimeline(taskRunId),
        ]);
        setTaskRun(nextTaskRun);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "刷新失败");
      } finally {
        setRefreshing(false);
      }
    },
    [loadTimeline, taskRun?.task_run_id],
  );

  const createOnly = useCallback(async () => {
    if (!userGoal.trim()) {
      toast.error("请输入用户目标");
      return;
    }
    setBusy(true);
    try {
      const created = await createAgentRuntimeTaskRun({
        user_goal: userGoal.trim(),
        env_code: envCode || null,
      });
      setTaskRun(created);
      setTimeline(null);
      setSelectedKey(null);
      toast.success("TaskRun 已创建");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }, [envCode, userGoal]);

  const createAndStart = useCallback(async () => {
    if (!userGoal.trim()) {
      toast.error("请输入用户目标");
      return;
    }
    if (!envCode) {
      toast.error("请选择环境");
      return;
    }
    if (!sceneCode.trim()) {
      toast.error("请选择已发布 Scene");
      return;
    }

    let inputs: Record<string, unknown>;
    try {
      inputs = parseJsonObject(inputsText);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "输入不是合法 JSON");
      return;
    }

    setBusy(true);
    setTimeline(null);
    setSelectedKey(null);
    try {
      const created = await createAgentRuntimeTaskRun({
        user_goal: userGoal.trim(),
        env_code: envCode,
      });
      setTaskRun(created);
      const started = await startAgentRuntimeTaskRun(created.task_run_id, {
        scene_code: sceneCode.trim(),
        inputs,
      });
      setTaskRun(started);
      await loadTimeline(started.task_run_id);
      toast.success("运行已返回");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }, [envCode, inputsText, loadTimeline, sceneCode, userGoal]);

  const cancelRun = useCallback(async () => {
    if (!taskRun) return;
    setBusy(true);
    try {
      const cancelled = await cancelAgentRuntimeTaskRun(taskRun.task_run_id);
      setTaskRun(cancelled);
      await loadTimeline(cancelled.task_run_id);
      toast.success("TaskRun 已取消");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "取消失败");
    } finally {
      setBusy(false);
    }
  }, [loadTimeline, taskRun]);

  const replyRun = useCallback(async () => {
    if (!taskRun || !canReply) return;
    setBusy(true);
    try {
      const replied = await replyAgentRuntimeTaskRun(taskRun.task_run_id, {
        reply_type: "CONFIRM_UNKNOWN_STATE",
        payload: { message: replyText.trim() },
      });
      setReplyText("");
      setTaskRun(replied);
      await loadTimeline(replied.task_run_id);
      toast.success("回复已提交");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "提交回复失败");
    } finally {
      setBusy(false);
    }
  }, [canReply, loadTimeline, replyText, taskRun]);

  const reset = useCallback(() => {
    setTaskRun(null);
    setTimeline(null);
    setSelectedKey(null);
    setReplyText("");
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <header className="flex shrink-0 items-center justify-between border-b px-6 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ShieldCheckIcon className="size-5 text-primary" />
            <h1 className="text-lg font-semibold tracking-tight">GDP Agent 运行台</h1>
            <StatusBadge status={taskRun?.status ?? "CREATED"} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{taskRun?.task_run_id ?? "未创建"}</span>
            <span>/</span>
            <span>{envCode || "-"}</span>
            <span>/</span>
            <span className="font-mono">{sceneCode || "-"}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={!taskRun || refreshing}>
            <RefreshCwIcon className={cn("mr-1.5 size-3.5", refreshing ? "animate-spin" : "")} />
            刷新
          </Button>
          <Button variant="outline" size="sm" onClick={reset} disabled={busy}>
            <RotateCcwIcon className="mr-1.5 size-3.5" />
            重置
          </Button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[360px_minmax(360px,1fr)_420px] overflow-hidden">
        <section className="flex min-h-0 flex-col border-r">
          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-5 p-5">
              <FieldBlock label="用户目标">
                <Textarea
                  value={userGoal}
                  onChange={(event) => setUserGoal(event.target.value)}
                  className="min-h-24 resize-none text-sm"
                />
              </FieldBlock>

              <div className="grid grid-cols-2 gap-3">
                <FieldBlock label="环境">
                  <Select value={envCode} onValueChange={setEnvCode}>
                    <SelectTrigger>
                      <SelectValue placeholder="选择环境" />
                    </SelectTrigger>
                    <SelectContent>
                      {environments.map((env) => (
                        <SelectItem key={env.envCode} value={env.envCode}>
                          {env.envName} ({env.envCode})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FieldBlock>
                <FieldBlock label="Scene">
                  <Select
                    value={sceneCode}
                    onValueChange={setSceneCode}
                    disabled={loadingScenes || scenes.length === 0}
                  >
                    <SelectTrigger className="min-w-0">
                      <SelectValue placeholder={loadingScenes ? "加载场景中" : "选择已发布场景"} />
                    </SelectTrigger>
                    <SelectContent>
                      {scenes.map((scene) => (
                        <SelectItem key={scene.sceneCode} value={scene.sceneCode}>
                          {scene.sceneName} ({scene.sceneCode})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FieldBlock>
              </div>

              <FieldBlock label="输入 JSON">
                <Textarea
                  value={inputsText}
                  onChange={(event) => setInputsText(event.target.value)}
                  className="min-h-44 resize-none font-mono text-xs"
                  spellCheck={false}
                />
              </FieldBlock>

              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" onClick={createOnly} disabled={busy}>
                  <ClipboardListIcon className="mr-1.5 size-4" />
                  创建
                </Button>
                <Button onClick={createAndStart} disabled={!canStartRun}>
                  {busy ? <Loader2Icon className="mr-1.5 size-4 animate-spin" /> : <PlayIcon className="mr-1.5 size-4" />}
                  启动
                </Button>
              </div>

              <Button variant="outline" className="w-full" onClick={cancelRun} disabled={!canCancel || busy}>
                <BanIcon className="mr-1.5 size-4" />
                取消
              </Button>

              {taskRun?.status === "WAITING_USER" ? (
                <div className="space-y-3 rounded-md border border-amber-200 bg-amber-50/60 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
                    <MessageSquareReplyIcon className="size-4" />
                    等待用户
                  </div>
                  <p className="text-xs leading-5 text-amber-800">{taskRun.pending_question}</p>
                  <Textarea
                    value={replyText}
                    onChange={(event) => setReplyText(event.target.value)}
                    className="min-h-20 resize-none bg-background"
                  />
                  <Button variant="outline" className="w-full bg-background" onClick={replyRun} disabled={!canReply || busy}>
                    <SendIcon className="mr-1.5 size-4" />
                    提交
                  </Button>
                </div>
              ) : null}
            </div>
          </ScrollArea>
        </section>

        <section className="flex min-h-0 flex-col">
          <div className="grid shrink-0 grid-cols-3 gap-3 border-b p-4">
            <SummaryPanel title="TaskRun" icon={ClipboardListIcon}>
              <InfoRow label="ID" value={taskRun?.task_run_id} />
              <InfoRow label="状态" value={taskRun?.status} />
              <InfoRow label="结束" value={formatTime(taskRun?.finished_at)} />
            </SummaryPanel>
            <SummaryPanel title="Evidence" icon={DatabaseIcon}>
              <InfoRow label="事实" value={String(timeline?.evidences[0]?.facts.length ?? 0)} />
              <InfoRow label="缺失" value={String(timeline?.evidences[0]?.missing_facts.length ?? 0)} />
              <InfoRow label="未知" value={String(timeline?.evidences[0]?.unknown_facts.length ?? 0)} />
            </SummaryPanel>
            <SummaryPanel title="Verdict" icon={ShieldCheckIcon}>
              <InfoRow label="类型" value={timeline?.verdicts[0]?.verdict_type} />
              <InfoRow label="原因" value={timeline?.verdicts[0]?.reason} />
              <InfoRow label="时间" value={formatTime(timeline?.verdicts[0]?.created_at)} />
            </SummaryPanel>
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex shrink-0 items-center justify-between border-b px-4 py-3">
              <h2 className="text-sm font-semibold">运行时间线</h2>
              <Badge variant="secondary" className="rounded-md">
                {timelineItems.length}
              </Badge>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="space-y-2 p-4">
                {timelineItems.length > 0 ? (
                  timelineItems.map((item) => (
                    <TimelineRow
                      key={item.key}
                      item={item}
                      active={selectedItem?.key === item.key}
                      onSelect={() => setSelectedKey(item.key)}
                    />
                  ))
                ) : (
                  <Alert>
                    <TerminalSquareIcon className="size-4" />
                    <AlertTitle>暂无记录</AlertTitle>
                    <AlertDescription>创建并启动 TaskRun 后显示运行账本。</AlertDescription>
                  </Alert>
                )}
              </div>
            </ScrollArea>
          </div>
        </section>

        <DetailPanel taskRun={taskRun} item={selectedItem} />
      </div>
    </div>
  );
}

function FieldBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-medium">{label}</label>
      {children}
    </div>
  );
}

function SummaryPanel({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof ClipboardListIcon;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium">
        <Icon className="size-4 text-primary" />
        {title}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function TimelineRow({
  item,
  active,
  onSelect,
}: {
  item: TimelineItem;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-3 rounded-md border px-3 py-2 text-left transition-colors",
        active ? "border-primary bg-primary/5" : "bg-background hover:bg-muted/50",
      )}
    >
      <div className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border", statusTone(item.status))}>
        {item.kind === "evidence" ? (
          <FileJsonIcon className="size-4" />
        ) : item.kind === "verdict" ? (
          <ShieldCheckIcon className="size-4" />
        ) : (
          <SquareActivityIcon className="size-4" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{item.title}</span>
          {item.status ? <StatusBadge status={item.status} /> : null}
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">{item.subtitle}</p>
      </div>
    </button>
  );
}

function DetailPanel({
  taskRun,
  item,
}: {
  taskRun: AgentRuntimeTaskRunResponse | null;
  item: TimelineItem | null;
}) {
  return (
    <aside className="flex min-h-0 flex-col border-l bg-muted/10">
      <div className="shrink-0 border-b px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">详情</h2>
          {item?.status ? <StatusBadge status={item.status} /> : null}
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 p-4">
          {taskRun ? (
            <section className="space-y-1.5 rounded-md border bg-background p-3">
              <InfoRow label="TaskRun" value={taskRun.task_run_id} />
              <InfoRow label="目标" value={taskRun.user_goal} />
              <InfoRow label="环境" value={taskRun.env_code} />
              <InfoRow label="更新" value={formatTime(taskRun.updated_at)} />
            </section>
          ) : null}

          {taskRun?.failure_reason ? (
            <Alert variant="destructive">
              <AlertTriangleIcon className="size-4" />
              <AlertTitle>失败原因</AlertTitle>
              <AlertDescription>{taskRun.failure_reason}</AlertDescription>
            </Alert>
          ) : null}

          {taskRun?.pending_question ? (
            <Alert className="border-amber-200 bg-amber-50 text-amber-800">
              <MessageSquareReplyIcon className="size-4" />
              <AlertTitle>等待确认</AlertTitle>
              <AlertDescription>{taskRun.pending_question}</AlertDescription>
            </Alert>
          ) : null}

          <Separator />

          {item ? (
            <section className="space-y-3">
              <div>
                <div className="text-xs font-semibold text-muted-foreground">{item.kind}</div>
                <h3 className="mt-1 text-sm font-medium">{item.title}</h3>
                <p className="mt-1 break-words text-xs text-muted-foreground">{item.subtitle}</p>
              </div>
              <pre className="max-h-[520px] overflow-auto rounded-md border bg-background p-3 text-xs leading-5">
                {formatJson(item.payload)}
              </pre>
            </section>
          ) : (
            <Alert>
              <FileJsonIcon className="size-4" />
              <AlertTitle>未选择对象</AlertTitle>
              <AlertDescription>选择时间线记录后显示结构化详情。</AlertDescription>
            </Alert>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
