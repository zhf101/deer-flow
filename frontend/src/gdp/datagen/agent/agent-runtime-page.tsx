"use client";

import {
  BanIcon,
  Loader2Icon,
  PanelRightIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  AgentRuntimeSceneCandidate,
  AgentRuntimeTaskRunResponse,
  AgentRuntimeTaskRunStatus,
  AgentRuntimeTimelineResponse,
  EnvironmentResponse,
  SceneSummary,
} from "../common/lib/types";
import { AgentRuntimeChat } from "./agent-runtime-chat";
import { AgentRuntimeDetailPanel } from "./agent-runtime-detail-panel";
import {
  deriveChatMessages,
  deriveCompletionResult,
  deriveTimelineDetailItems,
  deriveWaitingInteraction,
} from "./agent-runtime-view-model";

const TERMINAL_STATUSES = new Set<AgentRuntimeTaskRunStatus>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);

const DEFAULT_INPUTS = `{
  "buyer_id": "U1"
}`;

const POLL_INTERVAL_MS = 3000;

function statusTone(status?: string) {
  switch (status) {
    case "COMPLETED":
    case "DONE":
    case "SUCCEEDED":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "FAILED":
    case "CANCELLED":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    case "WAITING_USER":
    case "UNKNOWN_STATE":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "RUNNING":
      return "border-sky-200 bg-sky-50 text-sky-700";
    default:
      return "border-border bg-muted/40 text-muted-foreground";
  }
}

function parseJsonObject(text: string): Record<string, unknown> {
  if (!text.trim()) return {};
  const parsed = JSON.parse(text) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("输入必须是 JSON 对象。");
  }
  return parsed as Record<string, unknown>;
}

export function AgentRuntimePage() {
  // 表单状态
  const [userGoal, setUserGoal] = useState("造一笔已支付订单");
  const [envCode, setEnvCode] = useState("");
  const [inputsText, setInputsText] = useState(DEFAULT_INPUTS);

  // 数据状态
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [taskRun, setTaskRun] = useState<AgentRuntimeTaskRunResponse | null>(null);
  const [timeline, setTimeline] = useState<AgentRuntimeTimelineResponse | null>(null);

  // UI 状态
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedDetailKey, setSelectedDetailKey] = useState<string | null>(null);

  // 轮询 ref
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const taskRunRef = useRef(taskRun);
  taskRunRef.current = taskRun;

  // 派生数据
  const messages = useMemo(() => deriveChatMessages(taskRun, timeline), [taskRun, timeline]);
  const interaction = useMemo(() => deriveWaitingInteraction(taskRun, timeline), [taskRun, timeline]);
  const detailItems = useMemo(() => deriveTimelineDetailItems(timeline), [timeline]);
  const completionResult = useMemo(() => deriveCompletionResult(taskRun, timeline), [taskRun, timeline]);
  const canCancel = taskRun ? !TERMINAL_STATUSES.has(taskRun.status) : false;

  // 加载环境和场景
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

    listScenes({ status: "PUBLISHED", limit: 200 }).catch((error) => {
      toast.error(error instanceof Error ? error.message : "加载场景失败");
    });
  }, []);

  // 加载 timeline
  const loadTimeline = useCallback(async (taskRunId: string) => {
    const nextTimeline = await getAgentRuntimeTimeline(taskRunId);
    setTimeline(nextTimeline);
  }, []);

  // 刷新
  const refresh = useCallback(
    async (targetTaskRunId?: string) => {
      const taskRunId = targetTaskRunId ?? taskRun?.task_run_id;
      if (!taskRunId) return;
      setRefreshing(true);
      try {
        const nextTaskRun = await getAgentRuntimeTaskRun(taskRunId);
        await loadTimeline(taskRunId);
        setTaskRun(nextTaskRun);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "刷新失败");
      } finally {
        setRefreshing(false);
      }
    },
    [loadTimeline, taskRun?.task_run_id],
  );

  // RUNNING 状态下轮询
  useEffect(() => {
    const shouldPoll = taskRun?.status === "RUNNING";
    if (shouldPoll && taskRun.task_run_id) {
      pollRef.current = setInterval(async () => {
        const current = taskRunRef.current;
        if (!current || TERMINAL_STATUSES.has(current.status) || current.status !== "RUNNING") {
          if (pollRef.current) clearInterval(pollRef.current);
          return;
        }
        try {
          const nextTaskRun = await getAgentRuntimeTaskRun(current.task_run_id);
          await loadTimeline(current.task_run_id);
          setTaskRun(nextTaskRun);
          if (TERMINAL_STATUSES.has(nextTaskRun.status) || nextTaskRun.status !== "RUNNING") {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {
          // 轮询失败不 toast
        }
      }, POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [taskRun?.status, taskRun?.task_run_id, loadTimeline]);

  // 创建并启动
  const handleStart = useCallback(async () => {
    if (!userGoal.trim()) {
      toast.error("请输入造数目标");
      return;
    }
    if (!envCode) {
      toast.error("请选择环境");
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
    try {
      const created = await createAgentRuntimeTaskRun({
        user_goal: userGoal.trim(),
        env_code: envCode,
      });
      setTaskRun(created);
      const started = await startAgentRuntimeTaskRun(created.task_run_id, {
        scene_code: null,
        inputs,
      });
      setTaskRun(started);
      await loadTimeline(started.task_run_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }, [envCode, inputsText, loadTimeline, userGoal]);

  // 取消
  const handleCancel = useCallback(async () => {
    if (!taskRun) return;
    setBusy(true);
    try {
      const cancelled = await cancelAgentRuntimeTaskRun(taskRun.task_run_id);
      setTaskRun(cancelled);
      await loadTimeline(cancelled.task_run_id);
      toast.success("任务已取消");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "取消失败");
    } finally {
      setBusy(false);
    }
  }, [loadTimeline, taskRun]);

  // 选择候选
  const handleSelectCandidate = useCallback(
    async (candidate: AgentRuntimeSceneCandidate, approved: boolean) => {
      if (!taskRun) return;
      let inputs: Record<string, unknown>;
      try {
        inputs = parseJsonObject(inputsText);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "输入不是合法 JSON");
        return;
      }

      setBusy(true);
      try {
        const replied = await replyAgentRuntimeTaskRun(taskRun.task_run_id, {
          reply_type: "SELECT_SCENE",
          payload: {
            scene_code: candidate.scene_code,
            approved,
            inputs,
          },
        });
        setTaskRun(replied);
        await loadTimeline(replied.task_run_id);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "选择候选失败");
      } finally {
        setBusy(false);
      }
    },
    [inputsText, loadTimeline, taskRun],
  );

  // 批准
  const handleApprove = useCallback(async () => {
    if (!taskRun) return;
    let inputs: Record<string, unknown>;
    try {
      inputs = parseJsonObject(inputsText);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "输入不是合法 JSON");
      return;
    }

    setBusy(true);
    try {
      const replied = await replyAgentRuntimeTaskRun(taskRun.task_run_id, {
        reply_type: "APPROVE",
        payload: { inputs },
      });
      setTaskRun(replied);
      await loadTimeline(replied.task_run_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "审批失败");
    } finally {
      setBusy(false);
    }
  }, [inputsText, loadTimeline, taskRun]);

  // 补录 scene_code
  const handleSupplySceneCode = useCallback(
    async (sceneCode: string) => {
      if (!taskRun || !sceneCode.trim()) {
        toast.error("请输入 scene_code");
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
      try {
        const replied = await replyAgentRuntimeTaskRun(taskRun.task_run_id, {
          reply_type: "SUPPLY_SCENE_CODE",
          payload: {
            scene_code: sceneCode.trim(),
            inputs,
          },
        });
        setTaskRun(replied);
        await loadTimeline(replied.task_run_id);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "补录 scene_code 失败");
      } finally {
        setBusy(false);
      }
    },
    [inputsText, loadTimeline, taskRun],
  );

  // 补参
  const handleSupplyInput = useCallback(
    async (inputs: Record<string, unknown>) => {
      if (!taskRun) return;
      let existingInputs: Record<string, unknown>;
      try {
        existingInputs = parseJsonObject(inputsText);
      } catch {
        existingInputs = {};
      }

      setBusy(true);
      try {
        const replied = await replyAgentRuntimeTaskRun(taskRun.task_run_id, {
          reply_type: "SUPPLY_INPUT",
          payload: { inputs: { ...existingInputs, ...inputs } },
        });
        setTaskRun(replied);
        await loadTimeline(replied.task_run_id);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "补充输入失败");
      } finally {
        setBusy(false);
      }
    },
    [inputsText, loadTimeline, taskRun],
  );

  // 确认未知状态
  const handleConfirmUnknownState = useCallback(async () => {
    if (!taskRun) return;
    setBusy(true);
    try {
      const replied = await replyAgentRuntimeTaskRun(taskRun.task_run_id, {
        reply_type: "CONFIRM_UNKNOWN_STATE",
        payload: { message: "确认停止" },
      });
      setTaskRun(replied);
      await loadTimeline(replied.task_run_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "确认失败");
    } finally {
      setBusy(false);
    }
  }, [loadTimeline, taskRun]);

  // 查看执行尝试
  const handleViewAttempts = useCallback(() => {
    setDetailOpen(true);
    const attemptItem = detailItems.find((item) => item.kind === "attempt");
    if (attemptItem) {
      setSelectedDetailKey(attemptItem.key);
    }
  }, [detailItems]);

  // 重置
  const reset = useCallback(() => {
    setTaskRun(null);
    setTimeline(null);
    setSelectedDetailKey(null);
  }, []);

  const hasTaskRun = !!taskRun;

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* 顶部轻量栏 */}
      <header className="flex shrink-0 items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <ShieldCheckIcon className="size-5 text-primary" />
          <h1 className="text-base font-semibold tracking-tight">GDP Agent</h1>
          <Badge variant="outline" className={cn("gap-1 rounded-md text-xs", statusTone(taskRun?.status))}>
            {taskRun?.status === "RUNNING" ? <Loader2Icon className="size-3 animate-spin" /> : null}
            {taskRun?.status ?? "IDLE"}
          </Badge>
          {hasTaskRun ? (
            <span className="text-xs text-muted-foreground font-mono">{taskRun.task_run_id.slice(0, 8)}</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {hasTaskRun ? (
            <>
              {/* 环境选择（运行时禁用） */}
              <Select value={envCode} onValueChange={setEnvCode} disabled={hasTaskRun}>
                <SelectTrigger className="h-8 w-[140px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {environments.map((env) => (
                    <SelectItem key={env.envCode} value={env.envCode}>
                      {env.envName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {canCancel ? (
                <Button variant="outline" size="sm" onClick={handleCancel} disabled={busy}>
                  <BanIcon className="mr-1 size-3.5" />
                  取消
                </Button>
              ) : null}

              <Button
                variant="outline"
                size="sm"
                onClick={() => void refresh()}
                disabled={refreshing}
              >
                <RefreshCwIcon className={cn("mr-1 size-3.5", refreshing ? "animate-spin" : "")} />
                刷新
              </Button>
            </>
          ) : (
            <Select value={envCode} onValueChange={setEnvCode}>
              <SelectTrigger className="h-8 w-[140px] text-xs">
                <SelectValue placeholder="选择环境" />
              </SelectTrigger>
              <SelectContent>
                {environments.map((env) => (
                  <SelectItem key={env.envCode} value={env.envCode}>
                    {env.envName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {hasTaskRun ? (
            <Button variant="outline" size="sm" onClick={reset} disabled={busy}>
              <RotateCcwIcon className="mr-1 size-3.5" />
              重置
            </Button>
          ) : null}

          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={() => setDetailOpen((prev) => !prev)}
          >
            <PanelRightIcon className={cn("size-4", detailOpen ? "text-primary" : "")} />
          </Button>
        </div>
      </header>

      {/* 主体区域 */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <AgentRuntimeChat
          messages={messages}
          interaction={interaction}
          completionResult={completionResult}
          busy={busy}
          canStart={!busy && !!userGoal.trim() && !!envCode}
          onStart={handleStart}
          onSelectCandidate={handleSelectCandidate}
          onApprove={handleApprove}
          onCancel={handleCancel}
          onSupplySceneCode={handleSupplySceneCode}
          onSupplyInput={handleSupplyInput}
          onConfirmUnknownState={handleConfirmUnknownState}
          onViewAttempts={handleViewAttempts}
          userGoal={userGoal}
          onUserGoalChange={setUserGoal}
        />

        <AgentRuntimeDetailPanel
          taskRun={taskRun}
          items={detailItems}
          selectedKey={selectedDetailKey}
          onSelect={setSelectedDetailKey}
          open={detailOpen}
          onClose={() => setDetailOpen(false)}
        />
      </div>
    </div>
  );
}
