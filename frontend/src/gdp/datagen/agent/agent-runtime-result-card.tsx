import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronUpIcon,
  ExternalLinkIcon,
  FileJsonIcon,
  XCircleIcon,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { CompletionResult } from "./agent-runtime-view-model";

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN");
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function AgentRuntimeResultCard({
  result,
  onViewDetails,
}: {
  result: CompletionResult;
  onViewDetails?: () => void;
}) {
  const [showResponse, setShowResponse] = useState(false);
  const [showFacts, setShowFacts] = useState(false);

  const isSuccess = result.verdict_type === "DONE";
  const isFailed = result.verdict_type === "FAILED";

  const Icon = isSuccess ? CheckCircle2Icon : isFailed ? XCircleIcon : AlertTriangleIcon;
  const toneClass = isSuccess
    ? "border-emerald-200 bg-emerald-50"
    : isFailed
      ? "border-destructive/30 bg-destructive/10"
      : "border-amber-200 bg-amber-50";
  const iconClass = isSuccess
    ? "text-emerald-600"
    : isFailed
      ? "text-destructive"
      : "text-amber-600";
  const titleText = isSuccess ? "造数成功" : isFailed ? "造数失败" : "结果未知";

  const passedCount = result.facts.filter((f) => f.passed).length;
  const totalCount = result.facts.length;
  const hasResponse = Object.keys(result.response_preview).length > 0;

  return (
    <div className={cn("overflow-hidden rounded-lg border", toneClass)}>
      {/* 头部 */}
      <div className="flex items-center gap-3 px-4 py-3">
        <Icon className={cn("size-5", iconClass)} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{titleText}</div>
          <div className="text-xs text-muted-foreground">{result.reason}</div>
        </div>
        <div className="text-right text-[11px] text-muted-foreground">
          {result.scene_code ? (
            <div className="font-mono">{result.scene_code}</div>
          ) : null}
          <div>{formatTime(result.finished_at)}</div>
        </div>
      </div>

      {onViewDetails ? (
        <div className="border-t px-4 py-2">
          <Button variant="outline" size="sm" className="w-full text-xs" onClick={onViewDetails}>
            <ExternalLinkIcon className="mr-1.5 size-3.5" />
            查看执行详情
          </Button>
        </div>
      ) : null}

      {/* 事实摘要 */}
      {totalCount > 0 ? (
        <div className="border-t px-4 py-2">
          <button
            type="button"
            onClick={() => setShowFacts((prev) => !prev)}
            className="flex w-full items-center justify-between text-xs"
          >
            <span className="text-muted-foreground">
              验证事实：
              <span className={cn("font-medium", passedCount === totalCount ? "text-emerald-600" : "text-amber-600")}>
                {passedCount}/{totalCount} 通过
              </span>
            </span>
            {showFacts ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />}
          </button>

          {showFacts ? (
            <div className="mt-2 space-y-1.5">
              {result.facts.map((fact, index) => (
                <div
                  key={`${fact.subject}-${index}`}
                  className={cn(
                    "flex items-start gap-2 rounded-md border px-3 py-2 text-xs",
                    fact.passed ? "border-emerald-100 bg-emerald-50/50" : "border-destructive/20 bg-destructive/5",
                  )}
                >
                  {fact.passed ? (
                    <CheckCircle2Icon className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />
                  ) : (
                    <XCircleIcon className="mt-0.5 size-3.5 shrink-0 text-destructive" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{fact.subject}</div>
                    <div className="mt-0.5 text-muted-foreground">
                      期望：{formatValue(fact.expected)} / 实际：{formatValue(fact.actual)}
                    </div>
                    {fact.detail ? (
                      <div className="mt-0.5 text-muted-foreground/70">{fact.detail}</div>
                    ) : null}
                  </div>
                </div>
              ))}
              {result.missing_facts.length > 0 ? (
                <div className="mt-1 text-xs text-amber-600">
                  缺失事实：{result.missing_facts.join("，")}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* 响应数据 */}
      {hasResponse ? (
        <div className="border-t px-4 py-2">
          <button
            type="button"
            onClick={() => setShowResponse((prev) => !prev)}
            className="flex w-full items-center justify-between text-xs"
          >
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <FileJsonIcon className="size-3.5" />
              响应数据
            </span>
            {showResponse ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />}
          </button>

          {showResponse ? (
            <pre className="mt-2 max-h-[300px] overflow-auto rounded-md border bg-background p-3 text-xs leading-5">
              {formatJson(result.response_preview)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
