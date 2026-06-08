/**
 * ============================================================================
 * 任务编排 - 任务编辑器
 * ============================================================================
 *
 * 任务的详细编辑页面，支持配置基本信息、编排执行步骤和管理版本。
 *
 * UI 内容：
 *   - 顶部工具栏：返回按钮、任务名称、保存按钮、运行按钮
 *   - 基本信息区域：
 *     - 任务名称、描述、关联场景
 *   - 步骤编排区域：
 *     - 步骤列表（可拖拽排序）
 *     - 新增步骤按钮
 *     - 每个步骤可展开配置（引用 HTTP 源/SQL 源、设置参数映射）
 *     - 步骤间的变量传递配置
 *   - 版本历史面板（Collapsible）：
 *     - 版本列表（版本号、时间、描述）
 *     - 版本对比和回滚
 *
 * 被引用位置：
 *   - page.tsx 中作为 TabType="task-editor" 的内容组件
 *
 * 新增/复用判断：新增页面，任务编排模块编辑页
 */
"use client";

import {
  ArrowLeftIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  Loader2Icon,
  PlayIcon,
  PlusIcon,
  SaveIcon,
  SendIcon,
  Trash2Icon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  createTask,
  getTask,
  listScenes,
  listTaskVersions,
  publishTask,
  updateTask,
  validateTask,
} from "../common/lib/api";
import { createDefaultTask } from "../common/lib/defaults";
import type {
  SceneSummary,
  TaskDefinition,
  TaskStepDefinition,
  TaskValidationIssue,
  TaskVersion,
} from "../common/lib/types";

interface TaskEditorProps {
  taskCode?: string | null;
  onBack: () => void;
  readOnly?: boolean;
  onRun?: (taskCode: string) => void;
}

export function TaskEditor({ taskCode, onBack, readOnly, onRun }: TaskEditorProps) {
  const [task, setTask] = useState<TaskDefinition>(() => createDefaultTask());
  const [persistedCode, setPersistedCode] = useState<string | null>(taskCode ?? null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [validating, setValidating] = useState(false);
  const [loading, setLoading] = useState(!!taskCode);
  const [issues, setIssues] = useState<TaskValidationIssue[]>([]);
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [versions, setVersions] = useState<TaskVersion[]>([]);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  // 加载任务数据
  useEffect(() => {
    if (taskCode) {
      setLoading(true);
      getTask(taskCode)
        .then((data) => {
          setTask(normalizeTask(data));
          setPersistedCode(taskCode);
        })
        .catch((err) => {
          toast.error(err instanceof Error ? err.message : "加载失败");
          onBack();
        })
        .finally(() => setLoading(false));
    } else {
      setTask(createDefaultTask());
      setPersistedCode(null);
    }
  }, [taskCode, onBack]);

  // 加载可用场景
  useEffect(() => {
    listScenes({ limit: 500 })
      .then((s) => setScenes(s.filter((sc) => sc.status === "PUBLISHED")))
      .catch(() => toast.error("加载场景列表失败"));
  }, []);

  // 加载版本列表
  useEffect(() => {
    if (persistedCode) {
      listTaskVersions(persistedCode)
        .then(setVersions)
        .catch(() => undefined);
    }
  }, [persistedCode]);

  const save = async (showToast = true): Promise<string | null> => {
    if (readOnly) return persistedCode;
    if (!task.taskCode || !task.taskName) {
      if (showToast) toast.error("请先填写任务编码和名称");
      return null;
    }
    setSaving(true);
    try {
      const version = persistedCode
        ? await updateTask(persistedCode, task)
        : await createTask(task);
      setTask(normalizeTask(version.definition));
      setPersistedCode(version.taskCode);
      if (showToast) toast.success(`已保存 (v${version.versionNo})`);
      return version.taskCode;
    } catch (error) {
      if (showToast) toast.error(error instanceof Error ? error.message : "保存失败");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    const code = persistedCode ?? (await save(false));
    if (!code) return;
    setValidating(true);
    try {
      const result = await validateTask(code);
      setIssues(result.issues);
      if (result.valid) {
        toast.success("校验通过");
      } else {
        toast.warning(`校验发现 ${result.issues.length} 个问题`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "校验失败");
    } finally {
      setValidating(false);
    }
  };

  const handlePublish = async () => {
    const code = persistedCode ?? (await save(false));
    if (!code) return;

    setPublishing(true);
    try {
      const version = await publishTask(code);
      setTask(normalizeTask(version.definition));
      toast.success(`已发布 v${version.versionNo}`);
      onBack();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "发布失败");
    } finally {
      setPublishing(false);
    }
  };

  const addStep = () => {
    if (readOnly) return;
    const idx = task.steps.length;
    const newStep: TaskStepDefinition = {
      stepId: `scene_step_${idx + 1}`,
      sceneCode: "",
      stepName: `步骤 ${idx + 1}`,
      enabled: true,
      dependsOn: [],
      inputMapping: {},
      outputMapping: {},
    };
    setTask({ ...task, steps: [...task.steps, newStep] });
    setSelectedStepId(newStep.stepId);
  };

  const removeStep = (stepId: string) => {
    if (readOnly) return;
    setTask({
      ...task,
      steps: task.steps.filter((s) => s.stepId !== stepId),
    });
    if (selectedStepId === stepId) setSelectedStepId(null);
  };

  const updateStep = (updated: TaskStepDefinition) => {
    setTask({
      ...task,
      steps: task.steps.map((s) => (s.stepId === updated.stepId ? updated : s)),
    });
  };

  const selectedStep = task.steps.find((s) => s.stepId === selectedStepId) ?? null;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2Icon className="text-primary size-8 animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={onBack}>
            <ArrowLeftIcon className="size-4" />
          </Button>
          <div>
            <h2 className="text-lg font-semibold">
              {persistedCode ? (readOnly ? "查看任务" : "编辑任务") : "新增任务"}
            </h2>
            <p className="text-xs text-muted-foreground">
              {task.taskName || "未命名任务"}
              {persistedCode && ` (${persistedCode})`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {persistedCode && task.status === "PUBLISHED" && onRun && !readOnly && (
            <Button variant="outline" size="sm" onClick={() => onRun(persistedCode)} className="gap-1 text-green-600">
              <PlayIcon className="size-3.5" /> 执行
            </Button>
          )}
          {!readOnly && (
            <>
              <Button variant="outline" size="sm" onClick={handleValidate} disabled={validating} className="gap-1">
                {validating ? <Loader2Icon className="size-3.5 animate-spin" /> : null}
                校验
              </Button>
              <Button variant="outline" size="sm" onClick={() => save()} disabled={saving} className="gap-1">
                {saving ? <Loader2Icon className="size-3.5 animate-spin" /> : <SaveIcon className="size-3.5" />}
                保存
              </Button>
              <Button size="sm" onClick={handlePublish} disabled={publishing} className="gap-1">
                {publishing ? <Loader2Icon className="size-3.5 animate-spin" /> : <SendIcon className="size-3.5" />}
                发布
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 校验问题 */}
      {issues.length > 0 && (
        <div className="border-b bg-yellow-50 px-6 py-2">
          {issues.map((issue, i) => (
            <div key={i} className={cn("text-xs", issue.level === "ERROR" ? "text-red-600" : "text-yellow-600")}>
              [{issue.level}] {issue.field}: {issue.message}
            </div>
          ))}
        </div>
      )}

      {/* 主内容：双栏布局 */}
      <div className="flex flex-1 min-h-0">
        {/* 左侧：基本信息 + 步骤列表 */}
        <div className="w-[360px] border-r flex flex-col">
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-4">
              {/* 基本信息 */}
              <div className="space-y-3">
                <h3 className="text-sm font-semibold">基本信息</h3>
                <div>
                  <Label className="text-xs">任务编码</Label>
                  <Input
                    value={task.taskCode}
                    disabled={Boolean(readOnly) || persistedCode !== null}
                    onChange={(e) => setTask({ ...task, taskCode: e.target.value })}
                    placeholder="如: create_test_data"
                    className="h-8 font-mono text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">任务名称</Label>
                  <Input
                    value={task.taskName}
                    disabled={readOnly}
                    onChange={(e) => setTask({ ...task, taskName: e.target.value })}
                    placeholder="如: 电商测试数据生成"
                    className="h-8 text-xs"
                  />
                </div>
                <div>
                  <Label className="text-xs">备注</Label>
                  <Textarea
                    value={task.taskRemark ?? ""}
                    disabled={readOnly}
                    onChange={(e) => setTask({ ...task, taskRemark: e.target.value })}
                    placeholder="任务说明..."
                    className="min-h-[60px] text-xs resize-none"
                  />
                </div>
              </div>

              {/* 步骤列表 */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">场景步骤</h3>
                  {!readOnly && (
                    <Button variant="outline" size="sm" onClick={addStep} className="h-7 text-xs gap-1">
                      <PlusIcon className="size-3" /> 添加步骤
                    </Button>
                  )}
                </div>

                {task.steps.length === 0 ? (
                  <div className="border border-dashed rounded-md p-4 text-center text-xs text-muted-foreground">
                    暂无步骤，点击&quot;添加步骤&quot;编排场景
                  </div>
                ) : (
                  <div className="space-y-1">
                    {task.steps.map((step, idx) => {
                      const scene = scenes.find((s) => s.sceneCode === step.sceneCode);
                      return (
                        <div
                          key={step.stepId}
                          className={cn(
                            "flex items-center gap-2 rounded-md border p-2 cursor-pointer transition-colors text-xs",
                            selectedStepId === step.stepId
                              ? "border-primary bg-primary/5"
                              : "hover:bg-muted"
                          )}
                          onClick={() => setSelectedStepId(step.stepId)}
                        >
                          <span className="font-mono text-muted-foreground w-5 text-center shrink-0">
                            {idx + 1}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">
                              {step.stepName ?? step.stepId}
                            </div>
                            <div className="text-muted-foreground text-[10px] truncate">
                              {scene ? scene.sceneName : step.sceneCode ?? "未选择场景"}
                            </div>
                          </div>
                          <Switch
                            checked={step.enabled}
                            disabled={readOnly}
                            onCheckedChange={(checked) =>
                              updateStep({ ...step, enabled: checked })
                            }
                            onClick={(e) => e.stopPropagation()}
                          />
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* 版本历史 */}
              {versions.length > 0 && (
                <Collapsible>
                  <CollapsibleTrigger className="flex items-center gap-1 text-xs font-semibold text-muted-foreground">
                    <ChevronRightIcon className="size-3" />
                    版本历史 ({versions.length})
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pt-2 space-y-1">
                    {versions.map((v) => (
                      <div key={v.id} className="text-[10px] text-muted-foreground flex items-center gap-2">
                        <Badge variant={v.versionStatus === "PUBLISHED" ? "default" : "secondary"} className="text-[9px] h-4 py-0">
                          v{v.versionNo}
                        </Badge>
                        <span>{v.versionStatus}</span>
                        <span>{new Date(v.createdAt).toLocaleString()}</span>
                      </div>
                    ))}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* 右侧：选中步骤详情 */}
        <div className="flex-1 min-w-0">
          {selectedStep ? (
            <StepDetailPanel
              step={selectedStep}
              scenes={scenes}
              allSteps={task.steps}
              onChange={updateStep}
              onDelete={removeStep}
              readOnly={readOnly}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
              选择左侧步骤进行配置，或添加新步骤
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── 步骤详情面板 ── */

function StepDetailPanel({
  step,
  scenes,
  allSteps,
  onChange,
  onDelete,
  readOnly,
}: {
  step: TaskStepDefinition;
  scenes: SceneSummary[];
  allSteps: TaskStepDefinition[];
  onChange: (step: TaskStepDefinition) => void;
  onDelete: (stepId: string) => void;
  readOnly?: boolean;
}) {
  const [mappingOpen, setMappingOpen] = useState(true);
  const availableSteps = allSteps.filter((s) => s.stepId !== step.stepId);

  return (
    <ScrollArea className="h-full">
      <div className="p-6 space-y-6 max-w-3xl">
        {/* 步骤基本信息 */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold">步骤配置</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">步骤 ID</Label>
              <Input
                value={step.stepId}
                disabled={readOnly}
                onChange={(e) => onChange({ ...step, stepId: e.target.value })}
                className="h-8 font-mono text-xs"
              />
            </div>
            <div>
              <Label className="text-xs">步骤名称</Label>
              <Input
                value={step.stepName ?? ""}
                disabled={readOnly}
                onChange={(e) => onChange({ ...step, stepName: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
          </div>
        </div>

        {/* 场景选择 */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold">关联场景</h3>
          <Select
            value={step.sceneCode || ""}
            onValueChange={(v) => onChange({ ...step, sceneCode: v })}
            disabled={readOnly}
          >
            <SelectTrigger className="text-xs">
              <SelectValue placeholder="选择要执行的场景..." />
            </SelectTrigger>
            <SelectContent>
              {scenes.map((sc) => (
                <SelectItem key={sc.sceneCode} value={sc.sceneCode}>
                  {sc.sceneName} ({sc.sceneCode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {step.sceneCode && (
            <p className="text-xs text-muted-foreground">
              运行时将执行场景 &quot;{step.sceneCode}&quot; 的已发布版本。
            </p>
          )}
        </div>

        {/* 依赖项 */}
        <div className="space-y-3">
          <h3 className="text-sm font-semibold">依赖步骤</h3>
          {availableSteps.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {availableSteps.map((s) => {
                const isSelected = step.dependsOn.includes(s.stepId);
                return (
                  <button
                    key={s.stepId}
                    disabled={readOnly}
                    onClick={() => {
                      const next = isSelected
                        ? step.dependsOn.filter((id) => id !== s.stepId)
                        : [...step.dependsOn, s.stepId];
                      onChange({ ...step, dependsOn: next });
                    }}
                    className={cn(
                      "rounded-md border px-2 py-1 text-xs transition-colors",
                      isSelected
                        ? "border-primary bg-primary/10 text-primary"
                        : "hover:bg-muted"
                    )}
                  >
                    {s.stepName ?? s.stepId}
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">无其他步骤可依赖</p>
          )}
        </div>

        {/* 输入/输出映射 */}
        <Collapsible open={mappingOpen} onOpenChange={setMappingOpen}>
          <CollapsibleTrigger className="flex items-center gap-1 text-sm font-semibold">
            {mappingOpen ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4" />}
            参数映射
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-3 space-y-4">
            <div>
              <Label className="text-xs">输入映射 (JSON)</Label>
              <p className="text-[10px] text-muted-foreground mb-1">
                任务变量 → 场景输入参数的映射，如 {"{"} &quot;userId&quot;: &quot;$&#123;input.userId&#125;&quot; {"}"}
              </p>
              <Textarea
                className="font-mono text-xs"
                rows={6}
                disabled={readOnly}
                value={JSON.stringify(step.inputMapping, null, 2)}
                onChange={(e) => {
                  try { onChange({ ...step, inputMapping: JSON.parse(e.target.value) }); }
                  catch { /* 忽略 */ }
                }}
              />
            </div>
            <div>
              <Label className="text-xs">输出映射 (JSON)</Label>
              <p className="text-[10px] text-muted-foreground mb-1">
                场景输出 → 任务变量的映射，如 {"{"} &quot;orderNo&quot;: &quot;orderNo&quot; {"}"}
              </p>
              <Textarea
                className="font-mono text-xs"
                rows={4}
                disabled={readOnly}
                value={JSON.stringify(step.outputMapping, null, 2)}
                onChange={(e) => {
                  try { onChange({ ...step, outputMapping: JSON.parse(e.target.value) }); }
                  catch { /* 忽略 */ }
                }}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* 删除 */}
        {!readOnly && (
          <div className="border-t pt-4">
            <Button variant="destructive" size="sm" onClick={() => onDelete(step.stepId)} className="gap-1 text-xs">
              <Trash2Icon className="size-3.5" /> 删除此步骤
            </Button>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}

/* ── 辅助函数 ── */

function normalizeTask(task: TaskDefinition): TaskDefinition {
  return {
    ...task,
    inputSchema: task.inputSchema || [],
    steps: (task.steps || []).map((s) => ({
      ...s,
      dependsOn: s.dependsOn || [],
      enabled: s.enabled ?? true,
      inputMapping: s.inputMapping || {},
      outputMapping: s.outputMapping || {},
    })),
    resultMapping: task.resultMapping || {},
  };
}
