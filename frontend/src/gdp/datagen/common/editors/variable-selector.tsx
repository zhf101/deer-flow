"use client";

import { CheckIcon, ChevronsUpDownIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

import type { SceneDefinition } from "../lib/types";
import { buildVariableList, type VariableItem } from "../lib/variable-utils";

interface VariableCommandListProps {
  scene: SceneDefinition;
  currentStepId?: string | null;
  includeAllSteps?: boolean;
  onSelect: (variable: string, item?: VariableItem) => void;
}

export function VariableCommandList({
  scene,
  currentStepId,
  includeAllSteps,
  onSelect,
}: VariableCommandListProps) {
  const variables = useMemo(
    () => buildVariableList(scene, currentStepId, includeAllSteps),
    [scene, currentStepId, includeAllSteps],
  );

  return (
    <Command>
      <CommandInput placeholder="搜索变量..." />
      <CommandList>
        <CommandEmpty>未找到变量</CommandEmpty>
        {["输入参数", "步骤输出", "认证信息", "系统变量"].map((group) => {
          const items = variables.filter((v) => v.group === group);
          if (items.length === 0) return null;
          return (
            <CommandGroup key={group} heading={group}>
              {items.map((v) => (
                <CommandItem
                  key={v.value}
                  value={v.value}
                  onSelect={() => {
                    onSelect(v.value, v);
                  }}
                >
                  <CheckIcon className="mr-2 h-4 w-4 opacity-0" />
                  <div className="flex flex-col">
                    <span className="text-xs font-medium">{v.label}</span>
                    <span className="text-muted-foreground font-mono text-[10px]">
                      {v.value}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          );
        })}
      </CommandList>
    </Command>
  );
}

interface VariableSelectorProps {
  scene: SceneDefinition;
  currentStepId?: string | null;
  onSelect: (variable: string, item?: VariableItem) => void;
  className?: string;
}

export function VariableSelector({
  scene,
  currentStepId,
  onSelect,
  className,
}: VariableSelectorProps) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn("w-full justify-between", className)}
        >
          <span className="truncate">选择变量...</span>
          <ChevronsUpDownIcon className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
        <VariableCommandList
          scene={scene}
          currentStepId={currentStepId}
          onSelect={(variable, item) => {
            onSelect(variable, item);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
