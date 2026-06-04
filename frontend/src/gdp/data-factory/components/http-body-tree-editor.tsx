"use client";

import { InfoIcon, PlusIcon, Trash2Icon, VariableIcon, ZapIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { INPUT_FIELD_TYPES } from "../lib/defaults";
import type { InputFieldDefinition, InputFieldType, SceneDefinition, StepDefinition } from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";

import { VariableSelector } from "./variable-selector";

interface HttpBodyTreeEditorProps {
  scene: SceneDefinition;
  step: StepDefinition;
  onChange: (updates: Partial<StepDefinition>) => void;
}

export function HttpBodyTreeEditor({ scene, step, onChange }: HttpBodyTreeEditorProps) {
  const schema = step.bodySchema || [];
  const mapping = step.bodyMapping || {};

  const updateSchema = (newSchema: InputFieldDefinition[]) => {
    onChange({ bodySchema: newSchema });
  };

  const updateMapping = (path: string, value: any) => {
    const nextMapping = { ...mapping };
    nextMapping[path] = value;
    onChange({ bodyMapping: nextMapping });
  };

  const addTopLevelField = () => {
    const next = [...schema, {
      name: `field_${schema.length + 1}`,
      type: "string" as InputFieldType,
      required: false,
      batchEnabled: false,
    }];
    updateSchema(next);
  };

  const autoFill = () => {
    const nextMapping = { ...mapping };
    let filledCount = 0;

    const findMatch = (name: string) => {
        // Search in input schema
        const inputMatch = scene.inputSchema.find(f => f.name === name);
        if (inputMatch) return `\${input.${name}}`;
        
        // Search in previous steps
        const currentIdx = scene.steps.findIndex(s => s.stepId === step.stepId);
        const prevSteps = currentIdx >= 0 ? scene.steps.slice(0, currentIdx) : scene.steps;
        for (const s of prevSteps) {
            if (s.outputMapping && s.outputMapping[name]) {
                return `\${steps.${s.stepId}.outputs.${name}}`;
            }
        }
        return null;
    };

    const traverse = (fields: InputFieldDefinition[]) => {
        fields.forEach(f => {
            const match = findMatch(f.name);
            if (match && !nextMapping[f.name]) {
                nextMapping[f.name] = match;
                filledCount++;
            }
            if (f.children) traverse(f.children);
        });
    };

    traverse(schema);
    if (filledCount > 0) {
        onChange({ bodyMapping: nextMapping });
        toast.success(`自动关联了 ${filledCount} 个匹配字段`);
    } else {
        toast.info("未发现可自动关联的字段名");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">请求报文结构 (Body Schema)</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <InfoIcon className="text-muted-foreground size-3.5" />
              </TooltipTrigger>
              <TooltipContent>
                <p className="max-w-xs text-xs">
                  定义请求体 JSON 的结构。您可以为每个字段设置类型、是否必填以及关联变量。
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={autoFill} className="h-7 text-[10px] gap-1.5">
                <ZapIcon className="size-3 text-yellow-500" />
                自动关联变量
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={addTopLevelField} className="h-7 w-7">
                <PlusIcon className="size-4" />
            </Button>
        </div>
      </div>

      <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
        {schema.length === 0 ? (
          <div className="py-10 text-center text-xs text-muted-foreground italic">
            暂无报文结构，请点击上方按钮导入或手动添加
          </div>
        ) : (
          schema.map((field, idx) => (
            <HttpBodyFieldItem
              key={idx}
              field={field}
              mapping={mapping}
              scene={scene}
              currentStepId={step.stepId}
              onUpdateField={(updated) => {
                const next = [...schema];
                next[idx] = updated;
                updateSchema(next);
              }}
              onUpdateMapping={(val) => updateMapping(field.name, val)}
              onDelete={() => {
                const next = schema.filter((_, i) => i !== idx);
                updateSchema(next);
              }}
            />
          ))
        )}
      </div>
    </div>
  );
}

function HttpBodyFieldItem({
  field,
  mapping,
  scene,
  currentStepId,
  onUpdateField,
  onUpdateMapping,
  onDelete,
  depth = 0,
}: {
  field: InputFieldDefinition;
  mapping: Record<string, any>;
  scene: SceneDefinition;
  currentStepId: string;
  onUpdateField: (field: InputFieldDefinition) => void;
  onUpdateMapping: (value: any) => void;
  onDelete: () => void;
  depth?: number;
}) {
  const addChild = () => {
    const children = field.children || [];
    onUpdateField({
      ...field,
      type: field.type === "object" || field.type === "array" ? field.type : "object",
      children: [
        ...children,
        {
          name: `sub_field_${children.length + 1}`,
          type: "string" as InputFieldType,
          required: false,
          batchEnabled: false,
        },
      ],
    });
  };

  return (
    <div className={cn("space-y-3", depth > 0 && "ml-4 border-l pl-4 py-1")}>
      <div className="flex items-center gap-2 group">
        <div className="grid flex-1 grid-cols-[1fr_80px_140px_60px_1fr] gap-2 items-center">
          <Input
            value={field.name}
            onChange={(e) => onUpdateField({ ...field, name: e.target.value })}
            placeholder="字段名"
            className="h-7 font-mono text-[10px]"
          />
          <Select
            value={field.type}
            onValueChange={(val) => onUpdateField({ ...field, type: val as InputFieldType })}
          >
            <SelectTrigger className="h-7 text-[10px] px-2">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INPUT_FIELD_TYPES.map((t) => (
                <SelectItem key={t} value={t} className="text-[10px]">
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          <Input
            value={field.label || ""}
            onChange={(e) => onUpdateField({ ...field, label: e.target.value })}
            placeholder="字段注释/备注"
            className="h-7 text-[10px]"
          />

          <div className="flex items-center gap-1.5 justify-center rounded border h-7 bg-background px-1">
             <span className="text-[9px] text-muted-foreground scale-90">必填</span>
             <Switch
                checked={field.required}
                onCheckedChange={(v) => onUpdateField({ ...field, required: v })}
                className="scale-[0.6]"
             />
          </div>

          <div className="relative">
            {(() => {
              const rawVal = (mapping[field.name] as string) ?? "";
              const isVar = rawVal && isVariableRef(rawVal);
              const displayVal = isVar
                ? resolveVariableLabel(rawVal, scene, currentStepId)
                : rawVal;
              return (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Input
                        value={displayVal}
                        onChange={(e) => onUpdateMapping(e.target.value)}
                        placeholder="映射变量或固定值"
                        className={cn(
                          "h-7 pr-7 text-[10px]",
                          isVar && "bg-blue-50/50 text-blue-700 font-medium dark:bg-blue-950/30 dark:text-blue-300",
                          !isVar && "font-mono",
                        )}
                        readOnly={isVar}
                        disabled={field.type === "object" || field.type === "array"}
                      />
                    </TooltipTrigger>
                    {isVar && (
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="font-mono text-[10px]">{rawVal}</p>
                      </TooltipContent>
                    )}
                  </Tooltip>
                </TooltipProvider>
              );
            })()}
            {field.type !== "object" && field.type !== "array" && (
                <div className="absolute right-1 top-1/2 -translate-y-1/2">
                    <Popover>
                    <PopoverTrigger asChild>
                        <Button variant="ghost" size="icon-sm" className="h-5 w-5">
                            <VariableIcon className="size-2.5 text-primary" />
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[300px] p-0" align="end">
                        <VariableSelector
                            scene={scene}
                            currentStepId={currentStepId}
                            onSelect={(v) => onUpdateMapping(v)}
                        />
                    </PopoverContent>
                    </Popover>
                </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
            {(field.type === "object" || field.type === "array") && (
                <Button variant="ghost" size="icon-sm" onClick={addChild} className="h-7 w-7">
                    <PlusIcon className="size-3.5" />
                </Button>
            )}
            <Button variant="ghost" size="icon-sm" onClick={onDelete} className="h-7 w-7 text-muted-foreground hover:text-destructive">
                <Trash2Icon className="size-3.5" />
            </Button>
        </div>
      </div>

      {field.children && field.children.length > 0 && (
        <div className="space-y-1">
          {field.children.map((child, idx) => (
            <HttpBodyFieldItem
              key={idx}
              field={child}
              mapping={mapping} // We might need a proper nested mapping resolution later
              scene={scene}
              currentStepId={currentStepId}
              onUpdateField={(updated) => {
                const nextChildren = [...field.children!];
                nextChildren[idx] = updated;
                onUpdateField({ ...field, children: nextChildren });
              }}
              onUpdateMapping={(val) => {
                  // For nested objects, we'd ideally update a nested key in mapping
                  // For now, simplify and treat field.name as the unique key in mapping
                  // Note: This won't work for duplicate field names in different branches
                  onUpdateMapping(val);
              }}
              onDelete={() => {
                onUpdateField({
                  ...field,
                  children: field.children!.filter((_, i) => i !== idx),
                });
              }}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
