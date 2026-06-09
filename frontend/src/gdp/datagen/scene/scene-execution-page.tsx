"use client";

import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronLeftIcon,
  CircleDashedIcon,
  ClockIcon,
  DatabaseIcon,
  FileJsonIcon,
  Loader2Icon,
  PlayIcon,
  SendIcon,
  ServerIcon,
  XCircleIcon,
  ZapIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { getScene, getSceneRun, listEnvironments, runScene } from "../common/lib/api";
import type {
  EnvironmentResponse,
  ExecutionResult,
  InputFieldDefinition,
  SceneDefinition,
  StepResult,
} from "../common/lib/types";
import { formatUnknownValue } from "../common/lib/value-utils";

interface SceneExecutionPageProps {
  sceneCode: string;
  runId?: string;
  onBack?: () => void;
}

type JsonRecord = Record<string, unknown>;
type TimelineStep = StepResult & { pending?: boolean };

export function SceneExecutionPage({ sceneCode, runId, onBack }: SceneExecutionPageProps) {
  const [scene, setScene] = useState<SceneDefinition | null>(null);
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [envCode, setEnvCode] = useState("");
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [submittedInputs, setSubmittedInputs] = useState<Record<string, unknown>>({});

  const readOnly = !!runId;

  useEffect(() => {
    let active = true;
    setLoading(true);

    if (runId) {
      // 历史记录查看模式：直接加载执行结果
      getSceneRun(runId)
        .then((runResult) => {
          if (!active) return;
          setResult(runResult);
          setSelectedStepId(runResult.stepResults[0]?.stepId ?? null);
          setSubmittedInputs(runResult.inputs);
          setEnvCode(runResult.envCode);
          // 加载场景定义用于步骤列表展示
          return getScene(sceneCode);
        })
        .then((sceneData) => {
          if (!active || !sceneData) return;
          setScene(sceneData);
        })
        .catch((error) => {
          toast.error(error instanceof Error ? error.message : "加载执行记录失败");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    } else {
      // 执行模式：加载场景和环境
      Promise.all([getScene(sceneCode), listEnvironments()])
        .then(([sceneData, envs]) => {
          if (!active) return;
          const enabledEnvs = envs.filter((env) => env.status === "ENABLED");
          setScene(sceneData);
          setEnvironments(enabledEnvs);
          setEnvCode((current) => (current ? current : (enabledEnvs[0]?.envCode ?? "")));
          setInputs(buildDefaultInputs(sceneData.inputSchema));
        })
        .catch((error) => {
          toast.error(error instanceof Error ? error.message : "加载场景执行信息失败");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }

    return () => {
      active = false;
    };
  }, [sceneCode, runId]);

  const inputFields = useMemo(
    () => (scene?.inputSchema ?? []).filter((field) => field.name !== "env"),
    [scene?.inputSchema],
  );

  const selectedStep = useMemo(
    () => result?.stepResults.find((step) => step.stepId === selectedStepId) ?? result?.stepResults[0] ?? null,
    [result?.stepResults, selectedStepId],
  );

  const resultByStepId = useMemo(() => {
    return new Map((result?.stepResults ?? []).map((step) => [step.stepId, step]));
  }, [result?.stepResults]);

  const orderedSteps = useMemo(() => {
    return (scene?.steps ?? []).map((step, index) => {
      const executed = resultByStepId.get(step.stepId);
      return executed ?? stepToPendingResult(step, step.executionOrder ?? index + 1);
    });
  }, [resultByStepId, scene?.steps]);

  const handleRun = useCallback(async () => {
    if (!envCode) {
      toast.error("请先选择执行环境");
      return;
    }
    setRunning(true);
    setResult(null);
    setSelectedStepId(null);
    setSubmittedInputs({ ...inputs });
    try {
      const next = await runScene(sceneCode, { envCode, inputs });
      const detail = next.runId ? await getSceneRun(next.runId) : next;
      setResult(detail);
      setSelectedStepId(detail.stepResults[0]?.stepId ?? null);
      if (detail.status === "SUCCESS") {
        toast.success("场景执行成功");
      } else {
        toast.error(detail.errors[0] ?? "场景执行未完全成功");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "场景执行请求失败");
    } finally {
      setRunning(false);
    }
  }, [envCode, inputs, sceneCode]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        <Loader2Icon className="mr-2 size-4 animate-spin" />
        加载中...
      </div>
    );
  }

  if (!scene) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        场景不存在或加载失败
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      {/* ── Header ── */}
      <header className="shrink-0 border-b bg-card/50 px-6 py-3">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {onBack && (
                <Button variant="ghost" size="icon-sm" onClick={onBack} title="返回">
                  <ChevronLeftIcon className="size-4" />
                </Button>
              )}
              <h1 className="truncate text-lg font-semibold tracking-tight">{scene.sceneName}</h1>
              <Badge variant={scene.status === "PUBLISHED" ? "default" : "secondary"} className="rounded-md text-[10px]">
                {scene.status}
              </Badge>
              {result && <ExecutionStatusIndicator status={result.status} />}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              <span className="font-mono">{scene.sceneCode}</span>
              <span className="text-border">|</span>
              <span>{scene.sceneType?.trim() ? scene.sceneType : "未分类"}</span>
              <span className="text-border">|</span>
              <span>{scene.steps.length} 个节点</span>
              {result?.runId && (
                <>
                  <span className="text-border">|</span>
                  <span className="font-mono">run: {result.runId}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {!readOnly && (
              <>
                <Select value={envCode} onValueChange={setEnvCode}>
                  <SelectTrigger className="h-8 w-[170px] text-xs">
                    <SelectValue placeholder="执行环境" />
                  </SelectTrigger>
                  <SelectContent>
                    {environments.map((env) => (
                      <SelectItem key={env.envCode} value={env.envCode}>
                        {env.envName} ({env.envCode})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  onClick={handleRun}
                  disabled={running || !envCode}
                  size="sm"
                  className={cn(
                    "gap-1.5",
                    result?.status === "SUCCESS" && "bg-emerald-600 hover:bg-emerald-700",
                    result?.status === "FAILED" && "bg-red-600 hover:bg-red-700",
                  )}
                >
                  {running ? <Loader2Icon className="size-3.5 animate-spin" /> : <PlayIcon className="size-3.5" />}
                  {running ? "执行中" : "执行"}
                </Button>
              </>
            )}
            {readOnly && (
              <Badge variant="outline" className="text-[10px]">
                历史记录
              </Badge>
            )}
          </div>
        </div>
      </header>

      {/* ── 主体：上下结构 ── */}
      <div className="flex min-h-0 flex-1 flex-col">
        {/* ── 上：入参/响应 JSON 报文 ── */}
        <div className="shrink-0 border-b bg-muted/10 px-4 py-2 space-y-1.5">
          <InputJsonSection
            inputFields={inputFields}
            inputs={inputs}
            submittedInputs={submittedInputs}
            envCode={envCode}
            hasResult={!!result}
            onChange={(name, value) => setInputs((c) => ({ ...c, [name]: value }))}
          />
          {result && (
            <ResponseJsonSection result={result} />
          )}
        </div>

        {/* ── 下：左侧步骤 + 右侧详情 ── */}
        <div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)]">
          {/* 左侧步骤列表 */}
          <aside className="min-h-0 border-r bg-muted/20">
            <ScrollArea className="h-full">
              <div className="p-2.5">
                <h2 className="mb-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-1">
                  步骤
                </h2>
                <div className="relative">
                  {orderedSteps.map((step, index) => (
                    <StepTimelineItem
                      key={step.stepId}
                      step={step}
                      stepIndex={index + 1}
                      isLast={index === orderedSteps.length - 1}
                      selected={selectedStep?.stepId === step.stepId}
                      onSelect={() => setSelectedStepId(step.stepId)}
                    />
                  ))}
                </div>
              </div>
            </ScrollArea>
          </aside>

          {/* 右侧详情 */}
          <main className="min-h-0 min-w-0">
            <ScrollArea className="h-full">
              <div className="p-4 space-y-4">
                {/* 错误信息 */}
                {result?.errors && result.errors.length > 0 && (
                  <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/20 dark:border-red-900/30 p-3 space-y-1">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-red-700 dark:text-red-400">
                      <XCircleIcon className="size-3.5" />
                      执行错误
                    </div>
                    {result.errors.map((err, i) => (
                      <p key={i} className="text-xs text-red-600 dark:text-red-400/80 pl-5">{err}</p>
                    ))}
                  </div>
                )}

                {/* 步骤详情 */}
                {selectedStep ? (
                  <StepDetailPanel step={selectedStep} />
                ) : (
                  <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-16 text-muted-foreground">
                    <ZapIcon className="size-10 mb-3 opacity-15" />
                    <p className="text-sm font-medium">点击执行开始运行</p>
                    <p className="text-xs mt-1 opacity-70">执行后可在此查看每个步骤的详细结果</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          </main>
        </div>
      </div>
    </div>
  );
}

/* ── 入参控件 ── */

function InputFieldControl({
  field,
  value,
  onChange,
}: {
  field: InputFieldDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const label = field.label ?? field.name;

  if (field.type === "boolean") {
    return (
      <label className="flex items-center justify-between gap-2 rounded-md border bg-card px-2.5 py-1.5 text-xs cursor-pointer hover:bg-muted/50 transition-colors">
        <span className="truncate">
          {label}
          {field.required && <span className="ml-0.5 text-destructive">*</span>}
        </span>
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
          className="size-3.5 rounded border-input accent-primary"
        />
      </label>
    );
  }

  return (
    <div className="space-y-1">
      <label className="text-[11px] font-medium text-muted-foreground">
        {label}
        {field.required && <span className="ml-0.5 text-destructive">*</span>}
      </label>
      <Input
        type={field.type === "number" ? "number" : "text"}
        value={formatUnknownValue(value)}
        onChange={(event) => {
          const next = event.target.value;
          if (field.type === "number") {
            onChange(next === "" ? undefined : Number(next));
            return;
          }
          onChange(next === "" ? undefined : next);
        }}
        placeholder={field.remark ?? field.name}
        className="h-7 text-xs"
      />
    </div>
  );
}

/* ── 执行状态指示器 ── */

function ExecutionStatusIndicator({ status }: { status: ExecutionResult["status"] }) {
  if (status === "SUCCESS") {
    return (
      <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-600">
        <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
        执行成功
      </span>
    );
  }
  if (status === "FAILED") {
    return (
      <span className="flex items-center gap-1 text-[10px] font-semibold text-red-600">
        <span className="size-1.5 rounded-full bg-red-500" />
        执行失败
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-[10px] font-semibold text-amber-600">
      <span className="size-1.5 rounded-full bg-amber-500" />
      部分成功
    </span>
  );
}

/* ── 入参 JSON 报文区 ── */

function InputJsonSection({
  inputFields,
  inputs,
  submittedInputs,
  envCode,
  hasResult,
  onChange,
}: {
  inputFields: InputFieldDefinition[];
  inputs: Record<string, unknown>;
  submittedInputs: Record<string, unknown>;
  envCode: string;
  hasResult: boolean;
  onChange: (name: string, value: unknown) => void;
}) {
  const displayInputs = hasResult ? submittedInputs : inputs;
  const hasInputs = Object.keys(displayInputs).length > 0;

  return (
    <details open className="group rounded-md border bg-card overflow-hidden">
      <summary className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold cursor-pointer select-none hover:bg-muted/30 transition-colors">
        <span className="text-muted-foreground/50 group-open:rotate-90 transition-transform text-[10px]">▶</span>
        入参报文
        <Badge variant="outline" className="rounded text-[9px] px-1 py-0 ml-auto">{envCode || "未选环境"}</Badge>
      </summary>
      <div className="px-3 pb-2 space-y-2">
        {/* 入参编辑表单 */}
        {!hasResult && inputFields.length > 0 && (
          <div className="grid grid-cols-3 gap-2">
            {inputFields.map((field) => (
              <InputFieldControl
                key={field.name}
                field={field}
                value={inputs[field.name]}
                onChange={(value) => onChange(field.name, value)}
              />
            ))}
          </div>
        )}
        {/* JSON 预览 */}
        {hasInputs ? (
          <pre className="overflow-auto rounded-md bg-muted/40 p-2.5 text-[11px] leading-relaxed font-mono border border-border/50 max-h-[160px]">
            {jsonText(displayInputs)}
          </pre>
        ) : (
          <p className="text-[11px] text-muted-foreground italic py-1">无入参</p>
        )}
      </div>
    </details>
  );
}

/* ── 响应 JSON 报文区 ── */

function ResponseJsonSection({ result }: { result: ExecutionResult }) {
  return (
    <details className="group rounded-md border bg-card overflow-hidden">
      <summary className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold cursor-pointer select-none hover:bg-muted/30 transition-colors">
        <span className="text-muted-foreground/50 group-open:rotate-90 transition-transform text-[10px]">▶</span>
        响应报文
        <ExecutionStatusIndicator status={result.status} />
        <span className="ml-auto text-[10px] font-normal text-muted-foreground">
          {formatDuration(result.durationMs)}
        </span>
      </summary>
      <div className="px-3 pb-2">
        <pre className="overflow-auto rounded-md bg-muted/40 p-2.5 text-[11px] leading-relaxed font-mono border border-border/50 max-h-[200px]">
          {jsonText({
            status: result.status,
            errors: result.errors,
            finalOutput: result.finalOutput,
            stepCount: result.stepResults.length,
          })}
        </pre>
      </div>
    </details>
  );
}

/* ── 时间轴步骤项 ── */

function StepTimelineItem({
  step,
  stepIndex,
  isLast,
  selected,
  onSelect,
}: {
  step: TimelineStep;
  stepIndex: number;
  isLast: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const lineColor = step.pending
    ? "bg-border"
    : step.status === "SUCCESS"
      ? "bg-emerald-300 dark:bg-emerald-800"
      : step.status === "FAILED"
        ? "bg-red-300 dark:bg-red-800"
        : "bg-border";

  return (
    <div className="flex gap-2.5">
      {/* 左侧时间轴线 */}
      <div className="flex flex-col items-center w-5 shrink-0">
        <div className={cn(
          "flex items-center justify-center rounded-full border-2 shrink-0 mt-2 transition-colors",
          "size-5 text-[9px] font-bold",
          step.pending
            ? "border-muted-foreground/20 text-muted-foreground/40"
            : step.status === "SUCCESS"
              ? "border-emerald-400 bg-emerald-500 text-white"
              : step.status === "FAILED"
                ? "border-red-400 bg-red-500 text-white"
                : "border-muted bg-muted text-muted-foreground",
        )}>
          {stepIndex}
        </div>
        {!isLast && <div className={cn("w-0.5 flex-1 mt-1 transition-colors", lineColor)} />}
      </div>

      {/* 右侧卡片 */}
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "flex-1 rounded-md px-2.5 py-1.5 text-left transition-all mb-1.5",
          selected
            ? "bg-primary/8 border border-primary/20 shadow-sm"
            : "hover:bg-muted/60 border border-transparent",
        )}
      >
        <div className="flex items-center gap-1.5">
          <span className="min-w-0 flex-1 truncate text-xs font-medium">
            {step.stepName ?? step.stepId}
          </span>
          {step.pending ? (
            <PendingBadge />
          ) : (
            <StepStatusBadge status={step.status} />
          )}
        </div>
        <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="uppercase">{step.type}</span>
          {!step.pending && (
            <>
              <span className="text-border">·</span>
              <span>{formatDuration(step.durationMs)}</span>
            </>
          )}
        </div>
      </button>
    </div>
  );
}

/* ── 步骤详情面板（Tabs 布局） ── */

function StepDetailPanel({ step }: { step: StepResult }) {
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
    <section className={cn("rounded-lg border border-l-4 bg-card overflow-hidden", statusBorderColor)}>
      {/* 步骤 header */}
      <div className="px-4 py-3 border-b bg-muted/20">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="min-w-0 truncate text-sm font-semibold">{step.stepName ?? step.stepId}</h2>
          <Badge variant="outline" className="rounded text-[10px] px-1.5 py-0">{step.type}</Badge>
          <StepStatusBadge status={step.status} />
          {step.statusCode && <Badge variant="outline" className="rounded text-[10px] px-1.5 py-0">HTTP {step.statusCode}</Badge>}
          <span className="ml-auto text-[11px] text-muted-foreground flex items-center gap-1">
            <ClockIcon className="size-3" />
            {formatDuration(step.durationMs)}
          </span>
        </div>
        {step.error && (
          <div className="mt-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/20 rounded px-2 py-1.5">
            {step.error}
          </div>
        )}
      </div>

      {/* Tabs 内容区 */}
      <Tabs defaultValue="overview" className="p-0">
        <TabsList variant="line" className="w-full border-b rounded-none px-4 h-auto py-0 gap-0">
          <TabsTrigger value="overview" className="text-xs gap-1.5 data-[state=active]:text-foreground">
            <FileJsonIcon className="size-3" />
            概览
          </TabsTrigger>
          {step.type === "HTTP" && (
            <>
              <TabsTrigger value="request" className="text-xs gap-1.5 data-[state=active]:text-foreground">
                <SendIcon className="size-3" />
                请求
              </TabsTrigger>
              <TabsTrigger value="response" className="text-xs gap-1.5 data-[state=active]:text-foreground">
                <ServerIcon className="size-3" />
                响应
              </TabsTrigger>
            </>
          )}
          {step.type === "SQL" && (
            <TabsTrigger value="sql" className="text-xs gap-1.5 data-[state=active]:text-foreground">
              <DatabaseIcon className="size-3" />
              SQL
            </TabsTrigger>
          )}
        </TabsList>

        {/* 概览 Tab */}
        <TabsContent value="overview" className="p-4 space-y-4 m-0">
          <div className="grid grid-cols-2 gap-3 text-xs">
            <InfoItem label="开始时间" value={formatDateTime(step.startedAt)} />
            <InfoItem label="执行耗时" value={formatDuration(step.durationMs)} />
          </div>
          {Object.keys(step.outputs).length > 0 && (
            <div>
              <div className="text-xs font-semibold text-muted-foreground mb-2">输出变量</div>
              <div className="rounded-md border overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-muted/40 border-b">
                      <th className="text-left px-3 py-1.5 font-medium text-muted-foreground w-[40%]">变量名</th>
                      <th className="text-left px-3 py-1.5 font-medium text-muted-foreground">值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(step.outputs).map(([key, val]) => (
                      <tr key={key} className="border-b last:border-b-0">
                        <td className="px-3 py-1.5 font-mono text-[11px] text-foreground/80">{key}</td>
                        <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground break-all">{textValue(val)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {Object.keys(step.outputs).length === 0 && (
            <p className="text-xs text-muted-foreground italic py-2">该步骤无输出变量</p>
          )}
        </TabsContent>

        {/* HTTP 请求 Tab */}
        {step.type === "HTTP" && (
          <TabsContent value="request" className="p-4 space-y-3 m-0">
            <div className="grid grid-cols-3 gap-3 text-xs">
              <InfoItem label="方法" value={textValue(httpRequest.method)} mono />
              <InfoItem label="Body 类型" value={textValue(httpRequest.bodyType)} />
              <InfoItem label="URL" value={textValue(httpRequest.url)} mono />
            </div>
            <CollapsibleJson title="请求头" value={httpRequest.headers ?? {}} />
            <CollapsibleJson title="查询参数" value={httpRequest.query ?? {}} />
            <CollapsibleJson title="请求体" value={httpRequest.body ?? null} defaultOpen />
          </TabsContent>
        )}

        {/* HTTP 响应 Tab */}
        {step.type === "HTTP" && (
          <TabsContent value="response" className="p-4 space-y-4 m-0">
            {/* 状态码醒目展示 */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">状态码</span>
                {(() => {
                  const code = httpResponse.statusCode;
                  const codeNum = typeof code === "number" ? code : parseInt(String(code), 10);
                  const isSuccess = codeNum >= 200 && codeNum < 300;
                  const isRedirect = codeNum >= 300 && codeNum < 400;
                  return (
                    <span
                      className={cn(
                        "text-2xl font-bold tabular-nums",
                        isSuccess && "text-emerald-600 dark:text-emerald-400",
                        isRedirect && "text-amber-600 dark:text-amber-400",
                        !isSuccess && !isRedirect && "text-red-600 dark:text-red-400",
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
                <span>{httpResponse.elapsedMs === undefined ? "-" : formatDuration(Number(httpResponse.elapsedMs))}</span>
              </div>
            </div>
            {/* 响应体优先展示 */}
            <CollapsibleJson title="响应体" value={httpResponse.body ?? null} defaultOpen />
            <CollapsibleJson title="响应头" value={httpResponse.headers ?? {}} />
            <CollapsibleJson title="Cookie" value={httpResponse.cookies ?? []} />
            <CollapsibleJson title="业务判定" value={raw.businessResult ?? null} />
            <CollapsibleJson title="重试信息" value={raw.retryInfo ?? null} />
          </TabsContent>
        )}

        {/* SQL Tab */}
        {step.type === "SQL" && (
          <TabsContent value="sql" className="p-4 space-y-3 m-0">
            <div className="grid grid-cols-4 gap-3 text-xs">
              <InfoItem label="数据库" value={textValue(raw.dbType)} />
              <InfoItem label="操作" value={textValue(raw.operation)} />
              <InfoItem label="影响行数" value={textValue(raw.affectedRows)} />
              <InfoItem label="耗时" value={raw.elapsedMs === undefined ? "-" : formatDuration(Number(raw.elapsedMs))} />
            </div>
            <CollapsibleJson title="结果字段" value={sqlColumns} />
            <CollapsibleJson title="首行结果" value={raw.row ?? null} defaultOpen />
            <CollapsibleJson title="结果集" value={sqlRows} />
            <CollapsibleJson title="新增记录ID" value={raw.generatedKeys ?? []} />
            <CollapsibleJson title="警告" value={raw.warnings ?? []} />
          </TabsContent>
        )}

      </Tabs>
    </section>
  );
}

/* ── 信息项 ── */

function InfoItem({ label, value, mono, sub }: { label: string; value: string; mono?: boolean; sub?: string }) {
  return (
    <div className="space-y-0.5">
      <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className={cn("text-xs font-medium truncate", mono && "font-mono")}>{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

/* ── 可折叠 JSON 块 ── */

function CollapsibleJson({
  title,
  value,
  defaultOpen = false,
}: {
  title: string;
  value: unknown;
  defaultOpen?: boolean;
}) {
  const isEmpty = value === null || value === undefined || (typeof value === "object" && Object.keys(value).length === 0);

  return (
    <details open={defaultOpen} className="group">
      <summary className="flex items-center gap-2 text-xs font-semibold text-muted-foreground cursor-pointer select-none py-1 hover:text-foreground transition-colors">
        <span className="text-[10px] text-muted-foreground/50 group-open:rotate-90 transition-transform">▶</span>
        {title}
        {isEmpty && <span className="text-[10px] font-normal text-muted-foreground/50">(空)</span>}
      </summary>
      <div className="mt-1">
        <JsonBlock value={value} />
      </div>
    </details>
  );
}

/* ── JSON 代码块 ── */

function JsonBlock({ value, maxHeight = 300 }: { value: unknown; maxHeight?: number }) {
  const text = jsonText(value);
  const isShort = text.length < 80;

  return (
    <pre
      className={cn(
        "overflow-auto rounded-md bg-muted/40 p-3 text-[11px] leading-relaxed font-mono border border-border/50",
        !isShort && "whitespace-pre-wrap break-all",
      )}
      style={{ maxHeight: `${maxHeight}px` }}
    >
      {text}
    </pre>
  );
}

/* ── Badges ── */

function StepStatusBadge({ status }: { status: StepResult["status"] }) {
  const config = {
    SUCCESS: { label: "成功", icon: CheckCircle2Icon, className: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400" },
    FAILED: { label: "失败", icon: XCircleIcon, className: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400" },
    SKIPPED: { label: "跳过", icon: AlertTriangleIcon, className: "border-muted bg-muted text-muted-foreground" },
  }[status];
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={cn("gap-0.5 rounded px-1 py-0 text-[9px]", config.className)}>
      <Icon className="size-2.5" />
      {config.label}
    </Badge>
  );
}

function PendingBadge() {
  return (
    <Badge variant="outline" className="gap-0.5 rounded border-muted bg-muted px-1 py-0 text-[9px] text-muted-foreground">
      <CircleDashedIcon className="size-2.5" />
      待执行
    </Badge>
  );
}

/* ── 工具函数 ── */

function buildDefaultInputs(fields: InputFieldDefinition[]): Record<string, unknown> {
  const inputs: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.name === "env") continue;
    if (field.defaultValue !== undefined && field.defaultValue !== null) {
      inputs[field.name] = field.defaultValue;
    }
  }
  return inputs;
}

function stepToPendingResult(step: SceneDefinition["steps"][number], stepOrder?: number): TimelineStep {
  const now = new Date(0).toISOString();
  return {
    stepId: step.stepId,
    stepName: step.stepName,
    type: step.type,
    stepOrder: stepOrder ?? null,
    timelineOrder: null,
    status: "SKIPPED",
    startedAt: now,
    finishedAt: now,
    durationMs: 0,
    outputs: {},
    error: null,
    statusCode: null,
    pending: true,
  };
}

function unknownToRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function textValue(value: unknown): string {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "object") return jsonText(value);
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return value.toString();
  }
  if (typeof value === "symbol") return value.description ? `Symbol(${value.description})` : "Symbol()";
  if (typeof value === "function") return value.name ? `[Function ${value.name}]` : "[Function]";
  return "-";
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
  if (ms < 1000) return `${Math.round(ms * 1000) / 1000} ms`;
  return `${Math.round((ms / 1000) * 1000) / 1000} s`;
}

function formatDateTime(value: string): string {
  if (!value || value.startsWith("1970-01-01")) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}
