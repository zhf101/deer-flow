"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ClockIcon,
  Loader2Icon,
  RefreshCwIcon,
  XCircleIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

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
import { cn } from "@/lib/utils";

import { listSceneRuns, listScenes } from "../common/lib/api";
import type { SceneRunSummary, SceneSummary } from "../common/lib/types";

interface SceneRunHistoryProps {
  onViewRun?: (runId: string, sceneCode: string) => void;
}

export function SceneRunHistory({ onViewRun }: SceneRunHistoryProps) {
  const [runs, setRuns] = useState<SceneRunSummary[]>([]);
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [sceneCode, setSceneCode] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const limit = 20;

  // 加载场景列表用于筛选下拉
  useEffect(() => {
    listScenes({ limit: 200, offset: 0 })
      .then(setScenes)
      .catch(() => { /* 忽略 */ });
  }, []);

  const loadRuns = useCallback(async (reset = false) => {
    setLoading(true);
    try {
      const offset = reset ? 0 : page * limit;
      const effectiveSceneCode = sceneCode === "__all__" ? "" : sceneCode;
      const effectiveStatus = status === "__all__" ? "" : status;
      const result = await listSceneRuns({
        sceneCode: effectiveSceneCode || undefined,
        status: effectiveStatus || undefined,
        limit,
        offset,
      });
      if (reset) {
        setRuns(result);
      } else {
        setRuns((prev) => [...prev, ...result]);
      }
      setHasMore(result.length === limit);
      if (reset) setPage(1);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载执行记录失败");
    } finally {
      setLoading(false);
    }
  }, [sceneCode, status, page]);

  // 筛选变化时重置加载
  useEffect(() => {
    void loadRuns(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneCode, status]);

  const handleLoadMore = () => {
    setPage((p) => p + 1);
    void loadRuns(false);
  };

  return (
    <div className="flex h-full flex-col bg-background">
      {/* 筛选栏 */}
      <header className="shrink-0 border-b bg-card/50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <h1 className="text-sm font-semibold mr-4">执行历史</h1>
          <Select value={sceneCode} onValueChange={setSceneCode}>
            <SelectTrigger className="h-7 w-[180px] text-xs">
              <SelectValue placeholder="全部场景" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__" className="text-xs">全部场景</SelectItem>
              {scenes.map((s) => (
                <SelectItem key={s.sceneCode} value={s.sceneCode} className="text-xs">
                  {s.sceneName} ({s.sceneCode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-7 w-[120px] text-xs">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__" className="text-xs">全部状态</SelectItem>
              <SelectItem value="SUCCESS" className="text-xs">成功</SelectItem>
              <SelectItem value="FAILED" className="text-xs">失败</SelectItem>
              <SelectItem value="PARTIAL" className="text-xs">部分成功</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => void loadRuns(true)}
            disabled={loading}
            title="刷新"
          >
            <RefreshCwIcon className={cn("size-3.5", loading && "animate-spin")} />
          </Button>
        </div>
      </header>

      {/* 列表 */}
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-2">
          {runs.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <ClockIcon className="size-8 mb-2 opacity-20" />
              <p className="text-sm">暂无执行记录</p>
            </div>
          )}
          {runs.map((run) => (
            <RunCard
              key={run.runId}
              run={run}
              onClick={() => onViewRun?.(run.runId, run.sceneCode)}
            />
          ))}
          {hasMore && (
            <div className="flex justify-center pt-2 pb-4">
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadMore}
                disabled={loading}
                className="gap-1.5 text-xs"
              >
                {loading ? <Loader2Icon className="size-3 animate-spin" /> : <ChevronDownIcon className="size-3" />}
                加载更多
              </Button>
            </div>
          )}
          {loading && runs.length === 0 && (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin mr-2" />
              <span className="text-xs">加载中...</span>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

/* ── 执行记录卡片 ── */

function RunCard({ run, onClick }: { run: SceneRunSummary; onClick: () => void }) {
  const StatusIcon =
    run.status === "SUCCESS"
      ? CheckCircle2Icon
      : run.status === "FAILED"
        ? XCircleIcon
        : AlertTriangleIcon;

  const statusColor =
    run.status === "SUCCESS"
      ? "text-emerald-600 dark:text-emerald-400"
      : run.status === "FAILED"
        ? "text-red-600 dark:text-red-400"
        : "text-amber-600 dark:text-amber-400";

  const borderColor =
    run.status === "SUCCESS"
      ? "border-l-emerald-500"
      : run.status === "FAILED"
        ? "border-l-red-500"
        : "border-l-amber-500";

  const inputsText = Object.keys(run.inputs).length > 0
    ? JSON.stringify(run.inputs)
    : "";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-lg border border-l-4 bg-card p-3 transition-colors",
        "hover:bg-muted/50 hover:shadow-sm cursor-pointer",
        borderColor,
      )}
    >
      {/* 第一行：状态 + 场景 + 版本 + 环境 + 耗时 */}
      <div className="flex items-center gap-2 flex-wrap">
        <StatusIcon className={cn("size-4 shrink-0", statusColor)} />
        <span className="text-sm font-semibold truncate">{run.sceneCode}</span>
        <Badge variant="outline" className="rounded text-[9px] px-1 py-0">v{run.versionNo}</Badge>
        <Badge variant="secondary" className="rounded text-[9px] px-1 py-0">{run.envCode}</Badge>
        <span className="text-[11px] text-muted-foreground flex items-center gap-1">
          <ClockIcon className="size-3" />
          {formatDuration(run.durationMs)}
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {formatDateTime(run.startedAt)}
        </span>
      </div>

      {/* 第二行：步骤统计 + 入参 */}
      <div className="mt-1.5 flex items-center gap-3 text-[11px] text-muted-foreground">
        <span>
          步骤 <span className="font-medium text-foreground">{run.successCount}/{run.stepCount}</span>
          {run.failedCount > 0 && (
            <span className="text-red-500 ml-1">失败 {run.failedCount}</span>
          )}
        </span>
        {inputsText && (
          <span className="truncate font-mono text-[10px] opacity-70">
            入参: {inputsText}
          </span>
        )}
      </div>

      {/* 错误信息 */}
      {run.errors.length > 0 && (
        <div className="mt-1.5 text-[11px] text-red-600 dark:text-red-400 truncate">
          {run.errors[0]}
        </div>
      )}
    </button>
  );
}

/* ── 工具函数 ── */

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms)) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatDateTime(value: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}
