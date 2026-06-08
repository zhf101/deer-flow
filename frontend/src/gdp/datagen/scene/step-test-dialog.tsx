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
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
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
        toast.success(`请求成功 (${testResult.response?.statusCode})`);
        if (onTestSuccess) onTestSuccess(testResult);
      } else {
        toast.error(testResult.error?.message ?? "请求失败");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试执行失败");
    } finally {
      setTesting(false);
    }
  }, [envCode, step, inputs, depOutputs, onTestSuccess]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PlayIcon className="size-4 text-blue-500" />
            {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty stepName should fall through */}
            测试步骤：{step.stepName || step.stepId}
          </DialogTitle>
          <DialogDescription>
            {step.method} {step.path}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 min-h-0 pr-4">
          <div className="space-y-4">
            {/* 环境选择 */}
            <div className="space-y-2">
              <Label className="text-xs font-bold">运行环境</Label>
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

            {/* 输入参数 */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setShowInputs(!showInputs)}
                className="flex items-center gap-1 text-xs font-bold"
              >
                {showInputs ? <ChevronDownIcon className="size-3" /> : <ChevronRightIcon className="size-3" />}
                场景输入参数
              </button>
              {showInputs && (
                <div className="rounded-md border p-3 space-y-2">
                  {scene.inputSchema
                    .filter((f) => f.name !== "env")
                    .map((field) => (
                      <div key={field.name} className="grid grid-cols-[120px_1fr] gap-2 items-center">
                        <span className="text-[10px] font-mono font-bold truncate" title={field.name}>
                          {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty label should fall through */}
                          {field.label || field.name}
                          {field.required && <span className="text-destructive ml-0.5">*</span>}
                        </span>
                        <Input
                          className="h-7 text-[10px]"
                          value={safeStringify(inputs[field.name])}
                          placeholder={field.defaultValue != null ? `默认: ${safeStringify(field.defaultValue)}` : ""}
                          onChange={(e) =>
                            setInputs((prev) => ({ ...prev, [field.name]: e.target.value }))
                          }
                        />
                      </div>
                    ))}
                  {scene.inputSchema.filter((f) => f.name !== "env").length === 0 && (
                    <p className="text-[10px] text-muted-foreground italic">无输入参数</p>
                  )}
                </div>
              )}
            </div>

            {/* 前序步骤输出 */}
            {step.dependsOn.length > 0 && (
              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setShowDeps(!showDeps)}
                  className="flex items-center gap-1 text-xs font-bold"
                >
                  {showDeps ? <ChevronDownIcon className="size-3" /> : <ChevronRightIcon className="size-3" />}
                  前序步骤输出（{step.dependsOn.length} 个依赖）
                </button>
                {showDeps && (
                  <div className="rounded-md border p-3 space-y-3">
                    {Object.entries(depOutputs).map(([depId, outputs]) => (
                      <div key={depId} className="space-y-1">
                        <span className="text-[9px] font-bold text-muted-foreground uppercase">
                          {depId}
                        </span>
                        {Object.entries(outputs).map(([key, val]) => (
                          <div key={key} className="grid grid-cols-[120px_1fr] gap-2 items-center">
                            <span className="text-[10px] font-mono truncate">{key}</span>
                            <Input
                              className="h-7 text-[10px]"
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
              <div className="space-y-3 border-t pt-3">
                <div className="flex items-center gap-2">
                  {result.success ? (
                    <CheckCircle2Icon className="size-4 text-emerald-500" />
                  ) : (
                    <XCircleIcon className="size-4 text-destructive" />
                  )}
                  <span className="text-xs font-bold">
                    {result.success ? "测试通过" : "测试失败"}
                  </span>
                  {result.response?.statusCode && (
                    <Badge
                      variant={result.response.statusCode < 400 ? "default" : "destructive"}
                      className="text-[9px] h-4"
                    >
                      {result.response.statusCode}
                    </Badge>
                  )}
                  {result.response?.elapsedMs != null && (
                    <span className="text-[9px] text-muted-foreground">
                      {result.response.elapsedMs}ms
                    </span>
                  )}
                </div>

                {/* 提取的变量 */}
                {result.extractedOutputs && Object.keys(result.extractedOutputs).length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold text-muted-foreground uppercase">
                      提取的变量 ({Object.keys(result.extractedOutputs).length})
                    </span>
                    <div className="rounded-md border bg-muted/20 p-2 space-y-1">
                      {Object.entries(result.extractedOutputs).map(([key, val]) => (
                        <div key={key} className="flex items-center gap-2 text-[10px]">
                          <span className="font-mono font-bold text-blue-600">{key}</span>
                          <span className="text-muted-foreground">=</span>
                          <span className="font-mono truncate max-w-[300px]" title={safeStringify(val)}>
                            {safeStringify(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 响应体 */}
                {result.response?.body != null && (
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold text-muted-foreground uppercase">
                      响应体
                    </span>
                    <pre className="text-[9px] font-mono bg-muted/30 rounded-md p-3 max-h-[200px] overflow-auto whitespace-pre-wrap break-all">
                      {typeof result.response.body === "object"
                        ? JSON.stringify(result.response.body, null, 2)
                        : safeStringify(result.response.body).substring(0, 2000)}
                    </pre>
                  </div>
                )}

                {/* 错误信息 */}
                {result.error && (
                  <div className="text-[10px] text-destructive bg-destructive/5 rounded-md p-2">
                    {result.error.message}
                    {result.error.detail && (
                      <pre className="mt-1 text-[9px] whitespace-pre-wrap">{result.error.detail}</pre>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>

        {/* 底部按钮 */}
        <div className="flex justify-end gap-2 border-t pt-3 shrink-0">
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
