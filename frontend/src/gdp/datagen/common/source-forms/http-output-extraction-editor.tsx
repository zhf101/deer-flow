"use client";

import {
  ChevronDownIcon,
  ChevronRightIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { flattenSchema } from "../lib/schema-utils";
import type { HttpStepDefinition } from "../lib/types";
import { ConfirmDialog } from "../ui/confirm-dialog";

/* ── 表达式辅助函数（与 http-response-mapping-editor 共享） ── */

const EXPRESSION_RE = /^\$\{([A-Z_]+)\((.*)\)\}$/;

export function extractorExpression(source: string, path: string) {
  return `\${${source}(${path})}`;
}

export function bodyExpression(path: string) {
  return extractorExpression("RES_BODY", expressionPath(path));
}

export function headerExpression(name: string) {
  return extractorExpression("RES_HEADER", name);
}

export function cookieExpression(name: string) {
  return extractorExpression("RES_COOKIE", name);
}

export function expressionPath(path: string) {
  return path.replace(/^\$\.?/, "");
}

export function parseExtractor(value: string): { source: string; path: string } | null {
  const match = EXPRESSION_RE.exec(value.trim());
  if (!match) return null;
  return { source: match[1] ?? "", path: match[2] ?? "" };
}

export function mappingSource(value: string): "Body" | "Headers" | "Cookies" {
  const parsed = parseExtractor(value);
  if (parsed?.source === "RES_HEADER") return "Headers";
  if (parsed?.source === "RES_COOKIE") return "Cookies";
  return "Body";
}

export function mappingDisplayName(value: string) {
  const parsed = parseExtractor(value);
  if (parsed) return parsed.path.split(".").pop()?.replace("[*]", "") ?? parsed.path;
  return value.split(".").pop()?.replace("[*]", "") ?? value;
}

export function normalizeMapping(value: string) {
  const parsed = parseExtractor(value);
  if (parsed) {
    return `${parsed.source}:${parsed.source === "RES_HEADER" ? parsed.path.toLowerCase() : parsed.path}`;
  }
  return `INVALID:${value}`;
}

export function isSameMapping(a: string, b: string) {
  return normalizeMapping(a) === normalizeMapping(b);
}

/* ── 组件 ── */

interface HttpOutputExtractionEditorProps {
  step: HttpStepDefinition;
  onChange: (updates: Partial<HttpStepDefinition>) => void;
  disabled?: boolean;
  showHeader?: boolean;
}

export function HttpOutputExtractionSection({
  step,
  onChange,
  disabled = false,
}: Omit<HttpOutputExtractionEditorProps, "showHeader">) {
  const count = Object.keys(step.outputMapping ?? {}).length;
  const [open, setOpen] = useState(true);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 border-b text-sm font-bold text-blue-600 hover:text-blue-700 transition-colors">
        {open ? (
          <ChevronDownIcon className="size-4" />
        ) : (
          <ChevronRightIcon className="size-4" />
        )}
        提取响应数据到变量
        {count > 0 && (
          <span className="ml-1 rounded-full bg-muted px-1.5 text-[9px] font-bold text-muted-foreground">
            {count}
          </span>
        )}
      </CollapsibleTrigger>

      <CollapsibleContent className="space-y-3 pt-3">
        <p className="text-xs text-muted-foreground">
          从 Body / Headers / Cookies 中提取字段，定义下游步骤可引用的变量名。
        </p>
        <HttpOutputExtractionEditor
          step={step}
          onChange={onChange}
          disabled={disabled}
          showHeader={false}
        />
      </CollapsibleContent>
    </Collapsible>
  );
}

export function HttpOutputExtractionEditor({
  step,
  onChange,
  disabled = false,
  showHeader = true,
}: HttpOutputExtractionEditorProps) {
  const [pendingDeleteKey, setPendingDeleteKey] = useState<string | null>(null);

  const outputMapping = step.outputMapping ?? {};
  const schema = useMemo(() => step.responseSchema ?? [], [step.responseSchema]);
  const headersSchema = useMemo(() => step.responseHeadersSchema ?? [], [step.responseHeadersSchema]);
  const cookiesSchema = useMemo(() => step.responseCookiesSchema ?? [], [step.responseCookiesSchema]);

  /* ── 展开后的字段列表 ── */
  const bodyFlatFields = useMemo(() => flattenSchema(schema, "$"), [schema]);
  const extractableBodyFields = useMemo(
    () => bodyFlatFields.filter((f) => f.type !== "object" && f.type !== "array"),
    [bodyFlatFields],
  );
  const headerExtractable = useMemo(
    () => headersSchema.filter((h) => h.type !== "object" && h.type !== "array"),
    [headersSchema],
  );
  const cookieExtractable = useMemo(
    () => cookiesSchema.filter((c) => c.type !== "object" && c.type !== "array"),
    [cookiesSchema],
  );

  const handleDelete = () => {
    if (!pendingDeleteKey) return;
    const next = { ...outputMapping };
    const nextMeta = { ...(step.outputMeta ?? {}) };
    delete next[pendingDeleteKey];
    delete nextMeta[pendingDeleteKey];
    onChange({ outputMapping: next, outputMeta: nextMeta });
    setPendingDeleteKey(null);
  };

  return (
    <section className="space-y-3">
      {showHeader && (
        <>
          <div className="flex items-center justify-between border-b pb-2">
            <div className="flex items-center gap-2 text-blue-600 font-bold text-sm">
              <span>提取响应数据到变量</span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            从 Body / Headers / Cookies 中提取字段，定义下游步骤可引用的变量名。
          </p>
        </>
      )}
      <div className={cn("space-y-2", disabled && "pointer-events-none opacity-50")}>
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="grid grid-cols-[72px_minmax(120px,1fr)_minmax(120px,1fr)_110px_minmax(140px,1fr)_40px] gap-2 px-3 py-2 bg-muted/40 text-[10px] font-bold text-muted-foreground uppercase border-b">
            <div>来源</div>
            <div>响应字段</div>
            <div>下游变量名</div>
            <div>中文名</div>
            <div>备注</div>
            <div className="text-center">操作</div>
          </div>
          <div className="p-1.5 space-y-1.5">
            {Object.entries(outputMapping).map(([varName, path]) => {
              const source = mappingSource(path);
              const sourceColor =
                source === "Body"
                  ? "bg-emerald-500/10 text-emerald-600"
                  : source === "Headers"
                    ? "bg-blue-500/10 text-blue-600"
                    : "bg-amber-500/10 text-amber-600";

              const matched = bodyFlatFields.find((f) => isSameMapping(bodyExpression(f.path), path));
              const meta = step.outputMeta?.[varName] ?? {};
              const missingLabel = !(meta.label ?? "").trim();
              const missingRemark = !(meta.remark ?? "").trim();

              return (
                <div
                  key={varName}
                  className={cn(
                    "grid grid-cols-[72px_minmax(120px,1fr)_minmax(120px,1fr)_110px_minmax(140px,1fr)_40px] gap-2 px-3 items-center bg-muted/10 p-1 rounded border border-transparent hover:border-border transition-all",
                    (missingLabel || missingRemark) && "border-l-2 border-l-amber-400",
                  )}
                >
                  <div className="flex justify-center">
                    <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded", sourceColor)}>
                      {source}
                    </span>
                  </div>
                  <div className="px-2 text-xs truncate font-mono" title={path}>
                    {matched ? matched.label : mappingDisplayName(path)}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground shrink-0">=</span>
                    <Input
                      className="h-7 text-xs font-mono bg-background"
                      value={varName}
                      placeholder="输入变量名"
                      onChange={(e) => {
                        const newName = e.target.value;
                        if (newName === varName) return;
                        const next: Record<string, string> = {};
                        const nextMeta = { ...(step.outputMeta ?? {}) };
                        Object.entries(outputMapping).forEach(([k, v]) => {
                          const targetKey = k === varName ? newName : k;
                          next[targetKey] = v;
                          if (k === varName) {
                            nextMeta[targetKey] = nextMeta[varName] ?? {};
                            delete nextMeta[varName];
                          }
                        });
                        onChange({ outputMapping: next, outputMeta: nextMeta });
                      }}
                    />
                  </div>
                  <Input
                    className={cn(
                      "h-7 text-xs bg-background",
                      missingLabel && "border-l-2 border-l-amber-400",
                    )}
                    value={meta.label ?? ""}
                    placeholder="中文名"
                    onChange={(e) => {
                      const nextMeta = { ...(step.outputMeta ?? {}) };
                      nextMeta[varName] = { ...nextMeta[varName], label: e.target.value };
                      onChange({ outputMeta: nextMeta });
                    }}
                  />
                  <Input
                    className={cn(
                      "h-7 text-xs bg-background",
                      missingRemark && "border-l-2 border-l-amber-400",
                    )}
                    value={meta.remark ?? ""}
                    placeholder="业务说明"
                    onChange={(e) => {
                      const nextMeta = { ...(step.outputMeta ?? {}) };
                      nextMeta[varName] = { ...nextMeta[varName], remark: e.target.value };
                      onChange({ outputMeta: nextMeta });
                    }}
                  />
                  <div className="flex justify-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 text-muted-foreground hover:text-destructive"
                      onClick={() => setPendingDeleteKey(varName)}
                    >
                      <Trash2Icon className="size-3" />
                    </Button>
                  </div>
                </div>
              );
            })}
            {Object.keys(outputMapping).length === 0 && (
              <div className="py-4 text-center text-[10px] text-muted-foreground italic">
                未配置提取项，在上方各页签中勾选字段或点击下方按钮添加
              </div>
            )}
          </div>
        </div>

        {/* 快速添加下拉菜单 */}
        <div className="flex gap-2">
          {extractableBodyFields.length > 0 && (
            <Select onValueChange={(path) => {
              if (!path) return;
              const baseName = path.split(".").pop()?.replace("[*]", "") ?? "data";
              let varName = baseName;
              let suffix = 1;
              while (varName in outputMapping) {
                varName = `${baseName}_${suffix++}`;
              }
              const matchedField = bodyFlatFields.find((f) => f.path === path);
              const expression = bodyExpression(path);
              const nextMeta = { ...(step.outputMeta ?? {}) };
              nextMeta[varName] = {
                label: matchedField?.fieldLabel ?? "",
                remark: matchedField?.fieldRemark ?? "",
              };
              onChange({
                outputMapping: { ...outputMapping, [varName]: expression },
                outputMeta: nextMeta,
              });
            }}>
              <SelectTrigger className="w-[180px] h-8 text-xs gap-2">
                <PlusIcon className="size-3" />
                <SelectValue placeholder="+ Body 字段" />
              </SelectTrigger>
              <SelectContent>
                {extractableBodyFields.map((f) => (
                    <SelectItem key={f.path} value={f.path} className="text-xs">
                      {f.label}
                    </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {headerExtractable.length > 0 && (
            <Select onValueChange={(name) => {
              if (!name) return;
              const path = headerExpression(name);
              let varName = name.replace(/-/g, "_").toLowerCase();
              let suffix = 1;
              while (varName in outputMapping) {
                varName = `${name.replace(/-/g, "_").toLowerCase()}_${suffix++}`;
              }
              const header = headersSchema.find((h) => h.name === name);
              const nextMeta = { ...(step.outputMeta ?? {}) };
              nextMeta[varName] = { label: header?.label ?? "", remark: header?.remark ?? "" };
              onChange({
                outputMapping: { ...outputMapping, [varName]: path },
                outputMeta: nextMeta,
              });
            }}>
              <SelectTrigger className="w-[180px] h-8 text-xs gap-2">
                <PlusIcon className="size-3" />
                <SelectValue placeholder="+ Header" />
              </SelectTrigger>
              <SelectContent>
                {headerExtractable.map((h) => (
                  <SelectItem key={h.name} value={h.name} className="text-xs">
                    {h.name} {h.label ? `(${h.label})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {cookieExtractable.length > 0 && (
            <Select onValueChange={(name) => {
              if (!name) return;
              const path = cookieExpression(name);
              let varName = name;
              let suffix = 1;
              while (varName in outputMapping) {
                varName = `${name}_${suffix++}`;
              }
              const cookie = cookiesSchema.find((c) => c.name === name);
              const nextMeta = { ...(step.outputMeta ?? {}) };
              nextMeta[varName] = { label: cookie?.label ?? "", remark: cookie?.remark ?? "" };
              onChange({
                outputMapping: { ...outputMapping, [varName]: path },
                outputMeta: nextMeta,
              });
            }}>
              <SelectTrigger className="w-[180px] h-8 text-xs gap-2">
                <PlusIcon className="size-3" />
                <SelectValue placeholder="+ Cookie" />
              </SelectTrigger>
              <SelectContent>
                {cookieExtractable.map((c) => (
                  <SelectItem key={c.name} value={c.name} className="text-xs">
                    {c.name} {c.label ? `(${c.label})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDeleteKey !== null}
        onOpenChange={(open) => { if (!open) setPendingDeleteKey(null); }}
        onConfirm={handleDelete}
        title="删除提取项"
        description={`确定删除提取项 "${pendingDeleteKey}" 吗？`}
      />
    </section>
  );
}
