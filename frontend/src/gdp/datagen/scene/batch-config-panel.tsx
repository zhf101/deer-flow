"use client";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import type { BatchConfig, SceneDefinition } from "../common/lib/types";

interface BatchConfigPanelProps {
  scene: SceneDefinition;
  onChange: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

export function BatchConfigPanel({ scene, onChange, readOnly }: BatchConfigPanelProps) {
  const batch = scene.batchConfig ?? {
    enabled: false,
    failurePolicy: "STOP_ON_ERROR",
    maxConcurrency: 1,
  };

  const update = (next: BatchConfig) => {
    onChange({ ...scene, batchConfig: next });
  };

  return (
    <div className="space-y-4">
      <label className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
        启用批量
        <Switch
          checked={batch.enabled}
          disabled={readOnly}
          onCheckedChange={(checked) => update({ ...batch, enabled: checked })}
        />
      </label>
      <div className={cn("space-y-4", readOnly && "pointer-events-none opacity-80")}>
        <label className="block space-y-1.5">
          <span className="text-muted-foreground text-xs font-medium">失败策略</span>
          <Select
            value={batch.failurePolicy}
            onValueChange={(value) =>
              update({
                ...batch,
                failurePolicy: value as BatchConfig["failurePolicy"],
              })
            }
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="STOP_ON_ERROR">失败即停</SelectItem>
              <SelectItem value="CONTINUE_ON_ERROR">失败继续</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <label className="block space-y-1.5">
          <span className="text-muted-foreground text-xs font-medium">并发数</span>
          <Input
            type="number"
            min={1}
            max={20}
            value={batch.maxConcurrency}
            onChange={(event) =>
              update({
                ...batch,
                maxConcurrency: Math.max(1, Number(event.target.value || 1)),
              })
            }
          />
        </label>
      </div>
    </div>
  );
}
