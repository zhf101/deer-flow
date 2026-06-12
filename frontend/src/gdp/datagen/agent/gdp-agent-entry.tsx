"use client";

import {
  BotIcon,
  CheckCircle2Icon,
  ClipboardListIcon,
  Loader2Icon,
  MessageSquareReplyIcon,
  PlayIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SendIcon,
  SparklesIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  continueAgentTaskRun,
  createAgentTaskRun,
  getAgentTaskRun,
  listAgentTaskRunEvents,
  listEnvironments,
  replyAgentTaskRun,
  startGdpAgentRun,
} from "../common/lib/api";
import type {
  DatagenTaskEventResponse,
  DatagenTaskRunResponse,
  DatagenTaskStatus,
  DatagenTaskStepType,
  DeerflowRunResponse,
  EnvironmentResponse,
} from "../common/lib/types";
import { formatUnknownValue } from "../common/lib/value-utils";

const DEFAULT_ENV_VALUE = "__default__";
const TERMINAL_STATUSES = new Set<DatagenTaskStatus>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);

function createThreadId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `gdp-agent-${crypto.randomUUID()}`;
  }
  return `gdp-agent-${Date.now()}`;
}

function parseInputs(text: string): Record<string, unknown> {
  if (!text.trim()) return {};
  const parsed = JSON.parse(text) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("结构化输入必须是 JSON 对象。");
  }
  return parsed as Record<string, unknown>;
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusConfig(status: DatagenTaskStatus | undefined) {
  switch (status) {
    case "COMPLETED":
      return {
        label: "完成",
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
        icon: CheckCircle2Icon,
      };
    case "FAILED":
      return {
        label: "失败",
        className: "border-destructive/30 bg-destructive/10 text-destructive",
        icon: TriangleAlertIcon,
      };
    case "CANCELLED":
      return {
        label: "取消",
        className: "border-muted bg-muted text-muted-foreground",
        icon: TriangleAlertIcon,
      };
    case "WAITING_USER":
      return {
        label: "等待用户",
        className: "border-amber-200 bg-amber-50 text-amber-700",
        icon: MessageSquareReplyIcon,
      };
    case "RUNNING":
      return {
        label: "运行中",
        className: "border-sky-200 bg-sky-50 text-sky-700",
        icon: Loader2Icon,
      };
    case "PLANNING":
      return {
        label: "规划中",
        className: "border-violet-200 bg-violet-50 text-violet-700",
        icon: SparklesIcon,
      };
    default:
      return {
        label: "未启动",
        className: "border-muted bg-background text-muted-foreground",
        icon: BotIcon,
      };
  }
}

function planStepTypeLabel(stepType: DatagenTaskStepType) {
  switch (stepType) {
    case "RUN_SCENE":
      return "执行场景";
    case "REFLECT":
      return "结果校验";
    case "DESIGN_SCENE":
      return "设计场景";
    case "CONFIG_HTTP_SOURCE":
      return "HTTP Source";
    case "CONFIG_SQL_SOURCE":
      return "SQL Source";
    case "CONFIG_INFRA":
      return "基础配置";
    case "ASK_USER":
      return "用户确认";
    default:
      return stepType;
  }
}

function StatusBadge({ status }: { status?: DatagenTaskStatus }) {
  const config = statusConfig(status);
  const Icon = config.icon;
  return (
    <Badge variant="outline" className={cn("gap-1 rounded-md", config.className)}>
      <Icon className={cn("size-3", status === "RUNNING" ? "animate-spin" : "")} />
      {config.label}
    </Badge>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[88px_1fr] gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all font-mono text-foreground">{value || "-"}</span>
    </div>
  );
}

function EventItem({ event }: { event: DatagenTaskEventResponse }) {
  return (
    <div className="rounded-md border bg-background px-3 py-2">
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="h-5 rounded text-[10px]">
          #{event.eventNo}
        </Badge>
        <span className="min-w-0 flex-1 truncate text-xs font-medium">
          {event.message}
        </span>
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {formatDateTime(event.createdAt)}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
        <span>{event.phase}</span>
        <span>/</span>
        <span>{event.eventType}</span>
      </div>
    </div>
  );
}

export function GDPAgentEntry() {
  const [threadId, setThreadId] = useState(createThreadId);
  const [intent, setIntent] = useState("");
  const [envCode, setEnvCode] = useState(DEFAULT_ENV_VALUE);
  const [inputsText, setInputsText] = useState("{\n}");
  const [replyText, setReplyText] = useState("");
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [loadingEnvs, setLoadingEnvs] = useState(false);
  const [starting, setStarting] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [replying, setReplying] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [taskRun, setTaskRun] = useState<DatagenTaskRunResponse | null>(null);
  const [run, setRun] = useState<DeerflowRunResponse | null>(null);
  const [events, setEvents] = useState<DatagenTaskEventResponse[]>([]);

  const canPoll = taskRun ? !TERMINAL_STATUSES.has(taskRun.status) : false;
  const canStart = intent.trim().length > 0 && !starting;
  const canReply =
    taskRun?.status === "WAITING_USER" && replyText.trim().length > 0 && !replying;

  const selectedEnvLabel = useMemo(() => {
    if (envCode === DEFAULT_ENV_VALUE) return "默认 DEV";
    return environments.find((env) => env.envCode === envCode)?.envName ?? envCode;
  }, [envCode, environments]);

  useEffect(() => {
    setLoadingEnvs(true);
    listEnvironments()
      .then((items) => {
        setEnvironments(items.filter((item) => item.status === "ENABLED"));
      })
      .catch((error) => {
        toast.error(error instanceof Error ? error.message : "加载环境失败");
      })
      .finally(() => setLoadingEnvs(false));
  }, []);

  const refreshTaskRun = useCallback(
    async (targetTaskRunId?: string) => {
      const taskRunId = targetTaskRunId ?? taskRun?.taskRunId;
      if (!taskRunId) return;
      setRefreshing(true);
      try {
        const [nextTaskRun, nextEvents] = await Promise.all([
          getAgentTaskRun(taskRunId),
          listAgentTaskRunEvents(taskRunId),
        ]);
        setTaskRun(nextTaskRun);
        setEvents(nextEvents);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "刷新任务状态失败");
      } finally {
        setRefreshing(false);
      }
    },
    [taskRun?.taskRunId],
  );

  useEffect(() => {
    if (!canPoll || !taskRun?.taskRunId) return;
    const timer = window.setInterval(() => {
      void refreshTaskRun(taskRun.taskRunId);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [canPoll, refreshTaskRun, taskRun?.taskRunId]);

  const resetSession = useCallback(() => {
    setThreadId(createThreadId());
    setTaskRun(null);
    setRun(null);
    setEvents([]);
    setReplyText("");
  }, []);

  const handleStart = useCallback(async () => {
    if (!canStart) return;
    let inputs: Record<string, unknown>;
    try {
      inputs = parseInputs(inputsText);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "结构化输入不是合法 JSON。");
      return;
    }

    setStarting(true);
    setTaskRun(null);
    setRun(null);
    setEvents([]);
    try {
      const created = await createAgentTaskRun({
        userIntent: intent.trim(),
        envCode: envCode === DEFAULT_ENV_VALUE ? undefined : envCode,
        inputs,
      });
      setTaskRun(created);
      const started = await startGdpAgentRun(threadId, created.taskRunId);
      setTaskRun(started.taskRun);
      setRun(started.run);
      toast.success("GDP Agent 已发起");
      await refreshTaskRun(created.taskRunId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "发起 GDP Agent 失败");
    } finally {
      setStarting(false);
    }
  }, [canStart, envCode, inputsText, intent, refreshTaskRun, threadId]);

  const handleContinue = useCallback(async () => {
    if (!taskRun) return;
    setContinuing(true);
    try {
      const response = await continueAgentTaskRun(taskRun.taskRunId);
      setTaskRun(response.taskRun);
      toast.success(response.message);
      await refreshTaskRun(response.taskRun.taskRunId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "继续推进失败");
    } finally {
      setContinuing(false);
    }
  }, [refreshTaskRun, taskRun]);

  const handleReply = useCallback(async () => {
    if (!taskRun || !canReply) return;
    setReplying(true);
    try {
      await replyAgentTaskRun(taskRun.taskRunId, replyText.trim());
      setReplyText("");
      toast.success("回复已提交");
      await refreshTaskRun(taskRun.taskRunId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "提交回复失败");
    } finally {
      setReplying(false);
    }
  }, [canReply, refreshTaskRun, replyText, taskRun]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <header className="flex shrink-0 items-center justify-between border-b px-6 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <BotIcon className="size-5 text-primary" />
            <h1 className="text-lg font-semibold tracking-tight">GDP Agent</h1>
            <StatusBadge status={taskRun?.status} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {taskRun ? `${taskRun.phase} / ${selectedEnvLabel}` : selectedEnvLabel}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={resetSession} className="gap-1.5">
            <RotateCcwIcon className="size-3.5" />
            新会话
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refreshTaskRun()}
            disabled={!taskRun || refreshing}
            className="gap-1.5"
          >
            <RefreshCwIcon className={cn("size-3.5", refreshing ? "animate-spin" : "")} />
            刷新
          </Button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[420px_1fr] overflow-hidden">
        <section className="flex min-h-0 flex-col border-r">
          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-5 p-5">
              <div className="space-y-2">
                <label className="text-xs font-medium" htmlFor="gdp-agent-intent">
                  造数目标
                </label>
                <Textarea
                  id="gdp-agent-intent"
                  value={intent}
                  onChange={(event) => setIntent(event.target.value)}
                  placeholder="例如：帮我为手机号 13800000000 准备一条可完成登录链路的测试数据"
                  className="min-h-28 resize-none text-sm"
                />
              </div>

              <div className="grid grid-cols-[1fr_1fr] gap-3">
                <div className="space-y-2">
                  <label className="text-xs font-medium">环境</label>
                  <Select value={envCode} onValueChange={setEnvCode}>
                    <SelectTrigger>
                      <SelectValue placeholder="选择环境" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DEFAULT_ENV_VALUE}>默认 DEV</SelectItem>
                      {environments.map((env) => (
                        <SelectItem key={env.envCode} value={env.envCode}>
                          {env.envName} ({env.envCode})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-medium" htmlFor="gdp-agent-thread">
                    Thread
                  </label>
                  <Input
                    id="gdp-agent-thread"
                    value={threadId}
                    onChange={(event) => setThreadId(event.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium" htmlFor="gdp-agent-inputs">
                  结构化输入
                </label>
                <Textarea
                  id="gdp-agent-inputs"
                  value={inputsText}
                  onChange={(event) => setInputsText(event.target.value)}
                  className="min-h-32 resize-none font-mono text-xs"
                />
              </div>

              <Button
                className="h-10 w-full gap-2"
                onClick={handleStart}
                disabled={!canStart || loadingEnvs}
              >
                {starting ? (
                  <Loader2Icon className="size-4 animate-spin" />
                ) : (
                  <PlayIcon className="size-4" />
                )}
                发起 GDP Agent
              </Button>

              {taskRun?.status === "WAITING_USER" ? (
                <div className="space-y-3 rounded-md border border-amber-200 bg-amber-50/60 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
                    <MessageSquareReplyIcon className="size-4" />
                    等待用户回复
                  </div>
                  <Textarea
                    value={replyText}
                    onChange={(event) => setReplyText(event.target.value)}
                    placeholder="输入补充信息或确认内容"
                    className="min-h-20 resize-none bg-background"
                  />
                  <Button
                    variant="outline"
                    className="w-full gap-2 bg-background"
                    disabled={!canReply}
                    onClick={handleReply}
                  >
                    {replying ? (
                      <Loader2Icon className="size-4 animate-spin" />
                    ) : (
                      <SendIcon className="size-4" />
                    )}
                    提交回复
                  </Button>
                </div>
              ) : null}

              {taskRun ? (
                <Button
                  variant="outline"
                  className="w-full gap-2"
                  onClick={handleContinue}
                  disabled={continuing || TERMINAL_STATUSES.has(taskRun.status)}
                >
                  {continuing ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <SendIcon className="size-4" />
                  )}
                  继续推进
                </Button>
              ) : null}
            </div>
          </ScrollArea>
        </section>

        <section className="flex min-h-0 flex-col">
          <div className="grid shrink-0 grid-cols-3 gap-3 border-b p-4">
            <div className="rounded-md border bg-card p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium">
                <ClipboardListIcon className="size-4 text-primary" />
                Task Run
              </div>
              <div className="space-y-1.5">
                <InfoRow label="ID" value={taskRun?.taskRunId ?? "-"} />
                <InfoRow label="状态" value={taskRun?.status ?? "-"} />
                <InfoRow label="阶段" value={taskRun?.phase ?? "-"} />
              </div>
            </div>
            <div className="rounded-md border bg-card p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium">
                <BotIcon className="size-4 text-primary" />
                DeerFlow
              </div>
              <div className="space-y-1.5">
                <InfoRow label="Thread" value={taskRun?.deerflowThreadId ?? run?.thread_id ?? threadId} />
                <InfoRow label="Run" value={taskRun?.deerflowRunId ?? run?.run_id ?? "-"} />
                <InfoRow label="Assistant" value={run?.assistant_id ?? "gdp_agent"} />
              </div>
            </div>
            <div className="rounded-md border bg-card p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium">
                <SparklesIcon className="size-4 text-primary" />
                摘要
              </div>
              <div className="space-y-1.5">
                <InfoRow label="环境" value={taskRun?.envCode ?? selectedEnvLabel} />
                <InfoRow label="事件" value={String(events.length)} />
                <InfoRow label="更新" value={formatDateTime(taskRun?.updatedAt)} />
              </div>
            </div>
          </div>

          <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_320px] overflow-hidden">
            <div className="flex min-h-0 flex-col">
              <div className="flex shrink-0 items-center justify-between border-b px-4 py-3">
                <h2 className="text-sm font-semibold">事件流</h2>
                <Badge variant="secondary" className="rounded-md">
                  {events.length}
                </Badge>
              </div>
              <ScrollArea className="min-h-0 flex-1">
                <div className="space-y-2 p-4">
                  {events.length > 0 ? (
                    events.map((event) => <EventItem key={event.eventId} event={event} />)
                  ) : (
                    <Alert>
                      <BotIcon className="size-4" />
                      <AlertTitle>暂无事件</AlertTitle>
                      <AlertDescription>
                        发起后这里会显示 GDP Agent 的任务审计记录。
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </ScrollArea>
            </div>

            <aside className="min-h-0 border-l">
              <ScrollArea className="h-full">
                <div className="space-y-4 p-4">
                  <section>
                    <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
                      当前计划
                    </h3>
                    {taskRun?.plan?.summary ? (
                      <p className="rounded-md border bg-muted/30 p-3 text-xs leading-5">
                        {taskRun.plan.summary}
                      </p>
                    ) : (
                      <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                        暂无计划摘要
                      </p>
                    )}
                    {taskRun?.plan?.steps.length ? (
                      <div className="mt-2 space-y-2">
                        {taskRun.plan.steps.map((step) => (
                          <div key={step.stepNo} className="rounded-md border p-2">
                            <div className="flex items-center gap-2">
                              <Badge variant="secondary" className="h-5 rounded text-[10px]">
                                #{step.stepNo}
                              </Badge>
                              <span className="min-w-0 flex-1 truncate text-xs font-medium">
                                {step.goal}
                              </span>
                              <Badge variant="outline" className="h-5 rounded text-[10px]">
                                {step.status}
                              </Badge>
                            </div>
                            <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                              {planStepTypeLabel(step.stepType)}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </section>

                  <Separator />

                  <section>
                    <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
                      变量
                    </h3>
                    {taskRun?.visibleVariables.length ? (
                      <div className="space-y-2">
                        {taskRun.visibleVariables.map((variable) => (
                          <div key={variable.name} className="rounded-md border p-2">
                            <div className="text-xs font-medium">{variable.label ?? variable.name}</div>
                            <div className="mt-1 break-all font-mono text-[11px] text-muted-foreground">
                              {formatUnknownValue(variable.valuePreview ?? variable.value, "-")}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                        暂无变量
                      </p>
                    )}
                  </section>

                  {taskRun?.failureMessage ? (
                    <>
                      <Separator />
                      <Alert variant="destructive">
                        <TriangleAlertIcon className="size-4" />
                        <AlertTitle>{taskRun.failureType ?? "任务失败"}</AlertTitle>
                        <AlertDescription>{taskRun.failureMessage}</AlertDescription>
                      </Alert>
                    </>
                  ) : null}

                  {taskRun?.finalSummary ? (
                    <>
                      <Separator />
                      <section>
                        <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
                          最终总结
                        </h3>
                        <p className="rounded-md border bg-muted/30 p-3 text-xs leading-5">
                          {taskRun.finalSummary}
                        </p>
                      </section>
                    </>
                  ) : null}
                </div>
              </ScrollArea>
            </aside>
          </div>
        </section>
      </div>
    </div>
  );
}
