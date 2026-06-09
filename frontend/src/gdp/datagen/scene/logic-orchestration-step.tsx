import {
  DatabaseIcon,
  GlobeIcon,
  ListIcon,
  NetworkIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

import type {
  HttpSourceResponse,
  SceneDefinition,
  SqlSourceResponse,
  StepDefinition,
  ValidationIssue,
} from "../common/lib/types";

import { FlowCanvas } from "./flow/flow-canvas";
import { StepConfigPanel } from "./step-config-panel";
import { StepListView } from "./step-list-view";

interface LogicOrchestrationStepProps {
  scene: SceneDefinition;
  orchView: "list" | "canvas";
  setOrchView: (view: "list" | "canvas") => void;
  httpSources?: HttpSourceResponse[];
  sqlSources?: SqlSourceResponse[];
  issues?: ValidationIssue[];
  updateStep: (step: StepDefinition) => void;
  deleteStep: (id: string) => void;
  addStep: (type: "HTTP" | "SQL") => void;
  setScene: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

/** 表示“显示画布/列表视图”的哨兵值。 */
const CANVAS_TAB = "__canvas__";

export function LogicOrchestrationStep({
  scene,
  orchView,
  setOrchView,
  httpSources,
  sqlSources,
  issues = [],
  updateStep,
  deleteStep,
  addStep,
  setScene,
  readOnly,
}: LogicOrchestrationStepProps) {
  // 已打开步骤标签的有序 ID 列表（stepId 字符串）。
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  // 当前激活的标签：stepId 或 CANVAS_TAB。
  const [activeTabId, setActiveTabId] = useState<string>(CANVAS_TAB);

  // 解析当前激活的步骤定义（当步骤标签激活时）。
  const activeStep = useMemo(
    () =>
      activeTabId === CANVAS_TAB
        ? null
        : scene.steps.find((s) => s.stepId === activeTabId) ?? null,
    [scene.steps, activeTabId],
  );

  // 打开或激活步骤标签。
  const openStep = useCallback((stepId: string) => {
    setOpenTabs((prev) => (prev.includes(stepId) ? prev : [...prev, stepId]));
    setActiveTabId(stepId);
  }, []);

  // 关闭步骤标签，并激活相邻标签或回退到画布。
  const closeTab = useCallback(
    (stepId: string) => {
      setOpenTabs((prev) => {
        const idx = prev.indexOf(stepId);
        if (idx === -1) return prev;
        const next = [...prev];
        next.splice(idx, 1);

        // 如果关闭的是当前标签，则激活相邻标签或画布。
        if (activeTabId === stepId) {
          if (next.length > 0) {
            const neighbor = next[Math.min(idx, next.length - 1)] ?? CANVAS_TAB;
            setActiveTabId(neighbor);
          } else {
            setActiveTabId(CANVAS_TAB);
          }
        }
        return next;
      });
    },
    [activeTabId],
  );

  // 删除步骤：先移除标签，再调用父级删除逻辑。
  const handleDeleteStep = useCallback(
    (id: string) => {
      setOpenTabs((prev) => prev.filter((t) => t !== id));
      if (activeTabId === id) {
        setActiveTabId(CANVAS_TAB);
      }
      deleteStep(id);
    },
    [activeTabId, deleteStep],
  );

  // 新增步骤：委托父级创建，然后打开新标签。
  const handleAddStep = useCallback(
    (type: "HTTP" | "SQL") => {
      addStep(type);
      // addStep 执行后，新步骤会位于 scene.steps 末尾。
      // 这里计算预期的 stepId，用于打开对应标签。
      const idx = scene.steps.length;
      const stepId = `${type.toLowerCase()}${idx + 1}`;
      openStep(stepId);
    },
    [addStep, scene.steps.length, openStep],
  );

  // 点击画布或列表中的节点时，打开或激活对应标签。
  const handleSelectStep = useCallback(
    (stepId: string | null) => {
      if (stepId) {
        openStep(stepId);
      }
    },
    [openStep],
  );

  // 拖拽重排序：将步骤从 fromIndex 移动到 toIndex，重新赋值 executionOrder。
  // 校验依赖关系：不允许将步骤拖到其依赖项之前。
  const handleReorderSteps = useCallback(
    (fromIndex: number, toIndex: number) => {
      if (readOnly || fromIndex === toIndex) return;
      const nextSteps = [...scene.steps];
      const [moved] = nextSteps.splice(fromIndex, 1);
      if (!moved) return;
      nextSteps.splice(toIndex, 0, moved);

      // 检查重排序后是否违反依赖关系（步骤不能出现在其依赖项之前）
      const idToIndex = new Map(nextSteps.map((s, i) => [s.stepId, i]));
      const violation = nextSteps.find((step, idx) =>
        step.dependsOn.some((depId) => {
          const depIdx = idToIndex.get(depId);
          return depIdx !== undefined && depIdx > idx;
        }),
      );
      if (violation) {
        toast.error(`无法移动：步骤「${violation.stepName || violation.stepId}」不能出现在其依赖项之前`);
        return;
      }

      setScene({ ...scene, steps: assignExecutionOrders(nextSteps) });
    },
    [readOnly, scene, setScene],
  );

  // 画布中当前被选中并高亮的步骤。
  const selectedStepId =
    activeTabId !== CANVAS_TAB && openTabs.includes(activeTabId)
      ? activeTabId
      : null;

  return (
    <div className="h-full animate-in fade-in slide-in-from-left-2 duration-300 flex flex-col overflow-hidden rounded-lg border bg-card">
      {/* ── 标签栏 ── */}
      <div className="flex items-center border-b bg-muted/5 shrink-0">
        {/* 画布标签（始终存在） */}
        <button
          type="button"
          onClick={() => setActiveTabId(CANVAS_TAB)}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors shrink-0",
            activeTabId === CANVAS_TAB
              ? "border-primary text-foreground bg-background"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50",
          )}
        >
          <NetworkIcon className="size-3.5" />
          编排画布
          <Badge variant="secondary" className="text-[9px] h-4 px-1.5 ml-0.5">
            {orchView === "canvas" ? "画布" : "列表"}
          </Badge>
        </button>

        {/* 步骤标签（可滚动） */}
        <div className="flex items-center overflow-x-auto min-w-0 flex-1 scrollbar-thin">
          {openTabs.map((stepId) => {
            const step = scene.steps.find((s) => s.stepId === stepId);
            if (!step) return null;
            const isHttp = step.type === "HTTP";
            const isActive = activeTabId === stepId;

            return (
              <button
                key={stepId}
                type="button"
                onClick={() => setActiveTabId(stepId)}
                className={cn(
                  "group flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 transition-colors shrink-0 max-w-[200px]",
                  isActive
                    ? "border-primary text-foreground bg-background"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50",
                )}
              >
                {isHttp ? (
                  <GlobeIcon className="size-3 text-blue-500 shrink-0" />
                ) : (
                  <DatabaseIcon className="size-3 text-emerald-500 shrink-0" />
                )}
                {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty stepName should fall through */}
                <span className="truncate">{step.stepName || step.stepId}</span>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(stepId);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.stopPropagation();
                      closeTab(stepId);
                    }
                  }}
                  className={cn(
                    "ml-1 rounded-sm p-0.5 shrink-0 transition-colors",
                    isActive
                      ? "opacity-60 hover:opacity-100 hover:bg-muted"
                      : "opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:bg-muted",
                  )}
                >
                  <XIcon className="size-3" />
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 内容区域 ── */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        {activeTabId === CANVAS_TAB ? (
          /* 画布或列表视图 */
          <div className="h-full">
            {orchView === "list" ? (
              <StepListView
                scene={scene}
                steps={scene.steps}
                onSelectStep={handleSelectStep}
                onDeleteStep={handleDeleteStep}
                onAddStep={handleAddStep}
                onReorderSteps={handleReorderSteps}
                onToggleView={() => setOrchView("canvas")}
                readOnly={readOnly}
              />
            ) : (
              <div className="h-full relative">
                <FlowCanvas
                  scene={scene}
                  selectedStepId={selectedStepId}
                  onSceneChange={setScene}
                  onSelectStep={handleSelectStep}
                  readOnly={readOnly}
                />
                <div className="absolute top-4 right-4 z-10">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setOrchView("list")}
                    className="gap-2 shadow-md"
                  >
                    <ListIcon className="size-3.5" />
                    切换到列表
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : activeStep ? (
          /* 步骤配置面板 */
          <ScrollArea className="h-full">
            <div className="mx-auto max-w-[1200px] p-4">
              <StepConfigPanel
                scene={scene}
                step={activeStep}
                steps={scene.steps}
                httpSources={httpSources}
                sqlSources={sqlSources}
                stepIssues={issues.filter((i) => i.field.startsWith(`step:${activeStep.stepId}`))}
                onChange={updateStep}
                onDelete={handleDeleteStep}
                readOnly={readOnly}
              />
            </div>
          </ScrollArea>
        ) : (
          /* 兜底处理：步骤已删除但标签仍引用该步骤 */
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
            该步骤已被删除
          </div>
        )}
      </div>
    </div>
  );
}

function assignExecutionOrders(steps: StepDefinition[]): StepDefinition[] {
  return steps.map((step, index) => ({ ...step, executionOrder: index + 1 }));
}
