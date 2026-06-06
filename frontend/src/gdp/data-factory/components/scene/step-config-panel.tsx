"use client";

import { ChevronDownIcon, ChevronRightIcon, LinkIcon, PlusIcon, Trash2Icon, UnlinkIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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

import type {
  HttpSourceResponse,
  SceneDefinition,
  SqlSourceResponse,
  SqlTemplateResponse,
  StepDefinition,
} from "../../lib/types";

import { HttpStepForm } from "../http/http-step-form";
import { SqlStepForm } from "../sql/sql-step-form";

interface StepConfigPanelProps {
  scene: SceneDefinition;
  step: StepDefinition | null;
  steps: StepDefinition[];
  sqlTemplates: SqlTemplateResponse[];
  httpSources?: HttpSourceResponse[];
  sqlSources?: SqlSourceResponse[];
  onChange: (step: StepDefinition) => void;
  onDelete: (stepId: string) => void;
  readOnly?: boolean;
}

export function StepConfigPanel({
  scene,
  step,
  steps,
  sqlTemplates,
  httpSources = [],
  sqlSources = [],
  onChange,
  onDelete,
  readOnly,
}: StepConfigPanelProps) {
  if (!step) {
    return (
      <div className="text-muted-foreground rounded-md border border-dashed p-8 text-center text-sm">
        选择画布中的步骤进行配置
      </div>
    );
  }

  // Determine if step uses reference mode (has httpSourceCode or sqlSourceCode set)
  const isRefMode =
    (step.type === "HTTP" && step.httpSourceCode !== null && step.httpSourceCode !== undefined) ||
    (step.type === "SQL" && step.sqlSourceCode !== null && step.sqlSourceCode !== undefined);

  // Available steps for dependency: must be in the scene and not the current step
  const availableSteps = steps.filter(s => s.stepId !== step.stepId);
  const [basicOpen, setBasicOpen] = useState(false);
  const [depsOpen, setDepsOpen] = useState(true);

  const enabledHttpSources = httpSources.filter((s) => s.status === "ENABLED");
  const enabledSqlSources = sqlSources.filter((s) => s.status === "ENABLED");

  return (
    <div className={cn("space-y-3", readOnly && "pointer-events-none opacity-75")}>
      {/* 1. Basic Step Info (collapsible) */}
      <Collapsible open={basicOpen} onOpenChange={setBasicOpen}>
        <div className="flex items-center justify-between w-full py-2 border-b">
          <CollapsibleTrigger className="flex items-center gap-2 flex-1 min-w-0">
            {basicOpen ? (
              <ChevronDownIcon className="size-4 text-muted-foreground" />
            ) : (
              <ChevronRightIcon className="size-4 text-muted-foreground" />
            )}
            <span className="text-sm font-bold tracking-tight truncate">{step.stepName || step.stepId}</span>
          </CollapsibleTrigger>
          <Switch
            checked={step.enabled}
            disabled={readOnly}
            onCheckedChange={(checked) =>
              onChange({ ...step, enabled: checked })
            }
          />
        </div>

        <CollapsibleContent className="space-y-3 pt-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-muted-foreground uppercase">节点 ID (唯一)</label>
              <Input
                value={step.stepId}
                disabled={readOnly}
                readOnly={readOnly}
                onChange={(event) => onChange({ ...step, stepId: event.target.value })}
                className="h-8 font-mono text-[10px]"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-bold text-muted-foreground uppercase">展示名称</label>
              <Input
                value={step.stepName ?? ""}
                disabled={readOnly}
                readOnly={readOnly}
                onChange={(event) =>
                  onChange({ ...step, stepName: event.target.value })
                }
                placeholder="e.g. 用户登录"
                className="h-8 text-[10px]"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <label className="text-[10px] font-bold text-muted-foreground uppercase">逻辑说明</label>
              <Textarea
                value={step.description ?? ""}
                disabled={readOnly}
                readOnly={readOnly}
                onChange={(event) =>
                  onChange({ ...step, description: event.target.value })
                }
                className="min-h-12 resize-none text-[10px]"
                placeholder="简述此节点的业务逻辑..."
              />
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* 2. Dependency Management (collapsible) */}
      <Collapsible open={depsOpen} onOpenChange={setDepsOpen}>
        <div className="flex items-center justify-between w-full py-2 border-b">
          <CollapsibleTrigger className="flex items-center gap-2 flex-1 min-w-0">
            {depsOpen ? (
              <ChevronDownIcon className="size-4 text-muted-foreground" />
            ) : (
              <ChevronRightIcon className="size-4 text-muted-foreground" />
            )}
            <h4 className="text-sm font-bold">引用其他节点变量</h4>
            {step.dependsOn.length > 0 && (
              <span className="rounded-full bg-muted px-1.5 text-[9px] font-bold text-muted-foreground">
                {step.dependsOn.length}
              </span>
            )}
          </CollapsibleTrigger>
          {!readOnly && (
            <Popover>
                <PopoverTrigger asChild>
                    <Button variant="outline" size="sm" className="h-7 text-[10px] gap-1 border-dashed">
                        <PlusIcon className="size-3" />
                        添加依赖节点
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[220px] p-0" align="end">
                    <div className="max-h-[300px] overflow-auto p-1 space-y-1">
                        {availableSteps.length > 0 ? (
                            availableSteps.map(s => {
                                const isSelected = step.dependsOn.includes(s.stepId);
                                const typeName =
                                  s.type === "HTTP" ? "HTTP"
                                  : s.type === "SQL" ? "SQL"
                                  : s.type;
                                return (
                                    <button
                                        key={s.stepId}
                                        onClick={() => {
                                            const next = isSelected
                                                ? step.dependsOn.filter(id => id !== s.stepId)
                                                : [...step.dependsOn, s.stepId];
                                            onChange({ ...step, dependsOn: next });
                                        }}
                                        className={cn(
                                            "w-full text-left px-3 py-2 rounded-md transition-colors flex items-center gap-2 border text-xs",
                                            isSelected ? "bg-primary/10 border-primary/20" : "hover:bg-muted border-transparent"
                                        )}
                                    >
                                        {isSelected && <span className="text-primary">✓</span>}
                                        <span className="font-medium">{typeName}-{s.stepName ?? s.stepId}</span>
                                    </button>
                                );
                            })
                        ) : (
                            <div className="p-4 text-center text-[10px] text-muted-foreground italic">暂无可依赖的节点</div>
                        )}
                    </div>
                </PopoverContent>
            </Popover>
          )}
        </div>

        <CollapsibleContent className="space-y-2 pt-3">
          <div className="space-y-2">
            {step.dependsOn.length > 0 ? (
                <div className="rounded-md border overflow-hidden">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="px-2 py-1.5 text-left font-medium w-16">类型</th>
                        <th className="px-2 py-1.5 text-left font-medium w-28">展示名称</th>
                        <th className="px-2 py-1.5 text-left font-medium">接口/SQL</th>
                        <th className="px-2 py-1.5 text-left font-medium">逻辑说明</th>
                        {!readOnly && <th className="px-2 py-1.5 w-8" />}
                      </tr>
                    </thead>
                    <tbody>
                      {step.dependsOn.map(id => {
                        const s = steps.find(item => item.stepId === id);
                        if (!s) return null;
                        const urlOrSql =
                          s.type === "HTTP"
                            ? s.httpSourceCode
                              ? `ref: ${s.httpSourceCode}`
                              : s.url ?? ""
                            : s.type === "SQL"
                              ? s.sqlSourceCode
                                ? `ref: ${s.sqlSourceCode}`
                                : s.sqlTemplateCode ?? ""
                              : "";
                        return (
                          <tr key={id} className="border-b last:border-b-0">
                            <td className="px-2 py-1.5">
                              <Badge variant="outline" className="text-[8px] h-4 py-0 uppercase">
                                {s.type}
                              </Badge>
                            </td>
                            <td className="px-2 py-1.5 font-medium">
                              {s.stepName ?? s.stepId}
                            </td>
                            <td className="px-2 py-1.5 font-mono text-muted-foreground truncate max-w-[180px]" title={urlOrSql}>
                              {urlOrSql || <span className="italic text-muted-foreground/60">未配置</span>}
                            </td>
                            <td className="px-2 py-1.5 text-muted-foreground truncate max-w-[180px]" title={s.description ?? ""}>
                              {s.description ?? <span className="italic text-muted-foreground/60">无</span>}
                            </td>
                            {!readOnly && (
                              <td className="px-2 py-1.5 text-center">
                                <button
                                  onClick={() => onChange({ ...step, dependsOn: step.dependsOn.filter(d => d !== id) })}
                                  className="text-muted-foreground hover:text-destructive transition-colors"
                                >
                                  <Trash2Icon className="size-3" />
                                </button>
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
            ) : (
                <div className="text-center py-4 border border-dashed rounded-lg text-[10px] text-muted-foreground italic">
                    该节点暂未配置前序依赖。建议显式声明依赖关系。
                </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* 3. Detailed Logic Config */}
      <div>
        {/* Mode toggle for HTTP / SQL steps */}
        {(step.type === "HTTP" || step.type === "SQL") && !readOnly && (
          <div className="flex items-center gap-2 mb-3 pb-2 border-b">
            <span className="text-[10px] font-bold text-muted-foreground uppercase">配置模式</span>
            <Button
              variant={isRefMode ? "default" : "outline"}
              size="sm"
              className="h-6 text-[10px] gap-1 px-2"
              onClick={() => {
                if (step.type === "HTTP") {
                  onChange({ ...step, httpSourceCode: "", httpParamMapping: {} });
                } else {
                  onChange({ ...step, sqlSourceCode: "", sqlParamMapping: {} });
                }
              }}
            >
              <LinkIcon className="size-3" /> 引用配置
            </Button>
            <Button
              variant={!isRefMode ? "default" : "outline"}
              size="sm"
              className="h-6 text-[10px] gap-1 px-2"
              onClick={() => {
                if (step.type === "HTTP") {
                  onChange({ ...step, httpSourceCode: null, httpParamMapping: {} });
                } else {
                  onChange({ ...step, sqlSourceCode: null, sqlParamMapping: {} });
                }
              }}
            >
              <UnlinkIcon className="size-3" /> 内联配置
            </Button>
          </div>
        )}

        {/* Reference mode: HTTP */}
        {step.type === "HTTP" && step.httpSourceCode !== null && step.httpSourceCode !== undefined && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">HTTP 接口配置</Label>
              <Select
                value={step.httpSourceCode || ""}
                onValueChange={(v) => onChange({ ...step, httpSourceCode: v })}
                disabled={readOnly}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="选择 HTTP 接口..." />
                </SelectTrigger>
                <SelectContent>
                  {enabledHttpSources.map((s) => (
                    <SelectItem key={s.sourceCode} value={s.sourceCode}>
                      {s.sourceName} ({s.method} {s.path})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {step.httpSourceCode && (
                <p className="text-[10px] text-muted-foreground">
                  引用接口: {enabledHttpSources.find((s) => s.sourceCode === step.httpSourceCode)?.sourceName || step.httpSourceCode}
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">参数映射 (JSON)</Label>
              <p className="text-[9px] text-muted-foreground">
                运行时参数覆盖，如 {"{"} &quot;userId&quot;: &quot;$&#123;input.userId&#125;&quot; {"}"}
              </p>
              <Textarea
                className="font-mono text-[10px]"
                rows={4}
                disabled={readOnly}
                value={JSON.stringify(step.httpParamMapping || {}, null, 2)}
                onChange={(e) => {
                  try { onChange({ ...step, httpParamMapping: JSON.parse(e.target.value) }); }
                  catch { /* ignore parse errors while typing */ }
                }}
              />
            </div>
          </div>
        )}

        {/* Reference mode: SQL */}
        {step.type === "SQL" && step.sqlSourceCode !== null && step.sqlSourceCode !== undefined && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">SQL 配置</Label>
              <Select
                value={step.sqlSourceCode || ""}
                onValueChange={(v) => onChange({ ...step, sqlSourceCode: v })}
                disabled={readOnly}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="选择 SQL 配置..." />
                </SelectTrigger>
                <SelectContent>
                  {enabledSqlSources.map((s) => (
                    <SelectItem key={s.sourceCode} value={s.sourceCode}>
                      {s.sourceName} ({s.operation})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {step.sqlSourceCode && (
                <p className="text-[10px] text-muted-foreground">
                  引用 SQL: {enabledSqlSources.find((s) => s.sourceCode === step.sqlSourceCode)?.sourceName || step.sqlSourceCode}
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">参数映射 (JSON)</Label>
              <p className="text-[9px] text-muted-foreground">
                运行时参数覆盖，如 {"{"} &quot;orderId&quot;: &quot;$&#123;steps.createOrder.outputs.orderNo&#125;&quot; {"}"}
              </p>
              <Textarea
                className="font-mono text-[10px]"
                rows={4}
                disabled={readOnly}
                value={JSON.stringify(step.sqlParamMapping || {}, null, 2)}
                onChange={(e) => {
                  try { onChange({ ...step, sqlParamMapping: JSON.parse(e.target.value) }); }
                  catch { /* ignore */ }
                }}
              />
            </div>
          </div>
        )}

        {/* Inline mode: existing forms */}
        {step.type === "HTTP" && (step.httpSourceCode === null || step.httpSourceCode === undefined) ? (
          <HttpStepForm scene={scene} step={step} onChange={onChange} />
        ) : null}
        {step.type === "SQL" && (step.sqlSourceCode === null || step.sqlSourceCode === undefined) ? (
          <SqlStepForm
            scene={scene}
            step={step}
            sqlTemplates={sqlTemplates}
            onChange={onChange}
          />
        ) : null}
      </div>

      {/* Delete Footer */}
      {!readOnly && (
        <div className="flex justify-end border-t pt-3">
          <Button
            variant="destructive"
            size="sm"
            onClick={() => onDelete(step.stepId)}
            className="gap-2 h-8 text-xs"
          >
            <Trash2Icon className="size-3.5" />
            删除此节点
          </Button>
        </div>
      )}
    </div>
  );
}
