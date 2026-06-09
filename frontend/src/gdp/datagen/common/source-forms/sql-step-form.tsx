/**
 * ============================================================================
 * 通用数据源表单 - SQL 步骤完整配置表单
 * ============================================================================
 *
 * SQL 数据源的核心配置表单，支持手写 SQL 并通过后端 API 解析。
 * 包含系统/数据源选择、原始 SQL 输入、后端解析、参数绑定、
 * 以及执行结果提取配置。
 *
 * UI 内容（三大区域）：
 *   1. SQL 执行配置：系统选择 + 数据源选择 + 原始 SQL + 解析按钮 + 解析状态
 *   2. SQL 参数绑定：SQL 变量名 → 场景变量映射表格
 *   3. 执行结果提取：SqlOutputExtractionEditor
 *
 * 被引用位置：
 *   - SceneEditor 的 SQL 步骤配置面板
 *
 * 新增/复用判断：通用复用组件（核心表单）
 */
"use client";

import {
  CheckCircleIcon,
  ChevronDownIcon,
  DatabaseIcon,
  FileCodeIcon,
  ListChecksIcon,
  Loader2Icon,
  TableIcon,
  VariableIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
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

import { VariableSelector } from "../editors/variable-selector";
import { listDatasources, listSystems, parseSqlSource } from "../lib/api";
import { SQL_OPERATIONS } from "../lib/defaults";
import type {
  DatasourceResponse,
  SceneDefinition,
  SqlSourceConditionMeta,
  SqlSourceFieldMeta,
  SqlOperation,
  SqlStepDefinition,
  SqlSourceParameter,
  SqlSourceTableMeta,
  SysResponse,
} from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";

import { SqlOutputExtractionSection } from "./sql-output-extraction-editor";


interface SqlStepFormProps {
  scene: SceneDefinition;
  step: SqlStepDefinition;
  sqlTemplates?: unknown[];
  onChange: (step: SqlStepDefinition) => void;
}

type ParseStatus = "idle" | "parsing" | "success" | "error" | "stale";

const SQL_PARAMETER_TYPES = ["string", "number", "boolean", "date"] as const;
const TABLE_META_GRID = "minmax(160px, 1fr) minmax(100px, 120px) minmax(240px, 2fr)";
const RESULT_FIELD_META_GRID = "minmax(160px, 1fr) minmax(120px, 140px) minmax(120px, 140px) minmax(240px, 2fr)";
const CONDITION_FIELD_META_GRID = "minmax(160px, 1fr) minmax(120px, 140px) minmax(140px, 160px) minmax(240px, 2fr)";
const PARAMETER_META_GRID = "minmax(160px, 1fr) minmax(110px, 120px) minmax(90px, 100px) minmax(160px, 1fr) minmax(240px, 2fr)";

export function SqlStepForm({ scene, step, onChange }: SqlStepFormProps) {
  const safeStringify = (val: unknown): string => {
    if (val == null) return "";
    if (typeof val === "string") return val;
    if (typeof val === "number" || typeof val === "boolean") return String(val);
    return JSON.stringify(val);
  };

  const [rawSql, setRawSql] = useState(step.sqlText ?? "");
  const [parseStatus, setParseStatus] = useState<ParseStatus>(() => {
    if (step.normalizedSql) return "success";
    if (step.sqlText) return "stale";
    return "idle";
  });
  const [parseError, setParseError] = useState<string | null>(null);
  const [datasources, setDatasources] = useState<DatasourceResponse[]>([]);
  const [systems, setSystems] = useState<SysResponse[]>([]);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  const loadDatasources = useCallback(async () => {
    try {
      const [datasourceItems, systemItems] = await Promise.all([
        listDatasources(),
        listSystems(),
      ]);
      setDatasources(datasourceItems);
      setSystems(systemItems);
    } catch {
      // 忽略
    }
  }, []);

  useEffect(() => {
    void loadDatasources();
  }, [loadDatasources]);

  // 同步外部 step.sqlText 变化（如加载场景时）
  useEffect(() => {
    if (step.sqlText && step.sqlText !== rawSql) {
      setRawSql(step.sqlText);
      setParseStatus(step.normalizedSql ? "success" : step.sqlText ? "stale" : "idle");
    }
  // 仅在 step.sqlText 从外部变化时触发
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.sqlText]);

  const datasourceOptions = useMemo(() => {
    const selectedSysCode = step.sysCode ?? "";
    const seen = new Map<string, { code: string; name: string; envCodes: string[] }>();
    for (const ds of datasources) {
      if (ds.sysCode !== selectedSysCode) continue;
      const current = seen.get(ds.datasourceCode);
      if (current) {
        current.envCodes.push(ds.envCode);
      } else {
        seen.set(ds.datasourceCode, {
          code: ds.datasourceCode,
          name: ds.datasourceName,
          envCodes: [ds.envCode],
        });
      }
    }
    return Array.from(seen.values()).map((ds) => ({
      ...ds,
      envCodes: Array.from(new Set(ds.envCodes)).sort(),
    }));
  }, [datasources, step.sysCode]);

  const systemOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const sys of systems) {
      seen.set(sys.sysCode, sys.sysName);
    }
    for (const ds of datasources) {
      if (!seen.has(ds.sysCode)) seen.set(ds.sysCode, ds.sysCode);
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [datasources, systems]);

  /** 调用后端 API 解析 SQL，将结果回填到步骤的结构化字段中 */
  const handleParseSql = async () => {
    if (!rawSql.trim()) return;

    setParseStatus("parsing");
    setParseError(null);

    try {
      const parsed = await parseSqlSource(rawSql, step.parameters ?? []);

      // 保留已有的参数映射，仅添加新参数
      const nextParamMapping: Record<string, unknown> = {};
      for (const param of parsed.parameters) {
        const name = param.name;
        nextParamMapping[name] = step.paramMapping[name] ?? "";
      }

      onChange({
        ...step,
        sqlText: rawSql,
        normalizedSql: parsed.normalizedSql,
        operation: parsed.operation,
        tables: parsed.tables,
        resultFields: parsed.resultFields,
        conditionFields: parsed.conditionFields,
        parameters: parsed.parameters,
        safety: step.safety ?? { requireWhere: true, maxAffectedRows: null },
        paramMapping: nextParamMapping,
      });

      setParseStatus("success");
      toast.success(`SQL 解析成功：${parsed.operation}，${parsed.parameters.length} 个参数`);
    } catch (err) {
      setParseStatus("error");
      const msg = err instanceof Error ? err.message : "SQL 解析失败";
      setParseError(msg);
      toast.error(msg);
    }
  };

  /** SQL 文本变化时，更新 sqlText 并清空旧解析快照，标记为需要重新解析 */
  const handleSqlChange = (value: string) => {
    setRawSql(value);
    if (value !== step.sqlText) {
      onChange({
        ...step,
        sqlText: value,
        normalizedSql: "",
        tables: [],
        resultFields: [],
        conditionFields: [],
        parameters: [],
      });
      setParseStatus(value.trim() ? "stale" : "idle");
    }
  };

  /** 从解析结果的 resultFields 快速添加输出映射 */
  const handleAddFromResultFields = () => {
    if (!step.resultFields?.length) return;
    const nextMapping = { ...step.outputMapping };
    const nextMeta = { ...(step.outputMeta ?? {}) };

    for (const field of step.resultFields) {
      const varName = field.alias || field.fieldName;
      if (!varName || nextMapping[varName]) continue;
      nextMapping[varName] = field.fieldName;
      nextMeta[varName] = {
        label: field.description || field.alias || field.fieldName,
        remark: `来自表 ${field.sourceTable || ""}`,
      };
    }

    onChange({ ...step, outputMapping: nextMapping, outputMeta: nextMeta });
    toast.success(`已从解析结果添加 ${step.resultFields.length} 个输出字段`);
  };

  const updateTables = (tables: SqlSourceTableMeta[]) => {
    onChange({ ...step, tables });
  };

  const updateResultFields = (resultFields: SqlSourceFieldMeta[]) => {
    onChange({ ...step, resultFields });
  };

  const updateConditionFields = (conditionFields: SqlSourceConditionMeta[]) => {
    onChange({ ...step, conditionFields });
  };

  const updateParameterDefinition = (
    index: number,
    updates: Partial<SqlSourceParameter>,
  ) => {
    const next = [...(step.parameters ?? [])];
    const current = next[index];
    if (!current) return;
    next[index] = { ...current, ...updates };
    onChange({ ...step, parameters: next });
  };

  const tables = step.tables ?? [];
  const resultFields = step.resultFields ?? [];
  const conditionFields = step.conditionFields ?? [];
  const parameterDefinitions = step.parameters ?? [];

  const parseStatusBadge = () => {
    switch (parseStatus) {
      case "parsing":
        return <Badge variant="secondary" className="text-[9px] h-4 gap-1"><Loader2Icon className="size-3 animate-spin" />解析中</Badge>;
      case "success":
        return <Badge variant="default" className="text-[9px] h-4 gap-1 bg-emerald-600"><CheckCircleIcon className="size-3" />已解析</Badge>;
      case "error":
        return <Badge variant="destructive" className="text-[9px] h-4">解析失败</Badge>;
      case "stale":
        return <Badge variant="outline" className="text-[9px] h-4 text-amber-600 border-amber-300">需重新解析</Badge>;
      default:
        return rawSql.trim() ? <Badge variant="secondary" className="text-[9px] h-4">未解析</Badge> : null;
    }
  };

  return (
    <div className="space-y-4">
      <section className="space-y-3 rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-sm font-bold text-foreground">
            <DatabaseIcon className="size-4 text-primary" />
            <span>基本信息</span>
          </div>
          {parseStatusBadge()}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">所属系统</span>
            <Select
              value={step.sysCode ?? "__none__"}
              onValueChange={(value) =>
                onChange({
                  ...step,
                  sysCode: value === "__none__" ? "" : value,
                  datasourceCode: "",
                })
              }
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="选择系统" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__" className="text-xs">未选择系统</SelectItem>
                {systemOptions.map((sys) => (
                  <SelectItem key={sys.code} value={sys.code} className="text-xs">
                    {sys.name} ({sys.code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">数据源</span>
            <Select
              value={step.datasourceCode ?? "__none__"}
              onValueChange={(value) =>
                onChange({
                  ...step,
                  datasourceCode: value === "__none__" ? "" : value,
                })
              }
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder={step.sysCode ? "选择数据源" : "先选择系统"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__" className="text-xs">未选择数据源</SelectItem>
                {datasourceOptions.map((ds) => (
                  <SelectItem key={ds.code} value={ds.code} className="text-xs">
                    {ds.name} ({ds.code}) - {ds.envCodes.join(", ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">操作类型</span>
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
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">安全策略</span>
            <label className="flex h-8 items-center gap-2 rounded-md border bg-muted/30 px-3 text-[10px] text-muted-foreground">
              <input
                type="checkbox"
                checked={step.safety?.requireWhere ?? true}
                onChange={(e) =>
                  onChange({
                    ...step,
                    safety: {
                      ...step.safety,
                      requireWhere: e.target.checked,
                      maxAffectedRows: step.safety?.maxAffectedRows ?? null,
                    },
                  })
                }
              />
              UPDATE/DELETE 必须有 WHERE
            </label>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-sm font-bold text-emerald-600">
            <FileCodeIcon className="size-4" />
            <span>原始 SQL 语句</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 text-[10px]"
            onClick={handleParseSql}
            disabled={!rawSql.trim() || parseStatus === "parsing"}
          >
            {parseStatus === "parsing" ? (
              <Loader2Icon className="size-3 animate-spin" />
            ) : (
              <ListChecksIcon className="size-3" />
            )}
            {parseStatus === "success" ? "重新解析 SQL" : "解析 SQL"}
          </Button>
        </div>
        <Textarea
          className="min-h-[220px] resize-y font-mono text-xs"
          placeholder={'支持直接粘贴可执行 SQL、:userId、#{userId}、${tenantId}，也支持 MyBatis XML 片段。\n\n<select id="queryUser">\n  SELECT u.id, u.name FROM user_account u WHERE u.id = #{userId}\n</select>'}
          value={rawSql}
          onChange={(e) => handleSqlChange(e.target.value)}
        />
        <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
          <Badge variant="outline" className="font-mono">
            {step.operation ?? "UPDATE"}
          </Badge>
          <span>表 {tables.length}</span>
          <span>查询字段 {resultFields.length}</span>
          <span>条件字段 {conditionFields.length}</span>
          <span>参数 {parameterDefinitions.length}</span>
        </div>
        {parseStatus === "error" && parseError && (
          <div className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-[10px] text-destructive">
            {parseError}
          </div>
        )}
        {parseStatus === "stale" && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-600 dark:bg-amber-950/20">
            SQL 已修改，请点击&ldquo;解析 SQL&rdquo;重新生成标准 SQL、表字段和参数。
          </div>
        )}
      </section>

      <Collapsible
        open={analysisOpen}
        onOpenChange={setAnalysisOpen}
        className="overflow-hidden rounded-lg border bg-card"
      >
        <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-bold text-sky-600">
              <ListChecksIcon className="size-4" />
              <span>SQL 解析详情</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
              <Badge variant="outline" className="font-mono">
                {step.operation ?? "UPDATE"}
              </Badge>
              <span>表 {tables.length}</span>
              <span>查询字段 {resultFields.length}</span>
              <span>条件字段 {conditionFields.length}</span>
            </div>
          </div>
          <ChevronDownIcon
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform",
              analysisOpen && "rotate-180",
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 border-t p-4">
          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-sm font-bold text-sky-600">
                <ListChecksIcon className="size-4" />
                <span>格式化后SQL</span>
              </div>
            </div>
            <Textarea
              value={step.normalizedSql ?? ""}
              readOnly
              placeholder="请点击解析SQL按钮解析成系统规范的SQL"
              className="min-h-24 resize-y bg-muted/30 font-mono text-xs"
            />
          </section>

          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-sm font-bold text-blue-600">
                <TableIcon className="size-4" />
                <span>操作表说明</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="解析 SQL 后自动展示操作表"
              columns={["表名", "别名", "描述"]}
              gridTemplateColumns={TABLE_META_GRID}
              rows={tables}
              renderRow={(row, index) => (
                <div key={row.id} className="grid gap-2 p-1.5" style={{ gridTemplateColumns: TABLE_META_GRID }}>
                  <Input
                    value={row.tableName}
                    onChange={(e) => {
                      const next = [...tables];
                      next[index] = { ...row, tableName: e.target.value };
                      updateTables(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.alias}
                    onChange={(e) => {
                      const next = [...tables];
                      next[index] = { ...row, alias: e.target.value };
                      updateTables(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description}
                    onChange={(e) => {
                      const next = [...tables];
                      next[index] = { ...row, description: e.target.value };
                      updateTables(next);
                    }}
                    placeholder="填写表用途说明"
                    className="h-7 text-[10px]"
                  />
                </div>
              )}
            />
          </section>

          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-sm font-bold text-cyan-600">
                <DatabaseIcon className="size-4" />
                <span>查询结果字段</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="SELECT SQL 解析后自动展示查询字段"
              columns={["字段名", "来源表", "别名", "描述"]}
              gridTemplateColumns={RESULT_FIELD_META_GRID}
              rows={resultFields}
              renderRow={(row, index) => (
                <div key={row.id} className="grid gap-2 p-1.5" style={{ gridTemplateColumns: RESULT_FIELD_META_GRID }}>
                  <Input
                    value={row.fieldName}
                    onChange={(e) => {
                      const next = [...resultFields];
                      next[index] = { ...row, fieldName: e.target.value };
                      updateResultFields(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.sourceTable}
                    onChange={(e) => {
                      const next = [...resultFields];
                      next[index] = { ...row, sourceTable: e.target.value };
                      updateResultFields(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.alias}
                    onChange={(e) => {
                      const next = [...resultFields];
                      next[index] = { ...row, alias: e.target.value };
                      updateResultFields(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description}
                    onChange={(e) => {
                      const next = [...resultFields];
                      next[index] = { ...row, description: e.target.value };
                      updateResultFields(next);
                    }}
                    placeholder="填写字段含义"
                    className="h-7 text-[10px]"
                  />
                </div>
              )}
            />
          </section>

          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-sm font-bold text-amber-600">
                <ListChecksIcon className="size-4" />
                <span>条件字段</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="WHERE、JOIN ON 或 UPDATE 条件解析后自动展示"
              columns={["字段名", "来源表", "参数名", "描述"]}
              gridTemplateColumns={CONDITION_FIELD_META_GRID}
              rows={conditionFields}
              renderRow={(row, index) => (
                <div key={row.id} className="grid gap-2 p-1.5" style={{ gridTemplateColumns: CONDITION_FIELD_META_GRID }}>
                  <Input
                    value={row.fieldName}
                    onChange={(e) => {
                      const next = [...conditionFields];
                      next[index] = { ...row, fieldName: e.target.value };
                      updateConditionFields(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.sourceTable}
                    onChange={(e) => {
                      const next = [...conditionFields];
                      next[index] = { ...row, sourceTable: e.target.value };
                      updateConditionFields(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.paramName}
                    onChange={(e) => {
                      const next = [...conditionFields];
                      next[index] = { ...row, paramName: e.target.value };
                      updateConditionFields(next);
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description}
                    onChange={(e) => {
                      const next = [...conditionFields];
                      next[index] = { ...row, description: e.target.value };
                      updateConditionFields(next);
                    }}
                    placeholder="填写条件用途"
                    className="h-7 text-[10px]"
                  />
                </div>
              )}
            />
          </section>
        </CollapsibleContent>
      </Collapsible>

      <section className="space-y-3 rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-sm font-bold text-violet-600">
            <ListChecksIcon className="size-4" />
            <span>SQL 参数定义</span>
          </div>
        </div>
        <EditableMetaTable
          emptyText="解析 SQL 后自动生成参数"
          columns={["参数名", "类型", "必填", "默认值", "描述"]}
          gridTemplateColumns={PARAMETER_META_GRID}
          rows={parameterDefinitions}
          renderRow={(row, index) => (
            <div key={row.name} className="grid gap-2 p-1.5" style={{ gridTemplateColumns: PARAMETER_META_GRID }}>
              <Input
                value={row.name}
                onChange={(e) => updateParameterDefinition(index, { name: e.target.value })}
                className="h-7 text-[10px] font-mono"
              />
              <Select
                value={String(row.type || "string")}
                onValueChange={(value) => updateParameterDefinition(index, { type: value })}
              >
                <SelectTrigger className="h-7 w-full text-[10px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SQL_PARAMETER_TYPES.map((type) => (
                    <SelectItem key={type} value={type} className="text-xs">
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={row.required ? "true" : "false"}
                onValueChange={(value) =>
                  updateParameterDefinition(index, { required: value === "true" })
                }
              >
                <SelectTrigger className="h-7 w-full text-[10px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true" className="text-xs">是</SelectItem>
                  <SelectItem value="false" className="text-xs">否</SelectItem>
                </SelectContent>
              </Select>
              <Input
                value={safeStringify(row.defaultValue)}
                onChange={(e) => updateParameterDefinition(index, { defaultValue: e.target.value })}
                className="h-7 text-[10px] font-mono"
              />
              <Input
                value={row.description ?? ""}
                onChange={(e) => updateParameterDefinition(index, { description: e.target.value })}
                placeholder="填写参数用途"
                className="h-7 text-[10px]"
              />
            </div>
          )}
        />
      </section>

      <section className="space-y-3 rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-sm font-bold text-indigo-600">
            <VariableIcon className="size-4" />
            <span>SQL 参数绑定</span>
          </div>
          {parameterDefinitions.length > 0 && (
            <Badge variant="secondary" className="h-4 text-[9px]">
              {parameterDefinitions.length} 个参数
            </Badge>
          )}
        </div>
        <div className="overflow-hidden rounded-lg border bg-muted/20">
          <div className="grid grid-cols-[140px_1fr_80px] gap-4 bg-muted/40 px-4 py-2 text-[9px] font-bold uppercase text-muted-foreground">
            <div>SQL 变量名</div>
            <div>映射到场景变量</div>
            <div>必填/默认</div>
          </div>
          <div className="space-y-2 p-2">
            {parameterDefinitions.map((param) => {
              const key = param.name;
              const val = safeStringify(step.paramMapping[key]);
              const isVar = !!(val && isVariableRef(val));
              const displayVal = isVar
                ? resolveVariableLabel(val, scene, step.stepId)
                : val;

              return (
                <div key={key} className="grid grid-cols-[140px_1fr_80px] items-center gap-2">
                  <div className="px-2 font-mono text-[11px] font-bold text-primary">:{key}</div>
                  <div className="relative">
                    <input
                      className={cn(
                        "flex h-8 w-full rounded-md border border-input bg-background px-3 py-1 pr-8 text-[10px] shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                        isVar && "bg-blue-50/50 font-medium text-blue-700 dark:bg-blue-950/30 dark:text-blue-300",
                        !isVar && "font-mono",
                      )}
                      value={displayVal}
                      title={isVar ? val : undefined}
                      readOnly={isVar}
                      placeholder={param.defaultValue != null ? `默认: ${safeStringify(param.defaultValue)}` : "输入值或选择变量"}
                      onChange={(e) => {
                        const next = { ...step.paramMapping, [key]: e.target.value };
                        onChange({ ...step, paramMapping: next });
                      }}
                    />
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
                  <div className="px-2 text-[9px] text-muted-foreground">
                    {param.required ? (
                      <span className="font-bold text-destructive">必填</span>
                    ) : param.defaultValue != null ? (
                      <span>默认: {safeStringify(param.defaultValue)}</span>
                    ) : (
                      <span>可选</span>
                    )}
                  </div>
                </div>
              );
            })}
            {parameterDefinitions.length === 0 && (
              <div className="py-6 text-center text-[10px] italic text-muted-foreground">
                {parseStatus === "success"
                  ? "此 SQL 无参数"
                  : "解析 SQL 语句后自动生成参数列表"}
              </div>
            )}
          </div>
        </div>
      </section>

      <SqlOutputExtractionSection
        step={step}
        onChange={onChange}
        resultFields={resultFields}
        onAddFromResultFields={resultFields.length ? handleAddFromResultFields : undefined}
      />
    </div>
  );
}

function EditableMetaTable<T>({
  columns,
  gridTemplateColumns,
  rows,
  emptyText,
  renderRow,
}: {
  columns: string[];
  gridTemplateColumns?: string;
  rows: T[];
  emptyText: string;
  renderRow: (row: T, index: number) => React.ReactNode;
}) {
  const template = gridTemplateColumns ?? `repeat(${columns.length}, minmax(0, 1fr))`;

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div
        className="grid gap-2 border-b bg-muted/40 p-1.5 py-2 text-[10px] font-bold uppercase text-muted-foreground"
        style={{ gridTemplateColumns: template }}
      >
        {columns.map((column) => (
          <div key={column}>{column}</div>
        ))}
      </div>
      <div className="divide-y divide-border/50">
        {rows.length > 0 ? (
          rows.map(renderRow)
        ) : (
          <div className="py-8 text-center text-xs text-muted-foreground">
            {emptyText}
          </div>
        )}
      </div>
    </div>
  );
}
