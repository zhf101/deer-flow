/**
 * ============================================================================
 * 任务编排 - 任务执行对话框
 * ============================================================================
 *
 * 任务运行的弹窗对话框，支持填入输入参数、执行任务并查看逐步执行结果。
 *
 * UI 内容：
 *   - 环境选择下拉框
 *   - 输入参数表单（根据关联场景的入参定义动态生成）
 *   - 执行按钮
 *   - 执行结果展示区域：
 *     - 整体状态（运行中/成功/失败）
 *     - 各步骤执行结果（可折叠展开）：
 *       - 步骤名称、状态图标、耗时
 *       - 请求/响应详情
 *       - 变量提取结果
 *   - 日志输出区域
 *
 * 被引用位置：
 *   - page.tsx 中全局渲染，由 TaskDashboard / TaskEditor 触发打开
 *
 * 新增/复用判断：新增页面，任务执行交互组件
 */
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
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { getTask, listEnvironments, runTask } from "../common/lib/api";
import type {
  EnvironmentResponse,
  InputFieldDefinition,
  TaskDefinition,
  TaskExecutionResult,
  TaskStepExecutionResult,
} from "../common/lib/types";

interface TaskRunDialogProps {
  taskCode: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TaskRunDialog({
  taskCode,
  open,
  onOpenChange,
}: TaskRunDialogProps) {
  const [task, setTask] = useState<TaskDefinition | null>(null);
  const [envCode, setEnvCode] = useState("");
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TaskExecutionResult | null>(null);
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const [loadingTask, setLoadingTask] = useState(false);

  // 加载任务定义
  useEffect(() => {
    if (open && taskCode) {
      setLoadingTask(true);
      getTask(taskCode)
        .then((data) => {
          setTask(data);
          // 预填默认值
          const defaults: Record<string, unknown> = {};
          for (const field of data.inputSchema || []) {
            if (field.defaultValue !== null && field.defaultValue !== undefined) {
              defaults[field.name] = field.defaultValue;
            }
          }
          setInputs(defaults);
        })
        .catch(() => toast.error("加载任务定义失败"));

      listEnvironments()
        .then((envs) => {
          setEnvironments(envs.filter((e) => e.status === "ENABLED"));
          if (envs.length > 0 && !envCode) {
            setEnvCode(envs[0]?.envCode ?? "");
          }
        })
        .catch(() => toast.error("加载环境列表失败"));
    }
  }, [open, taskCode]);

  // 关闭时重置
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
      const res = await runTask(taskCode, { envCode, inputs });
      setResult(res);
      if (res.status === "SUCCESS") {
        toast.success("任务执行成功");
      } else {
        toast.error(`任务执行${res.status === "PARTIAL" ? "部分失败" : "失败"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "执行请求失败");
    } finally {
      setRunning(false);
    }
  };

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  const inputFields = (task?.inputSchema || []).filter((f) => f.name !== "env");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PlayIcon className="size-4 text-green-600" />
            执行任务: {task?.taskName || taskCode}
          </DialogTitle>
          <DialogDescription>
            填写输入参数并选择执行环境，任务将按依赖关系依次执行各场景步骤。
          </DialogDescription>
        </DialogHeader>

        {loadingTask ? (
          <div className="flex items-center justify-center py-12">
            <Loader2Icon className="size-6 animate-spin text-primary" />
          </div>
        ) : (
          <div className="flex-1 grid grid-cols-2 gap-4 overflow-hidden min-h-0">
            {/* 左侧：输入 */}
            <ScrollArea className="pr-4">
              <div className="space-y-4">
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
                    此任务无需输入参数
                  </p>
                )}

                {/* 步骤预览 */}
                {task && task.steps.length > 0 && (
                  <div className="space-y-2">
                    <label className="text-sm font-medium">执行步骤预览</label>
                    <div className="space-y-1">
                      {task.steps.map((step, idx) => (
                        <div key={step.stepId} className="flex items-center gap-2 text-xs text-muted-foreground border rounded px-2 py-1.5">
                          <span className="font-mono">{idx + 1}</span>
                          <span className="flex-1 truncate">{step.stepName || step.stepId}</span>
                          <Badge variant="outline" className="text-[9px]">{step.sceneCode || "未配置"}</Badge>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

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
                      执行任务
                    </>
                  )}
                </Button>
              </div>
            </ScrollArea>

            {/* 右侧：结果 */}
            <ScrollArea className="pl-4 border-l">
              {result ? (
                <div className="space-y-4">
                  <ResultSummary result={result} />

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold">步骤执行详情</h4>
                    {result.stepResults.map((sr) => (
                      <SceneResultCard
                        key={sr.stepId}
                        step={sr}
                        expanded={expandedSteps.has(sr.stepId)}
                        onToggle={() => toggleStep(sr.stepId)}
                      />
                    ))}
                  </div>

                  {Object.keys(result.finalOutput).length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-semibold">最终输出</h4>
                      <pre className="text-xs bg-muted p-3 rounded-md overflow-auto max-h-60">
                        {JSON.stringify(result.finalOutput, null, 2)}
                      </pre>
                    </div>
                  )}

                  {result.errors.length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-semibold text-red-600">错误信息</h4>
                      {result.errors.map((err, i) => (
                        <div key={i} className="text-xs text-red-600 bg-red-50 p-2 rounded">
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
        )}
      </DialogContent>
    </Dialog>
  );
}

/* ── 子组件 ── */

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

  if (field.type === "boolean") {
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
  }

  if (field.type === "number") {
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
  }

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

function ResultSummary({ result }: { result: TaskExecutionResult }) {
  const isSuccess = result.status === "SUCCESS";
  const Icon = isSuccess ? CheckCircle2Icon : XCircleIcon;
  const color = isSuccess ? "text-green-600" : "text-red-600";
  const bg = isSuccess ? "bg-green-50" : "bg-red-50";

  return (
    <div className={cn("flex items-center gap-3 p-3 rounded-md", bg)}>
      <Icon className={cn("size-5", color)} />
      <div className="flex-1">
        <div className={cn("text-sm font-semibold", color)}>
          {isSuccess ? "执行成功" : result.status === "PARTIAL" ? "部分失败" : "执行失败"}
        </div>
        <div className="text-xs text-muted-foreground flex items-center gap-3">
          <span className="flex items-center gap-1">
            <ClockIcon className="size-3" />
            {result.durationMs}ms
          </span>
        </div>
      </div>
      <Badge variant={isSuccess ? "default" : "destructive"}>
        {result.status}
      </Badge>
    </div>
  );
}

function SceneResultCard({
  step,
  expanded,
  onToggle,
}: {
  step: TaskStepExecutionResult;
  expanded: boolean;
  onToggle: () => void;
}) {
  const config = {
    SUCCESS: { icon: CheckCircle2Icon, color: "text-green-600", bg: "bg-green-50" },
    FAILED: { icon: XCircleIcon, color: "text-red-600", bg: "bg-red-50" },
    SKIPPED: { icon: AlertCircleIcon, color: "text-gray-400", bg: "bg-gray-50" },
  }[step.status];

  const StatusIcon = config.icon;

  return (
    <div className={cn("border rounded-md overflow-hidden", config.bg)}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-black/5 transition-colors"
      >
        {expanded ? (
          <ChevronDownIcon className="size-3 shrink-0" />
        ) : (
          <ChevronRightIcon className="size-3 shrink-0" />
        )}
        <StatusIcon className={cn("size-4 shrink-0", config.color)} />
        <span className="text-xs font-medium flex-1 truncate">
          {step.stepId}
        </span>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
          {step.sceneCode}
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
