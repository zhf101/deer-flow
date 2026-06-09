/**
 * ============================================================================
 * 模板导入弹窗 - 从 HTTP Source / SQL Source 导入配置到当前步骤
 * ============================================================================
 *
 * 在步骤配置面板顶部提供"从模板导入"按钮，点击后弹出此弹窗。
 * 弹窗列出与当前步骤类型匹配的模板（HTTP 步骤显示 HttpSource，SQL 步骤显示 SqlSource），
 * 用户选择后点击导入，将模板的业务配置字段覆盖到当前步骤中，同时设置 templateRef 快照。
 */
"use client";

import {
  DatabaseIcon,
  DownloadIcon,
  GlobeIcon,
  SearchIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { createDefaultHttpTimeoutConfig } from "../lib/defaults";
import {
  computeHttpSourceHash,
  computeHttpStepConfigHash,
  computeSqlSourceHash,
  computeSqlStepConfigHash,
} from "../lib/template-utils";
import type {
  HttpSourceResponse,
  HttpStepDefinition,
  SqlSourceResponse,
  SqlStepDefinition,
  StepDefinition,
} from "../lib/types";

interface TemplateImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  step: StepDefinition;
  httpSources: HttpSourceResponse[];
  sqlSources: SqlSourceResponse[];
  /** 导入完成后回调，参数为更新后的步骤 */
  onImport: (updatedStep: StepDefinition) => void;
}

export function TemplateImportDialog({
  open,
  onOpenChange,
  step,
  httpSources,
  sqlSources,
  onImport,
}: TemplateImportDialogProps) {
  const [search, setSearch] = useState("");
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const isHttp = step.type === "HTTP";
  const isSql = step.type === "SQL";

  // 根据步骤类型过滤模板列表
  const sources = useMemo(() => {
    if (isHttp) return httpSources;
    if (isSql) return sqlSources;
    return [];
  }, [isHttp, isSql, httpSources, sqlSources]);

  const filteredSources = useMemo(() => {
    if (!search.trim()) return sources;
    const q = search.toLowerCase();
    return sources.filter(
      (s) =>
        s.sourceName.toLowerCase().includes(q) ||
        s.sourceCode.toLowerCase().includes(q) ||
        s.sysCode.toLowerCase().includes(q),
    );
  }, [sources, search]);

  const selectedSource = sources.find((s) => s.sourceCode === selectedCode) ?? null;

  const handleImport = () => {
    if (!selectedSource) return;
    const now = new Date().toISOString();

    if (isHttp) {
      const src = selectedSource as HttpSourceResponse;
      const sourceHash = computeHttpSourceHash(src);
      const updated: HttpStepDefinition = {
        ...(step),
        sourceName: src.sourceName,
        sysCode: src.sysCode,
        method: src.method,
        path: src.path,
        timeoutConfig: src.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
        requestMapping: src.requestMapping ?? {},
        bodySchema: src.bodySchema ?? null,
        responseSchema: src.responseSchema ?? null,
        responseHeadersSchema: src.responseHeadersSchema ?? null,
        responseCookiesSchema: src.responseCookiesSchema ?? null,
        responseHandling: src.responseHandling ?? null,
        errorMapping: src.errorMapping ?? null,
        businessErrorMapping: src.businessErrorMapping ?? null,
        retryPolicy: src.retryPolicy ?? null,
        outputMapping: src.outputMapping ?? {},
        outputMeta: src.outputMeta ?? null,
        templateRef: {
          type: "HTTP_SOURCE",
          sourceCode: src.sourceCode,
          sourceNameAtSnapshot: src.sourceName,
          sourceUpdatedAtSnapshot: src.updatedAt,
          sourceHashSnapshot: sourceHash,
          configHash: "",
          snapshotAt: now,
          drifted: false,
        },
      };
      updated.templateRef!.configHash = computeHttpStepConfigHash(updated);
      onImport(updated);
    } else if (isSql) {
      const src = selectedSource as SqlSourceResponse;
      const sourceHash = computeSqlSourceHash(src);
      const updated: SqlStepDefinition = {
        ...(step),
        sourceName: src.sourceName,
        sysCode: src.sysCode,
        datasourceCode: src.datasourceCode,
        operation: src.operation,
        sqlText: src.sqlText,
        normalizedSql: src.normalizedSql,
        tables: src.tables ?? [],
        resultFields: src.resultFields ?? [],
        conditionFields: src.conditionFields ?? [],
        parameters: src.parameters ?? [],
        safety: src.safety ?? { requireWhere: true, maxAffectedRows: null },
        templateRef: {
          type: "SQL_SOURCE",
          sourceCode: src.sourceCode,
          sourceNameAtSnapshot: src.sourceName,
          sourceUpdatedAtSnapshot: src.updatedAt,
          sourceHashSnapshot: sourceHash,
          configHash: "",
          snapshotAt: now,
          drifted: false,
        },
      };
      updated.templateRef!.configHash = computeSqlStepConfigHash(updated);
      onImport(updated);
    }

    // 重置状态并关闭
    setSelectedCode(null);
    setSearch("");
    onOpenChange(false);
  };

  const handleClose = () => {
    setSelectedCode(null);
    setSearch("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <DownloadIcon className="size-4" />
            从模板导入配置
          </DialogTitle>
          <DialogDescription>
            选择{isHttp ? "HTTP 接口" : "SQL"}模板，将其配置导入到当前步骤。
            导入后步骤的 stepId、依赖关系和执行顺序保持不变。
          </DialogDescription>
        </DialogHeader>

        {/* 搜索栏 */}
        <div className="relative">
          <SearchIcon className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索模板名称、编码或系统..."
            className="h-8 pl-8 text-xs"
          />
        </div>

        {/* 模板列表 */}
        <div className="flex-1 overflow-auto rounded-md border">
          {filteredSources.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground text-xs">
              {sources.length === 0
                ? `暂无可用的${isHttp ? "HTTP 接口" : "SQL"}模板`
                : "没有匹配的模板"}
            </div>
          ) : (
            <div className="divide-y">
              {filteredSources.map((source) => {
                const isSelected = source.sourceCode === selectedCode;
                return (
                  <button
                    key={source.sourceCode}
                    type="button"
                    onClick={() => setSelectedCode(source.sourceCode)}
                    className={cn(
                      "w-full text-left px-3 py-2.5 transition-colors flex items-start gap-2.5",
                      isSelected
                        ? "bg-primary/10 border-l-2 border-l-primary"
                        : "hover:bg-muted/50 border-l-2 border-l-transparent",
                    )}
                  >
                    {isHttp ? (
                      <GlobeIcon className="size-4 text-blue-500 mt-0.5 shrink-0" />
                    ) : (
                      <DatabaseIcon className="size-4 text-emerald-500 mt-0.5 shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium truncate">
                          {source.sourceName}
                        </span>
                        <Badge variant="outline" className="text-[8px] h-4 shrink-0">
                          {source.sysCode}
                        </Badge>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="font-mono truncate">{source.sourceCode}</span>
                        {isHttp && (() => {
                          const httpSrc = source as HttpSourceResponse;
                          return (
                            <>
                              <Badge variant="secondary" className="text-[8px] h-4">
                                {httpSrc.method}
                              </Badge>
                              <span className="font-mono truncate">{httpSrc.path}</span>
                            </>
                          );
                        })()}
                        {isSql && (() => {
                          const sqlSrc = source as SqlSourceResponse;
                          return (
                            <>
                              <Badge variant="secondary" className="text-[8px] h-4">
                                {sqlSrc.operation}
                              </Badge>
                              <span className="truncate">{sqlSrc.datasourceCode}</span>
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={handleClose}>
            取消
          </Button>
          <Button
            size="sm"
            disabled={!selectedSource}
            onClick={handleImport}
            className="gap-1.5"
          >
            <DownloadIcon className="size-3.5" />
            导入配置
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
