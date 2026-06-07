"use client";

import { InfoIcon, PlusIcon, Trash2Icon, VariableIcon } from "lucide-react";
import { useMemo, useRef, useState } from "react";

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
import { ConfirmDialog } from "../ui/confirm-dialog";

/* ── common HTTP headers for autocomplete ──────────────────────── */
const COMMON_HEADERS = [
  { name: "Content-Type", desc: "内容类型" },
  { name: "Accept", desc: "接受的响应类型" },
  { name: "Authorization", desc: "认证信息" },
  { name: "X-Request-Id", desc: "请求追踪 ID" },
  { name: "X-Correlation-Id", desc: "关联 ID" },
  { name: "X-Api-Key", desc: "API 密钥" },
  { name: "X-Api-Version", desc: "API 版本" },
  { name: "Cache-Control", desc: "缓存控制" },
  { name: "Cookie", desc: "Cookie" },
  { name: "User-Agent", desc: "用户代理" },
  { name: "Referer", desc: "来源页面" },
  { name: "Origin", desc: "请求来源" },
  { name: "If-None-Match", desc: "条件请求 ETag" },
  { name: "If-Modified-Since", desc: "条件请求时间" },
  { name: "X-Forwarded-For", desc: "转发来源 IP" },
  { name: "X-Tenant-Id", desc: "租户 ID" },
  { name: "X-Trace-Id", desc: "链路追踪 ID" },
  { name: "X-Operator", desc: "操作人" },
  { name: "X-Source", desc: "请求来源标识" },
  { name: "X-Timestamp", desc: "请求时间戳" },
  { name: "X-Sign", desc: "签名" },
  { name: "X-Nonce", desc: "随机数" },
];

interface HeaderFieldMapperProps {
  label: string;
  description?: string;
  value: Record<string, any>;
  onChange: (value: Record<string, any>) => void;
  scene?: SceneDefinition;
  currentStepId?: string;
  placeholder?: string;
  /** Optional description map for each header key */
  descriptions?: Record<string, string>;
  onDescriptionsChange?: (descriptions: Record<string, string>) => void;
}

export function HeaderFieldMapper({
  label,
  description,
  value,
  onChange,
  scene,
  currentStepId,
  placeholder = "Header Key",
  descriptions,
  onDescriptionsChange,
}: HeaderFieldMapperProps) {
  const fields = Object.entries(value);
  const hasDesc = descriptions != null && onDescriptionsChange != null;
  const listId = useMemo(() => `header-suggest-${Math.random().toString(36).slice(2, 8)}`, []);

  const updateField = (oldKey: string, newKey: string, newValue: any) => {
    const next = { ...value };
    if (oldKey !== newKey) {
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
    onChange({ ...value, [`header_${fields.length + 1}`]: "" });
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
                <TooltipContent className="max-w-xs text-xs">{description}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={addField}>
          <PlusIcon className="size-4" />
        </Button>
      </div>

      {/* Hidden datalist for browser autocomplete */}
      <datalist id={listId}>
        {COMMON_HEADERS.map((h) => (
          <option key={h.name} value={h.name}>
            {h.desc}
          </option>
        ))}
      </datalist>

      <div className="space-y-1.5">
        {fields.map(([key, val]) => (
          <HeaderRow
            key={key}
            k={key}
            val={val}
            listId={listId}
            placeholder={placeholder}
            scene={scene}
            currentStepId={currentStepId}
            hasDesc={hasDesc}
            descValue={hasDesc ? (descriptions![key] ?? "") : undefined}
            onUpdate={(newKey, newVal) => updateField(key, newKey, newVal)}
            onRemove={() => removeField(key)}
            onDescChange={hasDesc ? (d) => updateDesc(key, d) : undefined}
          />
        ))}
        {fields.length === 0 && (
          <div className="py-3 text-center text-[10px] text-muted-foreground italic border border-dashed rounded-md">
            暂无 Header，点击 + 添加
          </div>
        )}
      </div>
    </div>
  );
}

/* ── single header row ──────────────────────────────────────────── */

function HeaderRow({
  k,
  val,
  listId,
  placeholder,
  scene,
  currentStepId,
  hasDesc,
  descValue,
  onUpdate,
  onRemove,
  onDescChange,
}: {
  k: string;
  val: any;
  listId: string;
  placeholder: string;
  scene?: SceneDefinition;
  currentStepId?: string;
  hasDesc: boolean;
  descValue?: string;
  onUpdate: (newKey: string, newVal: any) => void;
  onRemove: () => void;
  onDescChange?: (desc: string) => void;
}) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [filter, setFilter] = useState("");
  const [confirmPending, setConfirmPending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = useMemo(() => {
    const q = (filter || k).toLowerCase();
    if (!q) return COMMON_HEADERS.slice(0, 8);
    return COMMON_HEADERS.filter(
      (h) => h.name.toLowerCase().includes(q) || h.desc.includes(q),
    ).slice(0, 8);
  }, [filter, k]);

  const rawVal = typeof val === "string" ? val : JSON.stringify(val);
  const canResolve = !!scene;
  const isVar = canResolve && !!(rawVal && isVariableRef(rawVal));
  const displayVal = isVar ? resolveVariableLabel(rawVal, scene!, currentStepId) : rawVal;

  return (
    <div className={cn("flex items-center gap-2", hasDesc && "grid grid-cols-[1fr_1fr_1fr_32px]")}>
      {/* Key input with autocomplete dropdown */}
      <div className={cn("relative", !hasDesc && "w-1/3")}>
        <Input
          ref={inputRef}
          value={k}
          list={listId}
          onChange={(e) => {
            onUpdate(e.target.value, val);
            setFilter(e.target.value);
          }}
          onFocus={() => {
            setShowSuggestions(true);
            setFilter(k);
          }}
          onBlur={() => {
            // Delay to allow click on suggestion
            setTimeout(() => setShowSuggestions(false), 150);
          }}
          placeholder={placeholder}
          className="h-8 font-mono text-[10px]"
        />
        {showSuggestions && suggestions.length > 0 && (
          <div className="absolute left-0 top-full z-50 mt-1 w-full max-h-[200px] overflow-auto rounded-md border bg-popover shadow-md">
            {suggestions.map((h) => (
              <button
                key={h.name}
                type="button"
                className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-[10px] hover:bg-muted/50 transition-colors"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onUpdate(h.name, val);
                  setShowSuggestions(false);
                }}
              >
                <span className="font-mono font-medium">{h.name}</span>
                <span className="text-muted-foreground text-[9px]">{h.desc}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Value input with variable selector */}
      <div className="relative flex-1 group">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Input
                value={displayVal}
                onChange={(e) => onUpdate(k, e.target.value)}
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
                onSelect={(v) => onUpdate(k, v)}
              />
            </PopoverContent>
          </Popover>
        </div>
        )}
      </div>

      {hasDesc && (
        <Input
          value={descValue ?? ""}
          onChange={(e) => onDescChange?.(e.target.value)}
          placeholder="说明"
          className="h-8 text-[10px]"
        />
      )}

      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => setConfirmPending(true)}
        className="text-muted-foreground hover:text-destructive"
      >
        <Trash2Icon className="size-4" />
      </Button>

      <ConfirmDialog
        open={confirmPending}
        onOpenChange={setConfirmPending}
        onConfirm={onRemove}
        title="删除请求头"
        description={`确定删除请求头 "${k}" 吗？`}
      />
    </div>
  );
}
