import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ClockIcon,
  DatabaseIcon,
  FileJsonIcon,
  SendIcon,
  ServerIcon,
  XCircleIcon,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import type { ExecutionResult, StepResult } from "../common/lib/types";

// ── 工具函数 ─────────────────────────────────────────────────────────────

type JsonRecord = Record<string, unknown>;

function unknownToRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function textValue(value: unknown): string {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "object") return jsonText(value);
  return String(value);
}

function jsonText(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "无法序列化";
  }
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms)) return "-";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

// ── 通用子组件 ──────────────────────────────────────────────────────────

function InfoItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("text-xs font-medium truncate", mono && "font-mono")}>{value}</div>
    </div>
  );
}

function CollapsibleJson({
  title,
  value,
  defaultOpen = false,
}: {
  title: string;
  value: unknown;
  defaultOpen?: boolean;
}) {
  const isEmpty =
    value === null ||
    value === undefined ||
    (typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0);

  return (
    <details open={defaultOpen} className="group">
      <summary className="flex cursor-pointer select-none items-center gap-2 py-1 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground">
        <span className="text-[10px] text-muted-foreground/50 transition-transform group-open:rotate-90">
          ▶
        </span>
        {title}
        {isEmpty && <span className="text-[10px] font-normal text-muted-foreground/50">(空)</span>}
      </summary>
      <div className="mt-1">
        <pre
          className="overflow-auto whitespace-pre-wrap break-all rounded-md border border-border/50 bg-muted/40 p-3 font-mono text-[11px] leading-relaxed"
          style={{ maxHeight: "300px" }}
        >
          {jsonText(value)}
        </pre>
      </div>
    </details>
  );
}

// ── 步骤状态 Badge ──────────────────────────────────────────────────────

function StepStatusBadge({ status }: { status: StepResult["status"] }) {
  const config = {
    SUCCESS: {
      label: "成功",
      icon: CheckCircle2Icon,
      className:
        "border-emerald-200 bg-emerald-50 text-emerald-700",
    },
    FAILED: {
      label: "失败",
      icon: XCircleIcon,
      className: "border-red-200 bg-red-50 text-red-700",
    },
    SKIPPED: {
      label: "跳过",
      icon: AlertTriangleIcon,
      className: "border-muted bg-muted text-muted-foreground",
    },
  }[status];
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={cn("gap-0.5 rounded px-1 py-0 text-[9px]", config.className)}>
      <Icon className="size-2.5" />
      {config.label}
    </Badge>
  );
}

// ── 步骤详情面板 ────────────────────────────────────────────────────────

function SceneStepDetail({ step }: { step: StepResult }) {
  const raw = unknownToRecord(step.rawResponse);
  const httpRequest = unknownToRecord(raw.request);
  const httpResponse = unknownToRecord(raw.response);
  const sqlColumns = Array.isArray(raw.columns) ? raw.columns : [];
  const sqlRows = Array.isArray(raw.rows) ? raw.rows : [];

  const statusBorderColor =
    step.status === "SUCCESS"
      ? "border-l-emerald-500"
      : step.status === "FAILED"
        ? "border-l-red-500"
        : "border-l-muted";

  return (
    <section className={cn("overflow-hidden rounded-lg border border-l-4 bg-card", statusBorderColor)}>
      {/* 步骤 header */}
      <div className="border-b bg-muted/20 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="min-w-0 truncate text-xs font-semibold">{step.stepName ?? step.stepId}</h3>
          <Badge variant="outline" className="rounded text-[10px] px-1.5 py-0">
            {step.type}
          </Badge>
          <StepStatusBadge status={step.status} />
          {step.statusCode ? (
            <Badge variant="outline" className="rounded text-[10px] px-1.5 py-0">
              HTTP {step.statusCode}
            </Badge>
          ) : null}
          <span className="ml-auto flex items-center gap-1 text-[11px] text-muted-foreground">
            <ClockIcon className="size-3" />
            {formatDuration(step.durationMs)}
          </span>
        </div>
        {step.error ? (
          <div className="mt-1.5 rounded px-2 py-1 text-xs text-red-600 bg-red-50">{step.error}</div>
        ) : null}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="p-0">
        <TabsList variant="line" className="h-auto w-full gap-0 rounded-none border-b px-3 py-0">
          <TabsTrigger value="overview" className="text-[11px] gap-1">
            <FileJsonIcon className="size-3" />
            概览
          </TabsTrigger>
          {step.type === "HTTP" ? (
            <>
              <TabsTrigger value="request" className="text-[11px] gap-1">
                <SendIcon className="size-3" />
                请求
              </TabsTrigger>
              <TabsTrigger value="response" className="text-[11px] gap-1">
                <ServerIcon className="size-3" />
                响应
              </TabsTrigger>
            </>
          ) : null}
          {step.type === "SQL" ? (
            <TabsTrigger value="sql" className="text-[11px] gap-1">
              <DatabaseIcon className="size-3" />
              SQL
            </TabsTrigger>
          ) : null}
        </TabsList>

        {/* 概览 */}
        <TabsContent value="overview" className="m-0 space-y-3 p-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <InfoItem label="开始时间" value={step.startedAt ? new Date(step.startedAt).toLocaleString() : "-"} />
            <InfoItem label="执行耗时" value={formatDuration(step.durationMs)} />
          </div>
          {Object.keys(step.outputs).length > 0 ? (
            <div>
              <div className="mb-1.5 text-[10px] font-semibold text-muted-foreground">输出变量</div>
              <div className="overflow-hidden rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/40">
                      <th className="w-[40%] px-2 py-1 text-left text-[10px] font-medium text-muted-foreground">
                        变量名
                      </th>
                      <th className="px-2 py-1 text-left text-[10px] font-medium text-muted-foreground">值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(step.outputs).map(([key, val]) => (
                      <tr key={key} className="border-b last:border-b-0">
                        <td className="px-2 py-1 font-mono text-[11px]">{key}</td>
                        <td className="break-all px-2 py-1 font-mono text-[11px] text-muted-foreground">
                          {textValue(val)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="py-1 text-xs italic text-muted-foreground">该步骤无输出变量</p>
          )}
        </TabsContent>

        {/* HTTP 请求 */}
        {step.type === "HTTP" ? (
          <TabsContent value="request" className="m-0 space-y-2 p-3">
            <div className="grid grid-cols-3 gap-2 text-xs">
              <InfoItem label="方法" value={textValue(httpRequest.method)} mono />
              <InfoItem label="Body 类型" value={textValue(httpRequest.bodyType)} />
              <InfoItem label="URL" value={textValue(httpRequest.url)} mono />
            </div>
            <CollapsibleJson title="请求头" value={httpRequest.headers ?? {}} />
            <CollapsibleJson title="查询参数" value={httpRequest.query ?? {}} />
            <CollapsibleJson title="请求体" value={httpRequest.body ?? null} defaultOpen />
          </TabsContent>
        ) : null}

        {/* HTTP 响应 */}
        {step.type === "HTTP" ? (
          <TabsContent value="response" className="m-0 space-y-3 p-3">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  状态码
                </span>
                {(() => {
                  const code = httpResponse.statusCode;
                  const codeNum = typeof code === "number" ? code : parseInt(String(code), 10);
                  const isSuccess = codeNum >= 200 && codeNum < 300;
                  return (
                    <span
                      className={cn(
                        "text-xl font-bold tabular-nums",
                        isSuccess ? "text-emerald-600" : "text-red-600",
                        !code && "text-muted-foreground",
                      )}
                    >
                      {textValue(code)}
                    </span>
                  );
                })()}
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <ClockIcon className="size-3" />
                <span>
                  {httpResponse.elapsedMs === undefined
                    ? "-"
                    : formatDuration(Number(httpResponse.elapsedMs))}
                </span>
              </div>
            </div>
            <CollapsibleJson title="响应体" value={httpResponse.body ?? null} defaultOpen />
            <CollapsibleJson title="响应头" value={httpResponse.headers ?? {}} />
            <CollapsibleJson title="Cookie" value={httpResponse.cookies ?? []} />
          </TabsContent>
        ) : null}

        {/* SQL */}
        {step.type === "SQL" ? (
          <TabsContent value="sql" className="m-0 space-y-2 p-3">
            <div className="grid grid-cols-4 gap-2 text-xs">
              <InfoItem label="数据库" value={textValue(raw.dbType)} />
              <InfoItem label="操作" value={textValue(raw.operation)} />
              <InfoItem label="影响行数" value={textValue(raw.affectedRows)} />
              <InfoItem
                label="耗时"
                value={raw.elapsedMs === undefined ? "-" : formatDuration(Number(raw.elapsedMs))}
              />
            </div>
            <CollapsibleJson title="结果字段" value={sqlColumns} />
            <CollapsibleJson title="首行结果" value={raw.row ?? null} defaultOpen />
            <CollapsibleJson title="结果集" value={sqlRows} />
            <CollapsibleJson title="新增记录ID" value={raw.generatedKeys ?? []} />
            <CollapsibleJson title="警告" value={raw.warnings ?? []} />
          </TabsContent>
        ) : null}
      </Tabs>
    </section>
  );
}

// ── 场景运行详情主组件 ──────────────────────────────────────────────────

export function AgentRuntimeSceneRunDetail({ result }: { result: ExecutionResult }) {
  const orderedSteps = [...result.stepResults].sort(
    (a, b) => (a.timelineOrder ?? a.stepOrder ?? 0) - (b.timelineOrder ?? b.stepOrder ?? 0),
  );
  const [selectedStepId, setSelectedStepId] = useState<string | null>(orderedSteps[0]?.stepId ?? null);
  const selectedStep = orderedSteps.find((s) => s.stepId === selectedStepId) ?? null;

  const successCount = orderedSteps.filter((s) => s.status === "SUCCESS").length;
  const failedCount = orderedSteps.filter((s) => s.status === "FAILED").length;

  return (
    <div className="space-y-2">
      {/* 摘要 */}
      <div className="flex items-center gap-2 rounded-md border bg-muted/20 px-3 py-2 text-xs">
        <span className="font-medium">{result.sceneCode}</span>
        <Badge variant="outline" className="text-[10px]">
          v{result.versionNo}
        </Badge>
        <span className="text-muted-foreground">{result.envCode}</span>
        <span className="ml-auto flex items-center gap-1 text-muted-foreground">
          <ClockIcon className="size-3" />
          {formatDuration(result.durationMs)}
        </span>
        <span className="text-emerald-600">{successCount} 成功</span>
        {failedCount > 0 ? <span className="text-red-600">{failedCount} 失败</span> : null}
      </div>

      {/* 步骤列表 */}
      <div className="space-y-1">
        {orderedSteps.map((step, index) => {
          const isSelected = step.stepId === selectedStepId;
          const StatusIcon =
            step.status === "SUCCESS" ? CheckCircle2Icon : step.status === "FAILED" ? XCircleIcon : AlertTriangleIcon;
          return (
            <button
              key={step.stepId}
              type="button"
              onClick={() => setSelectedStepId(step.stepId)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left transition-colors",
                isSelected ? "border-primary bg-primary/5" : "bg-background hover:bg-muted/50",
              )}
            >
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[9px] font-bold">
                {index + 1}
              </span>
              <StatusIcon
                className={cn(
                  "size-3.5 shrink-0",
                  step.status === "SUCCESS"
                    ? "text-emerald-500"
                    : step.status === "FAILED"
                      ? "text-red-500"
                      : "text-muted-foreground",
                )}
              />
              <span className="min-w-0 flex-1 truncate text-xs font-medium">{step.stepName ?? step.stepId}</span>
              <Badge variant="outline" className="shrink-0 text-[9px] px-1 py-0">
                {step.type}
              </Badge>
              <span className="shrink-0 text-[10px] text-muted-foreground">{formatDuration(step.durationMs)}</span>
            </button>
          );
        })}
      </div>

      {/* 选中步骤详情 */}
      {selectedStep ? <SceneStepDetail step={selectedStep} /> : null}
    </div>
  );
}
