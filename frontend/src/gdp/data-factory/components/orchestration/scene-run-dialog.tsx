"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  Loader2Icon,
  PlayIcon,
  XCircleIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

import { listEnvironments, runScene } from "../../lib/api";
import type {
  EnvironmentResponse,
  ExecutionResult,
  InputFieldDefinition,
  SceneDefinition,
  StepResult,
} from "../../lib/types";

interface SceneRunDialogProps {
  scene: SceneDefinition;
  sceneCode: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SceneRunDialog({
  scene,
  sceneCode,
  open,
  onOpenChange,
}: SceneRunDialogProps) {
  const [envCode, setEnvCode] = useState("");
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  // 加载环境列表
  useEffect(() => {
    if (open) {
      listEnvironments()
        .then((envs) => {
          setEnvironments(envs.filter((e) => e.status === "ENABLED"));
          if (envs.length > 0 && !envCode) {
            setEnvCode(envs[0].envCode);
          }
        })
        .catch(() => toast.error("加载环境列表失败"));
    }
  }, [open]);

  // 预填默认值
  useEffect(() => {
    if (open && scene.inputSchema) {
      const defaults: Record<string, unknown> = {};
      for (const field of scene.inputSchema) {
        if (field.defaultValue !== null && field.defaultValue !== undefined) {
          defaults[field.name] = field.defaultValue;
        }
      }
      setInputs(defaults);
    }
  }, [open, scene.inputSchema]);

  // 重置状态
  useEffect(() => {
    if (!open) {
      setResult(null);
      setRunning(false);
      setExpandedSteps(new Set());
    }
  }, [open]);

  const handleRun = async () => {
    if (!envCode) {
      toast.error("请先选择执行环境");
      return;
    }

    setRunning(true);
    setResult(null);

    try {
      const res = await runScene(sceneCode, { envCode, inputs });
      setResult(res);
      if (res.status === "SUCCESS") {
        toast.success("场景执行成功");
      } else {
        toast.error(`场景执行失败: ${res.errors[0] || "未知错误"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "执行请求失败");
    } finally {
      setRunning(false);
    }
  };

  const toggleStepExpand = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  // 过滤掉 env 字段（由环境选择器处理）
  const inputFields = scene.inputSchema.filter((f) => f.name !== "env");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PlayIcon className="size-4 text-green-600" />
            执行场景: {scene.sceneName}
          </DialogTitle>
          <DialogDescription>
            填写输入参数并选择执行环境，点击执行后查看各步骤结果。
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 grid grid-cols-2 gap-4 overflow-hidden min-h-0">
          {/* ── 左侧：输入表单 ── */}
          <ScrollArea className="pr-4">
            <div className="space-y-4">
              {/* 环境选择 */}
              <div className="space-y-2">
                <label className="text-sm font-medium">执行环境</label>
                <Select value={envCode} onValueChange={setEnvCode}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择环境..." />
                  </SelectTrigger>
                  <SelectContent>
                    {environments.map((env) => (
                      <SelectItem key={env.envCode} value={env.envCode}>
                        {env.envName} ({env.envCode})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* 动态输入字段 */}
              {inputFields.map((field) => (
                <InputFieldRenderer
                  key={field.name}
                  field={field}
                  value={inputs[field.name]}
                  onChange={(val) =>
                    setInputs((prev) => ({ ...prev, [field.name]: val }))
                  }
                />
              ))}

              {inputFields.length === 0 && (
                <p className="text-sm text-muted-foreground italic">
                  此场景无需输入参数
                </p>
              )}

              {/* 执行按钮 */}
              <Button
                onClick={handleRun}
                disabled={running || !envCode}
                className="w-full bg-green-600 hover:bg-green-700 text-white"
              >
                {running ? (
                  <>
                    <Loader2Icon className="size-4 animate-spin mr-2" />
                    执行中...
                  </>
                ) : (
                  <>
                    <PlayIcon className="size-4 mr-2" />
                    执行
                  </>
                )}
              </Button>
            </div>
          </ScrollArea>

          {/* ── 右侧：执行结果 ── */}
          <ScrollArea className="pl-4 border-l">
            {result ? (
              <div className="space-y-4">
                {/* 总体结果 */}
                <ResultSummary result={result} />

                {/* 步骤结果列表 */}
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">步骤执行详情</h4>
                  {result.stepResults.map((sr) => (
                    <StepResultCard
                      key={sr.stepId}
                      step={sr}
                      expanded={expandedSteps.has(sr.stepId)}
                      onToggle={() => toggleStepExpand(sr.stepId)}
                    />
                  ))}
                </div>

                {/* 最终输出 */}
                {Object.keys(result.finalOutput).length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold">最终输出</h4>
                    <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-60">
                      {JSON.stringify(result.finalOutput, null, 2)}
                    </pre>
                  </div>
                )}

                {/* 错误列表 */}
                {result.errors.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-red-600">
                      错误信息
                    </h4>
                    {result.errors.map((err, i) => (
                      <div
                        key={i}
                        className="text-xs text-red-600 bg-red-50 p-2 rounded"
                      >
                        {err}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                <div className="text-center">
                  <PlayIcon className="size-8 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">填写参数后点击执行</p>
                </div>
              </div>
            )}
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── 输入字段渲染器 ─────────────────────────────────────────────────────

function InputFieldRenderer({
  field,
  value,
  onChange,
}: {
  field: InputFieldDefinition;
  value: unknown;
  onChange: (val: unknown) => void;
}) {
  const label = field.label || field.name;

  switch (field.type) {
    case "boolean":
      return (
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id={`field-${field.name}`}
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
            className="rounded border-gray-300"
          />
          <label htmlFor={`field-${field.name}`} className="text-sm font-medium">
            {label}
            {field.required && <span className="text-red-500 ml-1">*</span>}
          </label>
        </div>
      );

    case "number":
      return (
        <div className="space-y-1">
          <label className="text-sm font-medium">
            {label}
            {field.required && <span className="text-red-500 ml-1">*</span>}
          </label>
          <Input
            type="number"
            value={value != null ? String(value) : ""}
            onChange={(e) => {
              const v = e.target.value;
              onChange(v === "" ? undefined : Number(v));
            }}
            placeholder={field.remark || `输入 ${label}`}
          />
        </div>
      );

    default:
      return (
        <div className="space-y-1">
          <label className="text-sm font-medium">
            {label}
            {field.required && <span className="text-red-500 ml-1">*</span>}
          </label>
          <Input
            value={value != null ? String(value) : ""}
            onChange={(e) => onChange(e.target.value || undefined)}
            placeholder={field.remark || `输入 ${label}`}
          />
        </div>
      );
  }
}

// ── 总体结果摘要 ─────────────────────────────────────────────────────

function ResultSummary({ result }: { result: ExecutionResult }) {
  const isSuccess = result.status === "SUCCESS";
  const Icon = isSuccess ? CheckCircle2Icon : XCircleIcon;
  const color = isSuccess ? "text-green-600" : "text-red-600";
  const bg = isSuccess ? "bg-green-50" : "bg-red-50";

  return (
    <div className={cn("flex items-center gap-3 p-3 rounded-md", bg)}>
      <Icon className={cn("size-5", color)} />
      <div className="flex-1">
        <div className={cn("text-sm font-semibold", color)}>
          {isSuccess ? "执行成功" : "执行失败"}
        </div>
        <div className="text-xs text-muted-foreground flex items-center gap-3">
          <span>版本 v{result.versionNo}</span>
          <span className="flex items-center gap-1">
            <ClockIcon className="size-3" />
            {result.durationMs}ms
          </span>
          <span>{result.envCode}</span>
        </div>
      </div>
      <Badge variant={isSuccess ? "default" : "destructive"}>
        {result.status}
      </Badge>
    </div>
  );
}

// ── 步骤结果卡片 ─────────────────────────────────────────────────────

function StepResultCard({
  step,
  expanded,
  onToggle,
}: {
  step: StepResult;
  expanded: boolean;
  onToggle: () => void;
}) {
  const statusConfig = {
    SUCCESS: { icon: CheckCircle2Icon, color: "text-green-600", bg: "bg-green-50" },
    FAILED: { icon: XCircleIcon, color: "text-red-600", bg: "bg-red-50" },
    SKIPPED: { icon: AlertCircleIcon, color: "text-gray-400", bg: "bg-gray-50" },
  }[step.status];

  const StatusIcon = statusConfig.icon;

  return (
    <div className={cn("border rounded-md overflow-hidden", statusConfig.bg)}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-black/5 transition-colors"
      >
        {expanded ? (
          <ChevronDownIcon className="size-3 shrink-0" />
        ) : (
          <ChevronRightIcon className="size-3 shrink-0" />
        )}
        <StatusIcon className={cn("size-4 shrink-0", statusConfig.color)} />
        <span className="text-xs font-medium flex-1 truncate">
          {step.stepName || step.stepId}
        </span>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
          {step.type}
        </Badge>
        <span className="text-[10px] text-muted-foreground shrink-0 flex items-center gap-1">
          <ClockIcon className="size-3" />
          {step.durationMs}ms
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t bg-white/50">
          {step.error && (
            <div className="text-xs text-red-600 mt-2 p-2 bg-red-50 rounded">
              {step.error}
            </div>
          )}
          {step.statusCode && (
            <div className="text-xs text-muted-foreground mt-2">
              HTTP {step.statusCode}
            </div>
          )}
          {Object.keys(step.outputs).length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] font-semibold text-muted-foreground mb-1">
                输出变量
              </div>
              <pre className="text-[11px] bg-muted p-2 rounded overflow-auto max-h-40">
                {JSON.stringify(step.outputs, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
