"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { AlertTriangleIcon, DatabaseIcon, GlobeIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { StepNodeData } from "../../common/lib/flow";

export function HttpStepNode({ data, selected }: NodeProps) {
  const d = data as unknown as StepNodeData;
  // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty string should fall through
  const rawUrl = d.url || "未配置URL";
  const isDisabled = d.enabled === false;
  const outputCount = d.outputCount ?? 0;
  const hasErrors = d.hasErrors ?? false;
  let displayUrl = rawUrl;
  try {
    displayUrl = displayUrl.replace(/^(?:https?:\/\/[^/]+|\$\{[^}]+})/, "");
  } catch {
    // regex shouldn't throw, but guard defensively
  }
  if (!displayUrl) {
    displayUrl = rawUrl;
  }
  const truncatedUrl = displayUrl.length > 25 ? "..." + displayUrl.substring(displayUrl.length - 22) : displayUrl;

  return (
    <div className={cn(
        "px-4 py-3 rounded-lg border-2 bg-card shadow-lg min-w-[180px] max-w-[240px] transition-all",
        selected ? "border-blue-500 ring-4 ring-blue-500/10" : hasErrors ? "border-red-300" : "border-blue-200",
        isDisabled && "opacity-50 border-dashed"
    )}>
      <Handle type="target" position={Position.Left} className="w-2 h-2 bg-blue-400" />
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-blue-100">
        <div className="p-1 rounded bg-blue-100 text-blue-600">
            <GlobeIcon className="size-3.5" />
        </div>
        <div className="flex-1 min-w-0">
            <div className="text-[10px] font-bold text-blue-600 uppercase leading-none mb-0.5">HTTP</div>
            <div className="text-[11px] font-bold truncate leading-tight">{d.label}</div>
        </div>
        {hasErrors && (
          <AlertTriangleIcon className="size-3.5 text-red-500 shrink-0" />
        )}
      </div>
      <div className="bg-muted/50 rounded p-1.5 font-mono text-[9px] text-muted-foreground break-all leading-relaxed">
        <span className="text-blue-600 font-bold mr-1">URL:</span>
        {truncatedUrl}
      </div>
      {/* 状态指示器 */}
      <div className="flex items-center gap-1.5 mt-1.5">
        {outputCount > 0 && (
          <Badge variant="outline" className="text-[8px] h-3.5 px-1 border-blue-200 text-blue-600">
            {outputCount} outputs
          </Badge>
        )}
        {isDisabled && (
          <span className="text-[8px] text-muted-foreground font-medium italic">已禁用</span>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="w-2 h-2 bg-blue-400" />
    </div>
  );
}

export function SqlStepNode({ data, selected }: NodeProps) {
  const d = data as unknown as StepNodeData;
  // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty string should fall through
  const sql = d.sql || "未配置SQL";
  const isDisabled = d.enabled === false;
  const outputCount = d.outputCount ?? 0;
  const hasErrors = d.hasErrors ?? false;
  const cleanSql = sql.replace(/\s+/g, " ").trim();
  const truncatedSql = cleanSql.length > 30 ? cleanSql.substring(0, 27) + "..." : cleanSql;

  return (
    <div className={cn(
        "px-4 py-3 rounded-lg border-2 bg-card shadow-lg min-w-[180px] max-w-[240px] transition-all",
        selected ? "border-emerald-500 ring-4 ring-emerald-500/10" : hasErrors ? "border-red-300" : "border-emerald-200",
        isDisabled && "opacity-50 border-dashed"
    )}>
      <Handle type="target" position={Position.Left} className="w-2 h-2 bg-emerald-400" />
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-emerald-100">
        <div className="p-1 rounded bg-emerald-100 text-emerald-600">
            <DatabaseIcon className="size-3.5" />
        </div>
        <div className="flex-1 min-w-0">
            <div className="text-[10px] font-bold text-emerald-600 uppercase leading-none mb-0.5">SQL</div>
            <div className="text-[11px] font-bold truncate leading-tight">{d.label}</div>
        </div>
        {hasErrors && (
          <AlertTriangleIcon className="size-3.5 text-red-500 shrink-0" />
        )}
      </div>
      <div className="bg-muted/50 rounded p-1.5 font-mono text-[9px] text-muted-foreground break-all leading-relaxed">
        <span className="text-emerald-600 font-bold mr-1">SQL:</span>
        {truncatedSql}
      </div>
      {/* 状态指示器 */}
      <div className="flex items-center gap-1.5 mt-1.5">
        {outputCount > 0 && (
          <Badge variant="outline" className="text-[8px] h-3.5 px-1 border-emerald-200 text-emerald-600">
            {outputCount} outputs
          </Badge>
        )}
        {isDisabled && (
          <span className="text-[8px] text-muted-foreground font-medium italic">已禁用</span>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="w-2 h-2 bg-emerald-400" />
    </div>
  );
}
