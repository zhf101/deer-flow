/**
 * ============================================================================
 * 场景编排 - 内联步骤测试对话框
 * ============================================================================
 *
 * 在场景编排中测试单个 HTTP 步骤的对话框。
 * 支持选择环境、填写输入参数、执行测试、查看响应和提取结果。
 *
 * UI 内容：
 *   - 环境选择下拉框
 *   - 输入参数表单（从场景 inputSchema 生成）
 *   - 前序步骤输出占位（可手动填写）
 *   - 执行按钮 + 加载状态
 *   - 测试结果展示：状态码、耗时、响应体、提取的变量
 */
"use client";

import {
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  Loader2Icon,
  PlayIcon,
  XCircleIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { listEnvironments, testHttpSource } from "../common/lib/api";
import {
  buildDefaultInputs,
  collectDependencyOutputs,
  resolveRuntimeVariables,
  stepToHttpTestConfig,
} from "../common/lib/step-test-utils";
import type {
  EnvironmentResponse,
  HttpStepDefinition,
  HttpSourceTestResult,
  SceneDefinition,
} from "../common/lib/types";

interface StepTestDialogProps {
  step: HttpStepDefinition;
  scene: SceneDefinition;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 测试成功后可更新步骤的 outputMapping */
  onTestSuccess?: (result: HttpSourceTestResult) => void;
}

export function StepTestDialog({
  step,
  scene,
  open,
  onOpenChange,
  onTestSuccess,
}: StepTestDialogProps) {
  const safeStringify = (val: unknown): string => {
    if (val == null) return "";
    if (typeof val === "string") return val;
    if (typeof val === "number" || typeof val === "boolean") return String(val);
    return JSON.stringify(val);
  };

  const [envCode, setEnvCode] = useState("");
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [depOutputs, setDepOutputs] = useState<Record<string, Record<string, unknown>>>({});
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<HttpSourceTestResult | null>(null);
  const [showInputs, setShowInputs] = useState(true);
  const [showDeps, setShowDeps] = useState(false);

  useEffect(() => {
    if (open) {
      listEnvironments()
        .then((envs) => setEnvironments(envs.filter((e) => e.status === "ENABLED")))
        .catch(() => setEnvironments([]));
      setInputs(buildDefaultInputs(scene.inputSchema));
      setDepOutputs(collectDependencyOutputs(step, scene));
      setResult(null);
    }
  }, [open, scene, step]);

  const handleTest = useCallback(async () => {
    if (!envCode) {
      toast.error("请先选择环境");
      return;
    }

    setTesting(true);
    setResult(null);

    try {
      const rawConfig = stepToHttpTestConfig(step);
      const config = resolveRuntimeVariables(rawConfig, inputs, depOutputs);
      const testResult = await testHttpSource(envCode, config);
      setResult(testResult);

      if (testResult.success) {
        toast.success("执行成功");
        if (onTestSuccess) onTestSuccess(testResult);
      } else {
        toast.error("执行失败");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试执行失败");
    } finally {
      setTesting(false);
    }
  }, [envCode, step, inputs, depOutputs, onTestSuccess]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!block max-w-2xl max-h-[85vh] overflow-y-auto p-0">
        {/* 头部 */}
        <div className="sticky top-0 z-10 bg-background border-b px-6 py-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <div className="flex size-7 items-center justify-center rounded-md bg-blue-500/10">
                <PlayIcon className="size-3.5 text-blue-500" />
              </div>
              <div className="flex flex-col gap-0.5">
                {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty stepName should fall through */}
                <span>{step.stepName || step.stepId}</span>
                <span className="text-xs font-normal text-muted-foreground">
                  {step.method} {step.path}
                </span>
              </div>
            </DialogTitle>
          </DialogHeader>
        </div>

        {/* 内容区 */}
        <div className="space-y-4 px-6 py-4">
          {/* 环境选择 */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-muted-foreground">运行环境</Label>
            <Select value={envCode} onValueChange={setEnvCode}>
              <SelectTrigger className="h-9">
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

          {/* 场景输入参数 */}
          <div className="rounded-lg border">
            <button
              type="button"
              onClick={() => setShowInputs(!showInputs)}
              className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-medium hover:bg-muted/50 transition-colors"
            >
              <span>场景输入参数</span>
              {showInputs ? <ChevronDownIcon className="size-3.5 text-muted-foreground" /> : <ChevronRightIcon className="size-3.5 text-muted-foreground" />}
            </button>
            {showInputs && (
              <div className="border-t px-4 py-3 space-y-2">
                {scene.inputSchema
                  .filter((f) => f.name !== "env")
                  .map((field) => (
                    <div key={field.name} className="grid grid-cols-[130px_1fr] gap-3 items-center">
                      <span className="text-xs font-mono truncate" title={field.name}>
                        {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty label should fall through */}
                        {field.label || field.name}
                        {field.required && <span className="text-destructive ml-0.5">*</span>}
                      </span>
                      <Input
                        className="h-8 text-xs"
                        value={safeStringify(inputs[field.name])}
                        placeholder={field.defaultValue != null ? `默认: ${safeStringify(field.defaultValue)}` : ""}
                        onChange={(e) =>
                          setInputs((prev) => ({ ...prev, [field.name]: e.target.value }))
                        }
                      />
                    </div>
                  ))}
                {scene.inputSchema.filter((f) => f.name !== "env").length === 0 && (
                  <p className="text-xs text-muted-foreground italic py-1">无输入参数</p>
                )}
              </div>
            )}
          </div>

          {/* 前序步骤输出 */}
          {step.dependsOn.length > 0 && (
            <div className="rounded-lg border">
              <button
                type="button"
                onClick={() => setShowDeps(!showDeps)}
                className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-medium hover:bg-muted/50 transition-colors"
              >
                <span>前序步骤输出（{step.dependsOn.length} 个依赖）</span>
                {showDeps ? <ChevronDownIcon className="size-3.5 text-muted-foreground" /> : <ChevronRightIcon className="size-3.5 text-muted-foreground" />}
              </button>
              {showDeps && (
                <div className="border-t px-4 py-3 space-y-3">
                  {Object.entries(depOutputs).map(([depId, outputs]) => (
                    <div key={depId} className="space-y-1.5">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                        {depId}
                      </span>
                      {Object.entries(outputs).map(([key, val]) => (
                        <div key={key} className="grid grid-cols-[130px_1fr] gap-3 items-center">
                          <span className="text-xs font-mono truncate">{key}</span>
                          <Input
                            className="h-8 text-xs"
                            value={safeStringify(val)}
                            placeholder="测试值"
                            onChange={(e) =>
                              setDepOutputs((prev) => ({
                                ...prev,
                                [depId]: { ...prev[depId], [key]: e.target.value },
                              }))
                            }
                          />
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 测试结果 */}
          {result && (
            <div className="space-y-3">
              {/* 状态横幅 */}
              <div
                className={`flex items-center gap-3 rounded-lg px-4 py-3 ${
                  result.success
                    ? "bg-emerald-500/8 border border-emerald-500/20"
                    : "bg-destructive/8 border border-destructive/20"
                }`}
              >
                {result.success ? (
                  <CheckCircle2Icon className="size-5 text-emerald-500 shrink-0" />
                ) : (
                  <XCircleIcon className="size-5 text-destructive shrink-0" />
                )}
                <div className="flex flex-col">
                  <span className={`text-sm font-semibold ${result.success ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"}`}>
                    {result.success ? "测试通过" : "测试失败"}
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    {result.response?.statusCode && (
                      <span className="text-xs font-mono text-muted-foreground">
                        Status: {result.response.statusCode}
                      </span>
                    )}
                    {result.response?.elapsedMs != null && (
                      <span className="text-xs text-muted-foreground">
                        {result.response.elapsedMs}ms
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* 错误信息 */}
              {result.error && (
                <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3">
                  <p className="text-sm text-destructive font-medium">{result.error.message}</p>
                  {result.error.detail && (
                    <pre className="mt-2 text-xs text-destructive/80 whitespace-pre-wrap font-mono">{result.error.detail}</pre>
                  )}
                </div>
              )}

              {/* 提取的变量 */}
              {result.extractedOutputs && Object.keys(result.extractedOutputs).length > 0 && (
                <div className="rounded-lg border">
                  <div className="px-4 py-2.5 border-b bg-muted/30">
                    <span className="text-xs font-medium">
                      提取的变量 ({Object.keys(result.extractedOutputs).length})
                    </span>
                  </div>
                  <div className="px-4 py-2 space-y-1.5">
                    {Object.entries(result.extractedOutputs).map(([key, val]) => (
                      <div key={key} className="flex items-center gap-2 text-xs">
                        <span className="font-mono font-semibold text-blue-600 dark:text-blue-400">{key}</span>
                        <span className="text-muted-foreground">=</span>
                        <span className="font-mono truncate max-w-[320px] text-muted-foreground" title={safeStringify(val)}>
                          {safeStringify(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 响应体 */}
              {result.response?.body != null && (
                <div className="rounded-lg border">
                  <div className="px-4 py-2.5 border-b bg-muted/30">
                    <span className="text-xs font-medium">响应体</span>
                  </div>
                  <pre className="px-4 py-3 text-xs font-mono max-h-[240px] overflow-auto whitespace-pre-wrap break-all leading-relaxed">
                    {typeof result.response.body === "object"
                      ? JSON.stringify(result.response.body, null, 2)
                      : safeStringify(result.response.body).substring(0, 2000)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 底部按钮栏 */}
        <div className="sticky bottom-0 border-t bg-background px-6 py-3 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          <Button
            size="sm"
            onClick={handleTest}
            disabled={testing || !envCode}
            className="gap-1.5"
          >
            {testing ? (
              <Loader2Icon className="size-3.5 animate-spin" />
            ) : (
              <PlayIcon className="size-3.5" />
            )}
            {testing ? "测试中..." : "执行测试"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
