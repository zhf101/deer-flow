import {
  DatabaseIcon,
  GlobeIcon,
  ListIcon,
  NetworkIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

import type {
  SceneDefinition,
  SqlTemplateResponse,
  StepDefinition,
} from "../lib/types";

import { FlowCanvas } from "./flow-canvas";
import { StepConfigPanel } from "./step-config-panel";
import { StepListView } from "./step-list-view";

interface LogicOrchestrationStepProps {
  scene: SceneDefinition;
  orchView: "list" | "canvas";
  setOrchView: (view: "list" | "canvas") => void;
  sqlTemplates: SqlTemplateResponse[];
  updateStep: (step: StepDefinition) => void;
  deleteStep: (id: string) => void;
  addStep: (type: "HTTP" | "SQL") => void;
  setScene: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

/** Sentinel value meaning "show the canvas/list view". */
const CANVAS_TAB = "__canvas__";

export function LogicOrchestrationStep({
  scene,
  orchView,
  setOrchView,
  sqlTemplates,
  updateStep,
  deleteStep,
  addStep,
  setScene,
  readOnly,
}: LogicOrchestrationStepProps) {
  // Ordered list of open step-tab IDs (stepId strings).
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  // Currently active tab: a stepId or CANVAS_TAB.
  const [activeTabId, setActiveTabId] = useState<string>(CANVAS_TAB);

  // Resolve the active step definition (if a step tab is active).
  const activeStep = useMemo(
    () =>
      activeTabId === CANVAS_TAB
        ? null
        : scene.steps.find((s) => s.stepId === activeTabId) ?? null,
    [scene.steps, activeTabId],
  );

  // Open or activate a step tab.
  const openStep = useCallback((stepId: string) => {
    setOpenTabs((prev) => (prev.includes(stepId) ? prev : [...prev, stepId]));
    setActiveTabId(stepId);
  }, []);

  // Close a step tab, activating its neighbor or falling back to canvas.
  const closeTab = useCallback(
    (stepId: string) => {
      setOpenTabs((prev) => {
        const idx = prev.indexOf(stepId);
        if (idx === -1) return prev;
        const next = [...prev];
        next.splice(idx, 1);

        // If the closed tab was active, activate neighbor or canvas.
        if (activeTabId === stepId) {
          if (next.length > 0) {
            const neighbor = next[Math.min(idx, next.length - 1)];
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

  // Delete a step: remove its tab then call the parent delete.
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

  // Add a step: delegate to parent, then open the new tab.
  const handleAddStep = useCallback(
    (type: "HTTP" | "SQL") => {
      addStep(type);
      // The new step will be the last in scene.steps after addStep runs.
      // We compute the expected stepId to open its tab.
      const idx = scene.steps.length;
      const stepId = `${type.toLowerCase()}${idx + 1}`;
      openStep(stepId);
    },
    [addStep, scene.steps.length, openStep],
  );

  // When clicking a node in canvas or list, open/activate its tab.
  const handleSelectStep = useCallback(
    (stepId: string | null) => {
      if (stepId) {
        openStep(stepId);
      }
    },
    [openStep],
  );

  // For canvas: which step is "selected" (highlighted on canvas).
  const selectedStepId =
    activeTabId !== CANVAS_TAB && openTabs.includes(activeTabId)
      ? activeTabId
      : null;

  return (
    <div className="h-full animate-in fade-in slide-in-from-left-2 duration-300 flex flex-col overflow-hidden rounded-lg border bg-card">
      {/* ── Tab Bar ── */}
      <div className="flex items-center border-b bg-muted/5 shrink-0">
        {/* Canvas tab (always present) */}
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

        {/* Step tabs (scrollable) */}
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

      {/* ── Content Area ── */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        {activeTabId === CANVAS_TAB ? (
          /* Canvas or List view */
          <div className="h-full">
            {orchView === "list" ? (
              <StepListView
                steps={scene.steps}
                onSelectStep={handleSelectStep}
                onDeleteStep={handleDeleteStep}
                onAddStep={handleAddStep}
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
          /* Step config panel */
          <ScrollArea className="h-full">
            <div className="mx-auto max-w-[1200px] p-4">
              <StepConfigPanel
                scene={scene}
                step={activeStep}
                steps={scene.steps}
                sqlTemplates={sqlTemplates}
                onChange={updateStep}
                onDelete={handleDeleteStep}
                readOnly={readOnly}
              />
            </div>
          </ScrollArea>
        ) : (
          /* Fallback: step was deleted but tab still referenced */
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
            该步骤已被删除
          </div>
        )}
      </div>
    </div>
  );
}
