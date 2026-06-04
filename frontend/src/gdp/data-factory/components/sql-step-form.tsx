"use client";

import { DatabaseIcon, PlusIcon, Trash2Icon, VariableIcon, ZapIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { listDatasources } from "../lib/api";
import { SQL_OPERATIONS } from "../lib/defaults";
import type { DatasourceResponse, SceneDefinition, SqlOperation, SqlTemplateResponse, StepDefinition } from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";

import { VariableSelector } from "./variable-selector";

interface SqlStepFormProps {
  scene: SceneDefinition;
  step: StepDefinition;
  sqlTemplates: SqlTemplateResponse[];
  onChange: (step: StepDefinition) => void;
}

export function SqlStepForm({ scene, step, sqlTemplates, onChange }: SqlStepFormProps) {
  const [useTemplate, setUseTemplate] = useState(!step.datasource && !!step.sqlTemplateCode);
  const [rawSql, setRawSql] = useState("");
  const [datasources, setDatasources] = useState<DatasourceResponse[]>([]);

  const loadDatasources = useCallback(async () => {
    try {
      setDatasources(await listDatasources());
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void loadDatasources();
  }, [loadDatasources]);

  const datasourceOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const ds of datasources) {
      if (!seen.has(ds.datasourceCode)) {
        seen.set(ds.datasourceCode, ds.datasourceName);
      }
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [datasources]);

  const derivedParams = useMemo(() => {
    const sqlToParse = rawSql || "";
    const params = new Set<string>();

    const mybatisMatches = sqlToParse.match(/[#$]\{(\w+)\}/g);
    if (mybatisMatches) {
        mybatisMatches.forEach(m => params.add(m.substring(2, m.length - 1)));
    }

    const namedMatches = sqlToParse.match(/:\w+/g);
    if (namedMatches) {
        namedMatches.forEach(m => params.add(m.substring(1)));
    }

    const executableMatches = sqlToParse.matchAll(/(\w+)\s*=\s*(?:'[^']*'|[\d.-]+|TRUE|FALSE|NULL)/gi);
    for (const match of executableMatches) {
        if (match[1]) {
            const colName = match[1].toLowerCase();
            if (!["select", "insert", "update", "delete", "where", "and", "or", "on", "limit", "offset", "case"].includes(colName)) {
                params.add(match[1]);
            }
        }
    }

    return Array.from(params);
  }, [rawSql]);

  const detectOperation = (sql: string): SqlOperation => {
    const trimmed = sql.trim().toUpperCase();
    if (trimmed.startsWith("SELECT")) return "SELECT";
    if (trimmed.startsWith("INSERT")) return "INSERT";
    if (trimmed.startsWith("UPDATE")) return "UPDATE";
    if (trimmed.startsWith("DELETE")) return "DELETE";
    return "UPDATE";
  };

  const applyRawSql = () => {
    const op = detectOperation(rawSql);
    const newParamMapping: Record<string, any> = {};
    derivedParams.forEach(p => {
        newParamMapping[p] = step.paramMapping[p] || "";
    });

    onChange({
        ...step,
        operation: op,
        paramMapping: newParamMapping,
        sqlTemplateCode: "", 
        description: `Raw SQL: ${rawSql}`
    });
  };

  return (
    <div className="space-y-6">
      {/* SQL Input Section */}
      <div className="space-y-4 border-l-2 border-emerald-500/20 pl-5 py-1">
        <div className="flex items-center justify-between border-b pb-2 mb-2">
          <h4 className="text-sm font-bold flex items-center gap-2">
            <DatabaseIcon className="size-4 text-primary" />
            1. SQL 执行配置
          </h4>
          <div className="flex items-center gap-2">
            <Button 
                variant={useTemplate ? "default" : "outline"} 
                size="sm" 
                className="h-6 text-[10px]"
                onClick={() => setUseTemplate(true)}
            >使用模板</Button>
            <Button 
                variant={!useTemplate ? "default" : "outline"} 
                size="sm" 
                className="h-6 text-[10px]"
                onClick={() => setUseTemplate(false)}
            >手写 SQL</Button>
          </div>
        </div>

        <div className="space-y-4">
            <div className="space-y-2">
                <span className="text-xs font-medium text-muted-foreground">数据源 (Datasource)</span>
                <Select
                    value={step.datasource ?? "__none__"}
                    onValueChange={(value) =>
                        onChange({
                            ...step,
                            datasource: value === "__none__" ? "" : value,
                        })
                    }
                >
                    <SelectTrigger className="h-8 text-xs">
                        <SelectValue placeholder="选择数据源" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="__none__" className="text-xs">未选择</SelectItem>
                        {datasourceOptions.map((ds) => (
                            <SelectItem key={ds.code} value={ds.code} className="text-xs">
                                {ds.name} ({ds.code})
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            {useTemplate ? (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                            <span className="text-[10px] text-muted-foreground">选择预设模板</span>
                            <Select
                                value={step.sqlTemplateCode ?? "__none__"}
                                onValueChange={(value) =>
                                    onChange({
                                        ...step,
                                        sqlTemplateCode: value === "__none__" ? "" : value,
                                    })
                                }
                            >
                                <SelectTrigger className="h-8 text-xs">
                                    <SelectValue placeholder="选择模板" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__none__" className="text-xs">选择模板</SelectItem>
                                    {sqlTemplates.map((template) => (
                                        <SelectItem key={template.id} value={template.templateCode} className="text-xs">
                                            {template.templateName}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-1.5">
                             <span className="text-[10px] text-muted-foreground">操作类型</span>
                             <Select
                                value={step.operation ?? "UPDATE"}
                                onValueChange={(value) =>
                                    onChange({ ...step, operation: value as SqlOperation })
                                }
                            >
                                <SelectTrigger className="h-8 text-xs">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {SQL_OPERATIONS.map((operation) => (
                                        <SelectItem key={operation} value={operation} className="text-xs">
                                            {operation}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="space-y-3">
                    <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                            <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">贴入原始 SQL 语句</span>
                            {rawSql && (
                                <Badge variant="secondary" className="text-[9px] h-4 py-0">
                                    检测到类型: {detectOperation(rawSql)}
                                </Badge>
                            )}
                        </div>
                        <Textarea 
                            className="font-mono text-xs min-h-[120px] bg-muted/10 focus:bg-background transition-colors"
                            placeholder="e.g. SELECT * FROM users WHERE id = :user_id"
                            value={rawSql}
                            onChange={(e) => setRawSql(e.target.value)}
                        />
                    </div>
                    <Button 
                        variant="outline" 
                        size="sm" 
                        className="w-full h-8 text-xs gap-2 border-dashed"
                        onClick={applyRawSql}
                        disabled={!rawSql.trim()}
                    >
                        <ZapIcon className="size-3.5 text-yellow-500" />
                        解析 SQL 并推导参数
                    </Button>
                </div>
            )}
        </div>
      </div>

      {/* Parameter Mapping Section */}
      <div className="space-y-4 border-l-2 border-blue-500/20 pl-5 py-1">
        <div className="flex items-center gap-2 border-b pb-2 mb-2">
          <h4 className="text-sm font-bold">2. SQL 参数绑定 (Mapping)</h4>
        </div>
        
        <div className="rounded-lg border bg-muted/20 overflow-hidden">
            <div className="grid grid-cols-[140px_1fr] gap-4 px-4 py-2 bg-muted/40 text-[9px] font-bold text-muted-foreground uppercase">
                <div>SQL 变量名</div>
                <div>映射到场景变量</div>
            </div>
            <div className="p-2 space-y-2">
                {Object.entries(step.paramMapping).map(([key, val]) => (
                    <div key={key} className="grid grid-cols-[140px_1fr] gap-2 items-center">
                        <div className="font-mono text-[11px] text-primary font-bold px-2">:{key}</div>
                        <div className="relative">
                            {(() => {
                                const rawVal = String(val);
                                const isVar = rawVal && isVariableRef(rawVal);
                                const displayVal = isVar
                                    ? resolveVariableLabel(rawVal, scene, step.stepId)
                                    : rawVal;
                                return (
                                    <input
                                        className={cn(
                                            "flex h-8 w-full rounded-md border border-input bg-background px-3 py-1 text-[10px] pr-8 shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                                            isVar && "bg-blue-50/50 text-blue-700 font-medium dark:bg-blue-950/30 dark:text-blue-300",
                                            !isVar && "font-mono",
                                        )}
                                        value={displayVal}
                                        title={isVar ? rawVal : undefined}
                                        readOnly={isVar}
                                        onChange={(e) => {
                                            const next = { ...step.paramMapping, [key]: e.target.value };
                                            onChange({ ...step, paramMapping: next });
                                        }}
                                    />
                                );
                            })()}
                            <div className="absolute right-1 top-1/2 -translate-y-1/2">
                                <Popover>
                                    <PopoverTrigger asChild>
                                        <Button variant="ghost" size="icon-sm" className="h-6 w-6">
                                            <VariableIcon className="size-3 text-muted-foreground" />
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-[300px] p-0" align="end">
                                        <VariableSelector
                                            scene={scene}
                                            currentStepId={step.stepId}
                                            onSelect={(v) => {
                                                const next = { ...step.paramMapping, [key]: v };
                                                onChange({ ...step, paramMapping: next });
                                            }}
                                        />
                                    </PopoverContent>
                                </Popover>
                            </div>
                        </div>
                    </div>
                ))}
                {Object.keys(step.paramMapping).length === 0 && (
                    <div className="py-6 text-center text-[10px] text-muted-foreground italic">
                        {useTemplate ? "请先选择 SQL 模板" : "解析 SQL 语句后自动生成参数列表"}
                    </div>
                )}
            </div>
        </div>
      </div>

      {/* Output Section */}
      <div className="space-y-4 border-l-2 border-amber-500/20 pl-5 py-1">
        <div className="flex items-center gap-2 border-b pb-2 mb-2">
          <h4 className="text-sm font-bold">3. 执行结果提取</h4>
        </div>
        <p className="text-[11px] text-muted-foreground">对于 SELECT 语句，您可以将查询结果映射为变量。</p>
        <div className="space-y-3">
             <div className="rounded-lg border bg-card overflow-hidden">
                <div className="grid grid-cols-[120px_1fr_120px_1fr_48px] gap-4 px-4 py-2 bg-muted/40 text-[9px] font-bold text-muted-foreground uppercase border-b">
                    <div>结果字段</div>
                    <div>定义为变量名</div>
                    <div>中文名</div>
                    <div>备注</div>
                    <div className="text-center">操作</div>
                </div>
                <div className="p-2 space-y-2">
                    {Object.entries(step.outputMapping).map(([varName, field]) => {
                        const meta = step.outputMeta?.[varName] ?? {};
                        return (
                        <div key={varName} className="grid grid-cols-[120px_1fr_120px_1fr_48px] gap-2 items-center bg-muted/10 p-1.5 rounded">
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
                                    onClick={() => {
                                        const next = { ...step.outputMapping };
                                        const nextMeta = { ...(step.outputMeta ?? {}) };
                                        delete next[varName];
                                        delete nextMeta[varName];
                                        onChange({ ...step, outputMapping: next, outputMeta: nextMeta });
                                    }}
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
                            const next = { ...step.outputMapping, [`${step.stepId}.rsp.field_${Object.keys(step.outputMapping).length + 1}`]: "column_name" };
                            onChange({ ...step, outputMapping: next });
                        }}
                    >
                        <PlusIcon className="mr-1 size-3" />
                        添加结果提取项
                    </Button>
                </div>
             </div>
        </div>
      </div>
    </div>
  );
}
