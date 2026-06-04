"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { DatabaseIcon, GlobeIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export function HttpStepNode({ data, selected }: NodeProps) {
  const rawUrl = (data as any).url || "未配置URL";
  const isDisabled = (data as any).enabled === false;
  let displayUrl = rawUrl;
  try {
    displayUrl = displayUrl.replace(/^(?:https?:\/\/[^\/]+|\$\{[^\}]+\})/, '');
  } catch(e) {}
  if (!displayUrl) displayUrl = rawUrl;
  const truncatedUrl = displayUrl.length > 25 ? "..." + displayUrl.substring(displayUrl.length - 22) : displayUrl;

  return (
    <div className={cn(
        "px-4 py-3 rounded-lg border-2 bg-card shadow-lg min-w-[180px] max-w-[240px] transition-all",
        selected ? "border-blue-500 ring-4 ring-blue-500/10" : "border-blue-200",
        isDisabled && "opacity-50 border-dashed"
    )}>
      <Handle type="target" position={Position.Left} className="w-2 h-2 bg-blue-400" />
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-blue-100">
        <div className="p-1 rounded bg-blue-100 text-blue-600">
            <GlobeIcon className="size-3.5" />
        </div>
        <div className="flex-1 min-w-0">
            <div className="text-[10px] font-bold text-blue-600 uppercase leading-none mb-0.5">HTTP</div>
            <div className="text-[11px] font-bold truncate leading-tight">{(data as any).label}</div>
        </div>
      </div>
      <div className="bg-muted/50 rounded p-1.5 font-mono text-[9px] text-muted-foreground break-all leading-relaxed">
        <span className="text-blue-600 font-bold mr-1">URL:</span>
        {truncatedUrl}
      </div>
      {isDisabled && (
        <div className="mt-1.5 text-[8px] text-muted-foreground font-medium italic">已禁用</div>
      )}
      <Handle type="source" position={Position.Right} className="w-2 h-2 bg-blue-400" />
    </div>
  );
}

export function SqlStepNode({ data, selected }: NodeProps) {
  const sql = (data as any).sql || (data as any).sqlTemplateCode || "未配置SQL";
  const isDisabled = (data as any).enabled === false;
  const cleanSql = sql.replace(/\s+/g, ' ').trim();
  const truncatedSql = cleanSql.length > 30 ? cleanSql.substring(0, 27) + "..." : cleanSql;

  return (
    <div className={cn(
        "px-4 py-3 rounded-lg border-2 bg-card shadow-lg min-w-[180px] max-w-[240px] transition-all",
        selected ? "border-emerald-500 ring-4 ring-emerald-500/10" : "border-emerald-200",
        isDisabled && "opacity-50 border-dashed"
    )}>
      <Handle type="target" position={Position.Left} className="w-2 h-2 bg-emerald-400" />
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-emerald-100">
        <div className="p-1 rounded bg-emerald-100 text-emerald-600">
            <DatabaseIcon className="size-3.5" />
        </div>
        <div className="flex-1 min-w-0">
            <div className="text-[10px] font-bold text-emerald-600 uppercase leading-none mb-0.5">SQL</div>
            <div className="text-[11px] font-bold truncate leading-tight">{(data as any).label}</div>
        </div>
      </div>
      <div className="bg-muted/50 rounded p-1.5 font-mono text-[9px] text-muted-foreground break-all leading-relaxed">
        <span className="text-emerald-600 font-bold mr-1">SQL:</span>
        {truncatedSql}
      </div>
      {isDisabled && (
        <div className="mt-1.5 text-[8px] text-muted-foreground font-medium italic">已禁用</div>
      )}
      <Handle type="source" position={Position.Right} className="w-2 h-2 bg-emerald-400" />
    </div>
  );
}
