"use client";

import { AlertTriangleIcon, CheckCircle2Icon, DatabaseIcon, GlobeIcon, ListIcon, EyeIcon, NetworkIcon, PlusIcon, Trash2Icon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { computeStepConfigStatus } from "../common/lib/step-validation";
import type { SceneDefinition, StepDefinition } from "../common/lib/types";

interface StepListViewProps {
  scene: SceneDefinition;
  steps: StepDefinition[];
  onSelectStep: (id: string) => void;
  onDeleteStep: (id: string) => void;
  onAddStep: (type: 'HTTP' | 'SQL') => void;
  onToggleView: () => void;
  readOnly?: boolean;
}

export function StepListView({
  scene,
  steps,
  onSelectStep,
  onDeleteStep,
  onAddStep,
  onToggleView,
  readOnly,
}: StepListViewProps) {
  return (
    <div className="flex flex-col h-full bg-card overflow-hidden">
      <div className="flex items-center justify-between px-6 py-4 border-b bg-muted/5">
        <div className="flex items-center gap-2">
            <ListIcon className="size-4 text-primary" />
            <h4 className="text-sm font-bold">步骤列表视图</h4>
            <Badge variant="secondary" className="text-[10px] ml-2">{steps.length} 个节点</Badge>
        </div>
        <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onToggleView} className="h-8 text-xs gap-2">
                <NetworkIcon className="size-3.5" />
                切换到画布
            </Button>
            {!readOnly && (
              <>
                <div className="w-px h-4 bg-border mx-1" />
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
        ) : (
          <div className="space-y-3">
             {steps.map((step, idx) => {
                const status = computeStepConfigStatus(step, scene);
                return (
                <div
                    key={step.stepId}
                    className={cn(
                        "group flex items-center gap-4 p-4 rounded-xl border bg-background hover:border-primary/40 hover:shadow-md transition-all cursor-pointer",
                        !step.enabled && "opacity-50 border-dashed",
                        !status.complete && step.enabled && "border-red-300 hover:border-red-400"
                    )}
                    onClick={() => onSelectStep(step.stepId)}
                >
                    <div className={cn(
                        "size-10 rounded-full flex items-center justify-center shrink-0 transition-colors",
                        !status.complete && step.enabled ? "bg-red-50" : "bg-muted group-hover:bg-primary/10"
                    )}>
                        <span className={cn(
                            "text-xs font-bold",
                            !status.complete && step.enabled ? "text-red-500" : "text-muted-foreground group-hover:text-primary"
                        )}>{idx + 1}</span>
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
                                        {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty url should show placeholder */}
                                        <span className="font-mono text-[11px] truncate">{step.url || '未配置 URL'}</span>
                                        {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty method should default to POST */}
                                        <span className="opacity-40 ml-1 font-bold">[{step.method || 'POST'}]</span>
                                    </>
                                ) : (
                                    <>
                                        <DatabaseIcon className="size-3 shrink-0" />
                                        <span className="font-mono text-[11px] truncate">
                                            {/* eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty strings should fall through */}
                                            {step.sqlText || step.normalizedSql || step.sqlTemplateCode || '未配置 SQL'}
                                        </span>
                                    </>
                                )}
                            </div>
                            {step.description && !step.description.startsWith('Raw SQL:') && (
                                <div className="text-muted-foreground/60 truncate italic">— {step.description}</div>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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
             })}
          </div>
        )}
      </div>
    </div>
  );
}
