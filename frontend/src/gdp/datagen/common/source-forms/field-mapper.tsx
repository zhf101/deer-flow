"use client";

import { InfoIcon, PlusIcon, Trash2Icon, VariableIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import type { SceneDefinition } from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";

import { VariableSelector } from "../editors/variable-selector";

interface FieldMapperProps {
  label: string;
  description?: string;
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  scene?: SceneDefinition;
  currentStepId?: string;
  placeholder?: string;
  /** Optional description map for each key, displayed as a third column */
  descriptions?: Record<string, string>;
  onDescriptionsChange?: (descriptions: Record<string, string>) => void;
}

export function FieldMapper({
  label,
  description,
  value,
  onChange,
  scene,
  currentStepId,
  placeholder = "字段名",
  descriptions,
  onDescriptionsChange,
}: FieldMapperProps) {
  const fields = Object.entries(value);
  const hasDesc = descriptions != null && onDescriptionsChange != null;

  const updateField = (oldKey: string, newKey: string, newValue: any) => {
    const next = { ...value };
    if (oldKey !== newKey) {
      // Also migrate description when key changes
      if (hasDesc && descriptions![oldKey] != null) {
        const nextDesc = { ...descriptions };
        nextDesc[newKey] = nextDesc[oldKey]!;
        delete nextDesc[oldKey];
        onDescriptionsChange!(nextDesc);
      }
      delete next[oldKey];
    }
    next[newKey] = newValue;
    onChange(next);
  };

  const removeField = (key: string) => {
    const next = { ...value };
    delete next[key];
    onChange(next);
    if (hasDesc) {
      const nextDesc = { ...descriptions };
      delete nextDesc[key];
      onDescriptionsChange!(nextDesc);
    }
  };

  const addField = () => {
    onChange({ ...value, [`field_${fields.length + 1}`]: "" });
  };

  const updateDesc = (key: string, desc: string) => {
    onDescriptionsChange!({ ...descriptions, [key]: desc });
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">{label}</span>
          {description && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <InfoIcon className="text-muted-foreground size-3.5" />
                </TooltipTrigger>
                <TooltipContent className="max-w-xs text-xs">
                  {description}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={addField}>
          <PlusIcon className="size-4" />
        </Button>
      </div>

      <div className="space-y-1.5">
        {fields.map(([key, val]) => (
          <div key={key} className={cn("flex items-center gap-2", hasDesc && "grid grid-cols-[1fr_1fr_1fr_32px]")}>
            <Input
              value={key}
              onChange={(e) => updateField(key, e.target.value, val)}
              placeholder={placeholder}
              className={cn("h-8 font-mono text-[10px]", !hasDesc && "w-1/3")}
            />
            <div className={cn("relative group", !hasDesc && "flex-1")}>
              {(() => {
                const rawVal = typeof val === "string" ? val : JSON.stringify(val);
                const canResolve = !!scene;
                const isVar = canResolve && !!(rawVal && isVariableRef(rawVal));
                const displayVal = isVar
                  ? resolveVariableLabel(rawVal, scene!, currentStepId)
                  : rawVal;
                return (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Input
                          value={displayVal}
                          onChange={(e) => updateField(key, key, e.target.value)}
                          placeholder="值或变量 ${...}"
                          className={cn(
                            "h-8 pr-8 text-[10px]",
                            isVar && "bg-blue-50/50 text-blue-700 font-medium dark:bg-blue-950/30 dark:text-blue-300",
                            !isVar && "font-mono",
                          )}
                          readOnly={isVar}
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
              {scene && (
              <div className="absolute right-1 top-1/2 -translate-y-1/2">
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="ghost" size="icon-sm" className="h-6 w-6">
                      <VariableIcon className="size-3 text-primary" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[300px] p-0" align="end">
                    <VariableSelector
                      scene={scene}
                      currentStepId={currentStepId}
                      onSelect={(v) => updateField(key, key, v)}
                    />
                  </PopoverContent>
                </Popover>
              </div>
              )}
            </div>
            {hasDesc && (
              <Input
                value={descriptions![key] ?? ""}
                onChange={(e) => updateDesc(key, e.target.value)}
                placeholder="说明"
                className="h-8 text-[10px]"
              />
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => removeField(key)}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2Icon className="size-4" />
            </Button>
          </div>
        ))}
        {fields.length === 0 && (
          <div className="py-3 text-center text-[10px] text-muted-foreground italic border border-dashed rounded-md">
            暂无配置
          </div>
        )}
      </div>
    </div>
  );
}
