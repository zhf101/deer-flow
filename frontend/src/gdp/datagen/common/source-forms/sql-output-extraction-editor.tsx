/**
 * ============================================================================
 * 通用数据源表单 - SQL 结果提取编辑器
 * ============================================================================
 *
 * SQL 查询结果到场景变量的映射编辑器。
 * 支持手动添加和从解析结果快速导入。
 *
 * UI 内容：
 *   - 结果字段 → 变量名 映射表格
 *   - 每个映射可编辑字段名、变量名、中文名、备注
 *   - 从解析结果快速添加按钮（当有 resultFields 时）
 *
 * 被引用位置：
 *   - SqlStepForm 的结果提取区域
 *
 * 新增/复用判断：通用复用组件
 */
"use client";

import { ChevronDownIcon, ChevronRightIcon, PlusIcon, Trash2Icon, ZapIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { SqlSourceFieldMeta, StepDefinition } from "../lib/types";
import { ConfirmDialog } from "../ui/confirm-dialog";

interface SqlOutputExtractionEditorProps {
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
  disabled?: boolean;
  showHeader?: boolean;
  /** SQL 解析后的结果字段，用于快速添加 */
  resultFields?: SqlSourceFieldMeta[];
  /** 从解析结果添加的回调 */
  onAddFromResultFields?: () => void;
}

export function SqlOutputExtractionSection({
  step,
  onChange,
  disabled = false,
  resultFields,
  onAddFromResultFields,
}: Omit<SqlOutputExtractionEditorProps, "showHeader">) {
  const count = Object.keys(step.outputMapping ?? {}).length;
  const [open, setOpen] = useState(true);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 border-b text-sm font-bold text-amber-600 hover:text-amber-700 transition-colors">
        {open ? (
          <ChevronDownIcon className="size-4" />
        ) : (
          <ChevronRightIcon className="size-4" />
        )}
        <ZapIcon className="size-4" />
        执行结果提取
        {count > 0 && (
          <span className="ml-1 rounded-full bg-muted px-1.5 text-[9px] font-bold text-muted-foreground">
            {count}
          </span>
        )}
      </CollapsibleTrigger>

      <CollapsibleContent className="space-y-3 pt-3">
        <p className="text-xs text-muted-foreground">
          对于 SELECT 语句，将查询结果字段映射为变量，供后续步骤引用。
        </p>
        <SqlOutputExtractionEditor
          step={step}
          onChange={onChange}
          disabled={disabled}
          resultFields={resultFields}
          onAddFromResultFields={onAddFromResultFields}
          showHeader={false}
        />
      </CollapsibleContent>
    </Collapsible>
  );
}

export function SqlOutputExtractionEditor({
  step,
  onChange,
  disabled = false,
  showHeader = true,
  resultFields,
  onAddFromResultFields,
}: SqlOutputExtractionEditorProps) {
  const [pendingDeleteKey, setPendingDeleteKey] = useState<string | null>(null);

  const handleDelete = () => {
    if (!pendingDeleteKey) return;
    const next = { ...step.outputMapping };
    const nextMeta = { ...(step.outputMeta ?? {}) };
    delete next[pendingDeleteKey];
    delete nextMeta[pendingDeleteKey];
    onChange({ ...step, outputMapping: next, outputMeta: nextMeta });
    setPendingDeleteKey(null);
  };

  // 计算尚未添加的解析结果字段数
  const unmappedCount = resultFields?.filter(
    (f) => !step.outputMapping[f.alias || f.fieldName]
  ).length ?? 0;

  return (
    <div className="space-y-4">
      {showHeader && (
        <>
          <div className="flex items-center justify-between border-b pb-2 mb-2">
            <h4 className="text-sm font-bold">执行结果提取</h4>
            {onAddFromResultFields && unmappedCount > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-[9px] gap-1"
                onClick={onAddFromResultFields}
              >
                <ZapIcon className="size-3 text-yellow-500" />
                从解析结果添加 ({unmappedCount})
              </Button>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">
            对于 SELECT 语句，您可以将查询结果字段映射为变量，供后续步骤引用。
          </p>
        </>
      )}
      {!showHeader && onAddFromResultFields && unmappedCount > 0 && (
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-[9px] gap-1"
            onClick={onAddFromResultFields}
          >
            <ZapIcon className="size-3 text-yellow-500" />
            从解析结果添加 ({unmappedCount})
          </Button>
        </div>
      )}
      <div className={cn("space-y-3", disabled && "pointer-events-none opacity-50")}>
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="grid grid-cols-[120px_1fr_120px_1fr_48px] gap-2 px-4 py-2 bg-muted/40 text-[9px] font-bold text-muted-foreground uppercase border-b">
            <div>结果字段</div>
            <div>定义为变量名</div>
            <div>中文名</div>
            <div>备注</div>
            <div className="text-center">操作</div>
          </div>
          <div className="p-2 space-y-2">
            {Object.entries(step.outputMapping ?? {}).map(([varName, field]) => {
              const meta = step.outputMeta?.[varName] ?? {};
              return (
                <div key={varName} className="grid grid-cols-[120px_1fr_120px_1fr_48px] gap-2 px-4 items-center bg-muted/10 p-1.5 rounded">
                  <Input
                    className="h-7 text-[10px] font-mono bg-background"
                    value={field}
                    onChange={(e) => {
                      const next = { ...step.outputMapping, [varName]: e.target.value };
                      onChange({ ...step, outputMapping: next });
                    }}
                  />
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground">→</span>
                    <Input
                      className="h-7 text-[10px] font-mono bg-background flex-1"
                      value={varName}
                      readOnly
                    />
                  </div>
                  <Input
                    className="h-7 text-[10px] bg-background"
                    value={meta.label ?? ""}
                    placeholder="中文名"
                    onChange={(e) => {
                      const nextMeta = { ...(step.outputMeta ?? {}) };
                      nextMeta[varName] = { ...nextMeta[varName], label: e.target.value };
                      onChange({ ...step, outputMeta: nextMeta });
                    }}
                  />
                  <Input
                    className="h-7 text-[10px] bg-background"
                    value={meta.remark ?? ""}
                    placeholder="备注"
                    onChange={(e) => {
                      const nextMeta = { ...(step.outputMeta ?? {}) };
                      nextMeta[varName] = { ...nextMeta[varName], remark: e.target.value };
                      onChange({ ...step, outputMeta: nextMeta });
                    }}
                  />
                  <div className="flex justify-center">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 text-muted-foreground"
                      onClick={() => setPendingDeleteKey(varName)}
                    >
                      <Trash2Icon className="size-3" />
                    </Button>
                  </div>
                </div>
              );
            })}
            <Button
              variant="ghost"
              size="sm"
              className="w-full h-8 text-[10px] border border-dashed"
              onClick={() => {
                const idx = Object.keys(step.outputMapping ?? {}).length + 1;
                const next = { ...step.outputMapping, [`field_${idx}`]: "column_name" };
                onChange({ ...step, outputMapping: next });
              }}
            >
              <PlusIcon className="mr-1 size-3" />
              手动添加结果提取项
            </Button>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDeleteKey !== null}
        onOpenChange={(open) => { if (!open) setPendingDeleteKey(null); }}
        onConfirm={handleDelete}
        title="删除提取项"
        description={`确定删除提取项 "${pendingDeleteKey}" 吗？`}
      />
    </div>
  );
}
