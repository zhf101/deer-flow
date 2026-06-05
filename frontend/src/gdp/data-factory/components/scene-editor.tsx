"use client";

import {
  FileJsonIcon,
  InfoIcon,
  LayoutGridIcon,
  LayersIcon,
  Loader2Icon,
  Settings2Icon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ScrollArea } from "@/components/ui/scroll-area";
import { TooltipProvider } from "@/components/ui/tooltip";

import {
  createScene,
  getScene,
  listSqlTemplates,
  publishScene,
  updateScene,
} from "../lib/api";
import { createDefaultScene, createDefaultStep } from "../lib/defaults";
import type {
  SceneDefinition,
  SqlTemplateResponse,
  StepDefinition,
  ValidationIssue,
} from "../lib/types";
import { validateSceneDraft } from "../lib/validation";

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
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [sqlTemplates, setSqlTemplates] = useState<SqlTemplateResponse[]>([]);
  const [loading, setLoading] = useState(!!sceneCode);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(true);
  const [orchView, setOrchView] = useState<"list" | "canvas">("list");
  const [showRunDialog, setShowRunDialog] = useState(false);

  useEffect(() => {
    if (sceneCode) {
      setLoading(true);
      getScene(sceneCode)
        .then((data) => {
          setScene(normalizeScene(data));
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
    }
  }, [sceneCode, onBack]);

  useEffect(() => {
    listSqlTemplates()
      .then(setSqlTemplates)
      .catch(() => setSqlTemplates([]));
  }, []);

  useEffect(() => {
    setIssues(validateSceneDraft(scene));
  }, [scene]);

  const save = async (showToast = true): Promise<string | null> => {
    if (readOnly) return persistedSceneCode;
    if (!scene.sceneCode || !scene.sceneName) {
        if (showToast) toast.error("请先填写场景编码和名称");
        return null;
    }
    
    setSaving(true);
    try {
      const version = persistedSceneCode
        ? await updateScene(persistedSceneCode, scene)
        : await createScene(scene);
      const next = normalizeScene(version.definition);
      setScene(next);
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
      if (!readOnly) await save(false);
      setCurrentStep(idx);
  };

  const runPublish = async () => {
    if (readOnly) return;
    const code = persistedSceneCode ?? (await save());
    if (!code) return;
    
    const errors = issues.filter(i => i.level === 'ERROR');
    if (errors.length > 0) {
        toast.error(`发布校验未通过: ${errors[0]?.message ?? '未知错误'}`);
        return;
    }

    setPublishing(true);
    try {
      const version = await publishScene(code);
      setScene(normalizeScene(version.definition));
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
    setScene((curr) => ({ ...curr, steps: curr.steps.concat(nextStep) }));
  };

  const deleteStep = (id: string) => {
    if (readOnly) return;
    setScene((curr) => ({
        ...curr,
        steps: curr.steps.filter((s) => s.stepId !== id),
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
        onBack={onBack}
        sceneName={scene.sceneName || null}
        sceneCode={scene.sceneCode || null}
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
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        <SceneEditorHeader
          sceneName={scene.sceneName || null}
          stepTitle={STEPS[currentStep]?.title || "配置中"}
          currentStepIndex={currentStep}
          saving={saving}
          isPublished={persistedSceneCode !== null}
        />

        <main className="flex-1 relative overflow-hidden">
          {currentStep === 2 ? (
            <div className="h-full p-4">
              <LogicOrchestrationStep
                scene={scene}
                orchView={orchView}
                setOrchView={setOrchView}
                sqlTemplates={sqlTemplates}
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

function normalizeScene(scene: SceneDefinition): SceneDefinition {
  return {
    ...scene,
    inputSchema: (scene.inputSchema || []).map(field => ({
      ...field,
      children: field.children || undefined,
    })),
    batchConfig: scene.batchConfig || createDefaultScene().batchConfig,
    resultSchema: scene.resultSchema || [],
    resultMapping: normalizeResultMapping(scene.resultMapping),
    errorPolicy: scene.errorPolicy || "STOP_ON_ERROR",
    steps: (scene.steps || []).map((step) => ({
      ...step,
      requestMapping: step.requestMapping || {},
      outputMapping: step.outputMapping || {},
      paramMapping: step.paramMapping || {},
      assertions: step.assertions || [],
      assignments: step.assignments || {},
      dependsOn: step.dependsOn || [],
      enabled: step.enabled ?? true,
    })),
  };
}

function normalizeResultMapping(
  raw: Record<string, unknown> | Record<string, string> | undefined,
): Record<string, string> {
  if (!raw) return {};
  return Object.fromEntries(
    Object.entries(raw).map(([k, v]) => [k, typeof v === "string" ? v : String(v ?? "")]),
  );
}
