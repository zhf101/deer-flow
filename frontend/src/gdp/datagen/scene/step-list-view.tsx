"use client";

import {
  closestCenter,
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import type { DragEndEvent } from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  DatabaseIcon,
  EyeIcon,
  GlobeIcon,
  GripVerticalIcon,
  ListIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { computeStepConfigStatus } from "../common/lib/step-validation";
import type { SceneDefinition, StepDefinition } from "../common/lib/types";

function nonEmptyText(value: string | null | undefined, fallback: string): string {
  if (value) return value;
  return fallback;
}

interface StepListViewProps {
  scene: SceneDefinition;
  steps: StepDefinition[];
  onSelectStep: (id: string) => void;
  onDeleteStep: (id: string) => void;
  onAddStep: (type: 'HTTP' | 'SQL') => void;
  onReorderSteps: (fromIndex: number, toIndex: number) => void;
  readOnly?: boolean;
}

export function StepListView({
  scene,
  steps,
  onSelectStep,
  onDeleteStep,
  onAddStep,
  onReorderSteps,
  readOnly,
}: StepListViewProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = steps.findIndex((s) => s.stepId === active.id);
    const newIndex = steps.findIndex((s) => s.stepId === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    onReorderSteps(oldIndex, newIndex);
  };

  return (
    <div className="flex flex-col h-full bg-card overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b bg-muted/5">
        <div className="flex items-center gap-2">
            <ListIcon className="size-4 text-primary" />
            <h4 className="text-sm font-bold">步骤列表视图</h4>
            <Badge variant="secondary" className="text-[10px] ml-2">{steps.length} 个节点</Badge>
        </div>
        <div className="flex items-center gap-2">
            {!readOnly && (
              <>
                <Button size="sm" onClick={() => onAddStep('HTTP')} className="h-8 text-xs gap-1.5 bg-blue-600 hover:bg-blue-700">
                    <PlusIcon className="size-3.5" />
                    添加 HTTP
                </Button>
                <Button size="sm" onClick={() => onAddStep('SQL')} className="h-8 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700">
                    <PlusIcon className="size-3.5" />
                    添加 SQL
                </Button>
              </>
            )}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {steps.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-4">
             <div className="p-4 rounded-full bg-muted/50">
                <ListIcon className="size-12 opacity-20" />
             </div>
             <p className="text-sm italic">暂无编排步骤{readOnly ? "" : "，请点击上方按钮添加"}</p>
          </div>
        ) : readOnly ? (
          /* 只读模式：不可拖拽，无手柄 */
          <div className="space-y-3">
            {steps.map((step, idx) => (
              <StepCard
                key={step.stepId}
                scene={scene}
                step={step}
                idx={idx}
                readOnly
                onSelectStep={onSelectStep}
                onDeleteStep={onDeleteStep}
              />
            ))}
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={steps.map((s) => s.stepId)}
              strategy={verticalListSortingStrategy}
            >
              <div className="space-y-3">
                {steps.map((step, idx) => (
                  <SortableStepItem
                    key={step.stepId}
                    scene={scene}
                    step={step}
                    idx={idx}
                    onSelectStep={onSelectStep}
                    onDeleteStep={onDeleteStep}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>
    </div>
  );
}

/** 可拖拽的步骤卡片，包装 useSortable hook。 */
function SortableStepItem({
  scene,
  step,
  idx,
  onSelectStep,
  onDeleteStep,
}: {
  scene: SceneDefinition;
  step: StepDefinition;
  idx: number;
  onSelectStep: (id: string) => void;
  onDeleteStep: (id: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.stepId });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 50 : undefined,
    opacity: isDragging ? 0.5 : undefined,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <StepCard
        scene={scene}
        step={step}
        idx={idx}
        readOnly={false}
        dragHandleProps={{ ...attributes, ...listeners }}
        onSelectStep={onSelectStep}
        onDeleteStep={onDeleteStep}
        isDragging={isDragging}
      />
    </div>
  );
}

/** 步骤卡片 UI，可编辑模式下带拖拽手柄。 */
function StepCard({
  scene,
  step,
  idx,
  readOnly,
  dragHandleProps,
  onSelectStep,
  onDeleteStep,
  isDragging,
}: {
  scene: SceneDefinition;
  step: StepDefinition;
  idx: number;
  readOnly: boolean;
  dragHandleProps?: Record<string, unknown>;
  onSelectStep: (id: string) => void;
  onDeleteStep: (id: string) => void;
  isDragging?: boolean;
}) {
  const status = computeStepConfigStatus(step, scene);
  const executionOrder = step.executionOrder ?? idx + 1;

  return (
    <div
      className={cn(
        "group flex items-center gap-4 p-4 rounded-xl border bg-background hover:border-primary/40 hover:shadow-md transition-all cursor-pointer",
        !step.enabled && "opacity-50 border-dashed",
        !status.complete && step.enabled && "border-red-300 hover:border-red-400",
        isDragging && "shadow-lg ring-2 ring-primary/30",
      )}
      onClick={() => onSelectStep(step.stepId)}
    >
      {/* 拖拽手柄（仅可编辑模式） */}
      {!readOnly && (
        <div
          className="flex items-center cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground transition-colors shrink-0"
          onClick={(e) => e.stopPropagation()}
          {...dragHandleProps}
        >
          <GripVerticalIcon className="size-5" />
        </div>
      )}

      <div className={cn(
          "flex h-12 w-14 shrink-0 flex-col items-center justify-center rounded-md border transition-colors",
          !status.complete && step.enabled ? "border-red-200 bg-red-50" : "border-border bg-muted group-hover:bg-primary/10"
      )}>
          <span className="text-[9px] font-medium text-muted-foreground">执行</span>
          <span className={cn(
              "text-sm font-bold leading-none",
              !status.complete && step.enabled ? "text-red-500" : "text-muted-foreground group-hover:text-primary"
          )}>#{executionOrder}</span>
      </div>

      <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2">
              <Badge variant="outline" className={cn(
                  "text-[9px] uppercase font-bold",
                  step.type === 'HTTP' ? "border-blue-200 text-blue-600 bg-blue-50" : "border-emerald-200 text-emerald-600 bg-emerald-50"
              )}>
                  {step.type}
              </Badge>
              {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty stepName should fall through */}
              <span className="font-bold text-sm truncate">{step.stepName || step.stepId}</span>
              {!step.enabled && (
                  <Badge variant="outline" className="text-[8px] text-muted-foreground border-dashed">已禁用</Badge>
              )}
              {step.enabled && status.complete && (
                  <CheckCircle2Icon className="size-3.5 text-emerald-500 shrink-0" />
              )}
              {step.enabled && !status.complete && (
                  <div className="flex items-center gap-1 shrink-0">
                      <AlertTriangleIcon className="size-3.5 text-red-500" />
                      <span className="text-[10px] text-red-500 font-medium">{status.errorCount}</span>
                  </div>
              )}
              {status.outputCount > 0 && (
                  <Badge variant="secondary" className="text-[9px] ml-auto shrink-0">
                      {status.outputCount} 输出
                  </Badge>
              )}
          </div>

          <div className="flex items-center gap-4 text-xs">
              <div className="flex items-center gap-1.5 text-muted-foreground truncate max-w-md bg-muted/30 px-2 py-0.5 rounded">
                  {step.type === 'HTTP' ? (
                      <>
                          <GlobeIcon className="size-3 shrink-0" />
                          <span className="font-mono text-[11px] truncate">{nonEmptyText(step.path, '未配置 URL')}</span>
                          <span className="opacity-40 ml-1 font-bold">[{step.method}]</span>
                      </>
                  ) : step.type === 'SQL' ? (
                      <>
                          <DatabaseIcon className="size-3 shrink-0" />
                          <span className="font-mono text-[11px] truncate">
                              {nonEmptyText(step.sqlText, nonEmptyText(step.normalizedSql, '未配置 SQL'))}
                          </span>
                      </>
                  ) : (
                      <span className="font-mono text-[11px] truncate">
                        {step.type === "ASSERT" ? `${step.assertions.length} 条断言` : `${Object.keys(step.assignments).length} 个赋值`}
                      </span>
                  )}
              </div>
              {step.description ? !step.description.startsWith('Raw SQL:') && (
                  <div className="text-muted-foreground/60 truncate italic">— {step.description}</div>
              ) : null}
          </div>
      </div>

      <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" className="h-8 w-8">
              <EyeIcon className="size-4" />
          </Button>
          {!readOnly && (
            <Button
                variant="ghost"
                size="icon-sm"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                onClick={(e) => {
                    e.stopPropagation();
                    onDeleteStep(step.stepId);
                }}
            >
                <Trash2Icon className="size-4" />
            </Button>
          )}
      </div>
    </div>
  );
}
