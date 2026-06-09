"use client";

import {
  FileJsonIcon,
  InfoIcon,
  LayoutGridIcon,
  LayersIcon,
  Loader2Icon,
  Settings2Icon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ScrollArea } from "@/components/ui/scroll-area";
import { TooltipProvider } from "@/components/ui/tooltip";

import {
  createScene,
  getScene,
  listHttpSources,
  listSqlSources,
  publishScene,
  updateScene,
} from "../common/lib/api";
import { createDefaultHttpTimeoutConfig, createDefaultScene, createDefaultStep } from "../common/lib/defaults";
import { toStrictScenePayload } from "../common/lib/step-payload";
import { validateSceneForPublish } from "../common/lib/step-validation";
import type {
  HttpSourceResponse,
  SceneDefinition,
  SqlSourceResponse,
  StepDefinition,
  ValidationIssue,
} from "../common/lib/types";
import { formatUnknownValue } from "../common/lib/value-utils";

import { BasicInfoPanel } from "./basic-info-panel";
import { BatchConfigPanel } from "./batch-config-panel";
import { InputSchemaPanel } from "./input-schema-panel";
import { LogicOrchestrationStep } from "./logic-orchestration-step";
import { ResultMappingPanel } from "./result-mapping-panel";
import { SceneEditorHeader } from "./scene-editor-header";
import { SceneEditorSidebar } from "./scene-editor-sidebar";
import { SceneRunDialog } from "./scene-run-dialog";

interface SceneEditorProps {
  sceneCode?: string | null;
  onBack: () => void;
  readOnly?: boolean;
}

const STEPS = [
  { title: "基础配置", description: "定义场景基本信息", icon: InfoIcon },
  { title: "参数配置", description: "配置场景输入参数", icon: FileJsonIcon },
  { title: "逻辑编排", description: "编排执行步骤与逻辑", icon: LayersIcon },
  { title: "结果输出", description: "配置最终返回结果", icon: LayoutGridIcon },
  { title: "批量设置", description: "配置批量执行策略", icon: Settings2Icon },
];

export function SceneEditor({ sceneCode, onBack, readOnly }: SceneEditorProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [scene, setScene] = useState<SceneDefinition>(() => createDefaultScene());
  const [persistedSceneCode, setPersistedSceneCode] = useState<string | null>(
    sceneCode ?? null,
  );
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [httpSources, setHttpSources] = useState<HttpSourceResponse[]>([]);
  const [sqlSources, setSqlSources] = useState<SqlSourceResponse[]>([]);
  const [loading, setLoading] = useState(!!sceneCode);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [showRunDialog, setShowRunDialog] = useState(false);

  useEffect(() => {
    if (sceneCode) {
      setLoading(true);
      getScene(sceneCode)
        .then((data) => {
          const next = normalizeScene(data);
          setScene(next);
          setLastSavedSnapshot(buildSceneSnapshot(next));
          setPersistedSceneCode(sceneCode);
        })
        .catch((err) => {
          toast.error(err instanceof Error ? err.message : "加载失败");
          onBack();
        })
        .finally(() => setLoading(false));
    } else {
      setScene(createDefaultScene());
      setPersistedSceneCode(null);
      setLastSavedSnapshot(null);
    }
  }, [sceneCode, onBack]);

  useEffect(() => {
    listHttpSources()
      .then(setHttpSources)
      .catch(() => setHttpSources([]));
    listSqlSources()
      .then(setSqlSources)
      .catch(() => setSqlSources([]));
  }, []);

  useEffect(() => {
    setIssues(validateSceneForPublish(scene));
  }, [scene]);

  // 将校验问题按步骤分组，供侧边栏导航显示 ERROR 红点
  const stepIssueCounts = useMemo(() => {
    const counts = Array.from({ length: STEPS.length }, () => ({ errors: 0, warnings: 0 }));
    for (const issue of issues) {
      let stepIdx = -1;
      if (issue.field === "sceneCode" || issue.field === "sceneName" || issue.field === "sceneRemark") {
        stepIdx = 0;
      } else if (issue.field.startsWith("inputSchema")) {
        stepIdx = 1;
      } else if (issue.field.startsWith("step:") || issue.field.startsWith("steps[")) {
        stepIdx = 2;
      } else if (issue.field.startsWith("resultMapping") || issue.field.startsWith("resultSchema")) {
        stepIdx = 3;
      } else if (issue.field.startsWith("batchConfig")) {
        stepIdx = 4;
      }
      if (stepIdx >= 0 && stepIdx < counts.length) {
        if (issue.level === "ERROR") counts[stepIdx]!.errors++;
        else if (issue.level === "WARNING") counts[stepIdx]!.warnings++;
      }
    }
    return counts;
  }, [issues]);

  const currentSceneSnapshot = useMemo(() => buildSceneSnapshot(scene), [scene]);
  const hasUnsavedChanges = persistedSceneCode === null || currentSceneSnapshot !== lastSavedSnapshot;

  const save = async (showToast = true): Promise<string | null> => {
    if (readOnly) return persistedSceneCode;
    if (!scene.sceneCode || !scene.sceneName) {
        if (showToast) toast.error("请先填写场景编码和名称");
        return null;
    }

    const payload = toStrictScenePayload(scene);
    const snapshot = JSON.stringify(payload);
    if (persistedSceneCode && snapshot === lastSavedSnapshot) {
      if (showToast) toast.info("没有需要保存的变更");
      return persistedSceneCode;
    }
    
    setSaving(true);
    try {
      const version = persistedSceneCode
        ? await updateScene(persistedSceneCode, payload)
        : await createScene(payload);
      const next = normalizeScene(version.definition);
      setScene(next);
      setLastSavedSnapshot(buildSceneSnapshot(next));
      setPersistedSceneCode(version.sceneCode);
      if (showToast) toast.success(`配置已自动保存 (v${version.versionNo})`);
      return version.sceneCode;
    } catch (error) {
      if (showToast) toast.error(error instanceof Error ? error.message : "保存失败");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const navigateToStep = async (idx: number) => {
      if (idx === currentStep) return;
      if (!readOnly && hasUnsavedChanges) await save(false);
      setCurrentStep(idx);
  };

  const runPublish = async () => {
    if (readOnly) return;
    if (persistedSceneCode && scene.status === "PUBLISHED" && !hasUnsavedChanges) {
      toast.info("当前版本已经发布，无需重复发布");
      return;
    }
    
    const errors = issues.filter(i => i.level === 'ERROR');
    if (errors.length > 0) {
        toast.error(`发布校验未通过: ${errors[0]?.message ?? '未知错误'}`);
        return;
    }

    setPublishing(true);
    try {
      const code = hasUnsavedChanges ? await save(false) : persistedSceneCode;
      if (!code) {
        toast.error("保存失败，无法发布");
        return;
      }
      const version = await publishScene(code);
      const next = normalizeScene(version.definition);
      setScene(next);
      setLastSavedSnapshot(buildSceneSnapshot(next));
      toast.success(`已发布成功 v${version.versionNo}`);
      onBack();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "发布失败");
    } finally {
      setPublishing(false);
    }
  };

  const updateStep = (nextStep: StepDefinition) => {
    if (readOnly) return;
    setScene((current) => ({
      ...current,
      steps: current.steps.map((step) =>
        step.stepId === nextStep.stepId ? nextStep : step,
      ),
    }));
  };

  const addStep = (type: 'HTTP' | 'SQL') => {
    if (readOnly) return;
    const nextStep = createDefaultStep(type, scene.steps.length);
    setScene((curr) => ({ ...curr, steps: assignExecutionOrders(curr.steps.concat(nextStep)) }));
  };

  const deleteStep = (id: string) => {
    if (readOnly) return;
    setScene((curr) => ({
        ...curr,
        steps: assignExecutionOrders(curr.steps.filter((s) => s.stepId !== id)),
    }));
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2Icon className="text-primary size-8 animate-spin" />
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={0}>
    <div className="flex h-full overflow-hidden">
      <SceneEditorSidebar
        isSidebarExpanded={isSidebarExpanded}
        setIsSidebarExpanded={setIsSidebarExpanded}
        sceneName={scene.sceneName ?? null}
        sceneCode={scene.sceneCode ?? null}
        status={scene.status}
        steps={STEPS}
        currentStep={currentStep}
        navigateToStep={navigateToStep}
        saving={saving}
        publishing={publishing}
        save={save}
        runPublish={runPublish}
        onRun={persistedSceneCode && scene.status === "PUBLISHED" ? () => setShowRunDialog(true) : undefined}
        readOnly={readOnly}
        stepIssueCounts={stepIssueCounts}
      />

      {/* 主内容区域 */}
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        <SceneEditorHeader
          sceneName={scene.sceneName ?? null}
          stepTitle={STEPS[currentStep]?.title ?? "配置中"}
          currentStepIndex={currentStep}
          saving={saving}
          isPublished={persistedSceneCode !== null}
        />

        <main className="flex-1 relative overflow-hidden">
          {currentStep === 2 ? (
            <div className="h-full p-4">
              <LogicOrchestrationStep
                scene={scene}
                httpSources={httpSources}
                sqlSources={sqlSources}
                issues={issues}
                updateStep={updateStep}
                deleteStep={deleteStep}
                addStep={addStep}
                setScene={setScene}
                readOnly={readOnly}
              />
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="mx-auto max-w-5xl p-8">
                {currentStep === 0 && (
                  <div className="animate-in fade-in slide-in-from-left-2 duration-300">
                    <BasicInfoPanel
                      scene={scene}
                      persisted={persistedSceneCode !== null}
                      onChange={setScene}
                      readOnly={readOnly}
                    />
                  </div>
                )}

                {currentStep === 1 && (
                  <div className="animate-in fade-in slide-in-from-left-2 duration-300">
                    <InputSchemaPanel scene={scene} onChange={setScene} readOnly={readOnly} />
                  </div>
                )}

                {currentStep === 3 && (
                  <div className="animate-in fade-in slide-in-from-left-2 duration-300">
                    <ResultMappingPanel scene={scene} onChange={setScene} readOnly={readOnly} />
                  </div>
                )}

                {currentStep === 4 && (
                  <div className="animate-in fade-in slide-in-from-left-2 duration-300">
                    <BatchConfigPanel scene={scene} onChange={setScene} readOnly={readOnly} />
                  </div>
                )}
              </div>
            </ScrollArea>
          )}
        </main>
      </div>

      {/* 执行场景对话框 */}
      {persistedSceneCode && (
        <SceneRunDialog
          scene={scene}
          sceneCode={persistedSceneCode}
          open={showRunDialog}
          onOpenChange={setShowRunDialog}
        />
      )}
    </div>
    </TooltipProvider>
  );
}

function buildSceneSnapshot(scene: SceneDefinition): string {
  return JSON.stringify(toStrictScenePayload(scene));
}

function normalizeScene(scene: SceneDefinition): SceneDefinition {
  return {
    ...scene,
    inputSchema: (scene.inputSchema ?? []).map(field => ({
      ...field,
      children: field.children ?? undefined,
    })),
    batchConfig: scene.batchConfig ?? createDefaultScene().batchConfig,
    resultSchema: scene.resultSchema ?? [],
    resultMapping: normalizeResultMapping(scene.resultMapping),
    errorPolicy: scene.errorPolicy ?? "STOP_ON_ERROR",
    steps: normalizeSteps(scene.steps ?? []),
  };
}

function normalizeSteps(steps: StepDefinition[]): StepDefinition[] {
  return steps
    .map((step, index) => normalizeStep(step, index))
    .sort((left, right) => (left.executionOrder ?? 0) - (right.executionOrder ?? 0))
    .map((step, index) => ({ ...step, executionOrder: index + 1 }));
}

function assignExecutionOrders(steps: StepDefinition[]): StepDefinition[] {
  return steps.map((step, index) => ({ ...step, executionOrder: index + 1 }));
}

function normalizeStep(step: StepDefinition, index: number): StepDefinition {
  const base = {
    stepId: step.stepId,
    stepName: step.stepName ?? null,
    type: step.type,
    executionOrder: step.executionOrder ?? index + 1,
    enabled: step.enabled ?? true,
    dependsOn: step.dependsOn ?? [],
    description: step.description ?? null,
    templateRef: step.templateRef ?? null,
    outputMapping: step.outputMapping ?? {},
    outputMeta: step.outputMeta ?? null,
  };

  if (step.type === "HTTP") {
    return {
      ...base,
      type: "HTTP",
      sourceName: step.sourceName ?? null,
      sysCode: step.sysCode ?? "",
      method: step.method ?? "POST",
      path: step.path ?? "",
      timeoutConfig: step.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
      requestMapping: step.requestMapping ?? {},
      httpParamMapping: step.httpParamMapping ?? {},
      bodySchema: step.bodySchema ?? null,
      responseSchema: step.responseSchema ?? null,
      responseHeadersSchema: step.responseHeadersSchema ?? null,
      responseCookiesSchema: step.responseCookiesSchema ?? null,
      responseHandling: step.responseHandling ?? null,
      errorMapping: step.errorMapping ?? null,
      businessErrorMapping: step.businessErrorMapping ?? null,
      retryPolicy: step.retryPolicy ?? null,
    };
  }

  if (step.type === "SQL") {
    return {
      ...base,
      type: "SQL",
      sourceName: step.sourceName ?? null,
      sysCode: step.sysCode ?? "",
      datasourceCode: step.datasourceCode ?? "",
      operation: step.operation ?? "UPDATE",
      sqlText: step.sqlText ?? "",
      normalizedSql: step.normalizedSql ?? "",
      tables: step.tables ?? [],
      resultFields: step.resultFields ?? [],
      conditionFields: step.conditionFields ?? [],
      parameters: step.parameters ?? [],
      safety: step.safety ?? { requireWhere: true, maxAffectedRows: null },
      paramMapping: step.paramMapping ?? {},
    };
  }

  if (step.type === "ASSERT") {
    return {
      ...base,
      type: "ASSERT",
      assertions: step.assertions ?? [],
    };
  }

  return {
    ...base,
    type: "TRANSFORM",
    assignments: step.assignments ?? {},
  };
}

function normalizeResultMapping(
  raw: Record<string, unknown> | Record<string, string> | undefined,
): Record<string, string> {
  if (!raw) return {};
  return Object.fromEntries(
    Object.entries(raw).map(([k, v]) => [k, formatUnknownValue(v)]),
  );
}
