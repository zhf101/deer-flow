"use client";

import {
  ArrowLeftIcon,
  DatabaseIcon,
  FileCodeIcon,
  ListChecksIcon,
  PencilIcon,
  PlusIcon,
  PowerIcon,
  SaveIcon,
  TableIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import {
  createSqlSource,
  disableSqlSource,
  listDatasources,
  listSystems,
  listSqlSources,
  parseSqlSource,
  updateSqlSource,
} from "../common/lib/api";
import { createDefaultSqlSource } from "../common/lib/defaults";
import type {
  ConfigStatus,
  DatasourceResponse,
  InputFieldType,
  SqlOperation,
  SqlSourceConfig,
  SqlSourceConditionMeta,
  SqlSourceFieldMeta,
  SqlSourceParameter,
  SqlSourceParseResponse,
  SqlSourceResponse,
  SqlSourceTableMeta,
  SysResponse,
} from "../common/lib/types";

const SQL_OPERATIONS: SqlOperation[] = ["SELECT", "INSERT", "UPDATE", "DELETE"];
const FIELD_TYPES: InputFieldType[] = ["string", "number", "boolean", "date"];

type SqlAnalysis = SqlSourceParseResponse;

export function SqlSourceManagement() {
  const [sources, setSources] = useState<SqlSourceResponse[]>([]);
  const [datasources, setDatasources] = useState<DatasourceResponse[]>([]);
  const [systems, setSystems] = useState<SysResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<SqlSourceConfig | null>(null);
  const [isNew, setIsNew] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [s, d, systemItems] = await Promise.all([
        listSqlSources(),
        listDatasources(),
        listSystems(),
      ]);
      setSources(s);
      setDatasources(d);
      setSystems(systemItems);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleNew = () => {
    setEditing(createDefaultSqlSource());
    setIsNew(true);
  };

  const handleEdit = (source: SqlSourceResponse) => {
    setEditing({ ...source });
    setIsNew(false);
  };

  const handleSave = async (config: SqlSourceConfig) => {
    try {
      const payload = sanitizeSqlSourceConfig(config);
      if (isNew) {
        await createSqlSource(payload);
        toast.success("SQL 配置已创建");
      } else {
        await updateSqlSource(payload.sourceCode, payload);
        toast.success("SQL 配置已保存");
      }
      setEditing(null);
      await reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  };

  const handleDisable = async (code: string) => {
    await disableSqlSource(code);
    toast.success("已停用");
    await reload();
  };

  if (editing) {
    return (
      <SqlSourceEditor
        config={editing}
        datasources={datasources}
        systems={systems}
        isNew={isNew}
        onChange={setEditing}
        onCancel={() => setEditing(null)}
        onSave={handleSave}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <h2 className="text-lg font-semibold">SQL 配置</h2>
        <Button size="sm" onClick={handleNew}>
          <PlusIcon className="mr-1 size-4" /> 新增 SQL
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <p className="text-muted-foreground">加载中...</p>
        ) : sources.length === 0 ? (
          <p className="text-muted-foreground">
            暂无 SQL 配置，点击&quot;新增 SQL&quot;创建。
          </p>
        ) : (
          <div className="space-y-2">
            {sources.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between rounded-lg border p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-medium">{s.sourceCode}</span>
                    <Badge
                      variant={s.status === "ENABLED" ? "default" : "secondary"}
                    >
                      {s.status}
                    </Badge>
                    <Badge variant="outline">{s.operation}</Badge>
                    <Badge variant="outline" className="text-xs">
                      {s.datasourceCode}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {s.sourceName}
                  </p>
                  <p className="mt-0.5 max-w-xl truncate font-mono text-xs text-muted-foreground">
                    {s.sqlText.slice(0, 120)}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleEdit(s)}
                  >
                    <PencilIcon className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDisable(s.sourceCode)}
                  >
                    <PowerIcon className="size-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SqlSourceEditor({
  config,
  datasources,
  systems,
  isNew,
  onChange,
  onCancel,
  onSave,
}: {
  config: SqlSourceConfig;
  datasources: DatasourceResponse[];
  systems: SysResponse[];
  isNew: boolean;
  onChange: (config: SqlSourceConfig) => void;
  onCancel: () => void;
  onSave: (config: SqlSourceConfig) => void;
}) {
  const [analysis, setAnalysis] = useState<SqlAnalysis>(() =>
    createInitialAnalysis(config),
  );
  const [parsing, setParsing] = useState(false);

  const datasourceOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const ds of datasources) {
      if (!seen.has(ds.datasourceCode)) {
        const sysName =
          systems.find((sys) => sys.sysCode === ds.sysCode)?.sysName ??
          ds.sysCode;
        seen.set(
          ds.datasourceCode,
          `${ds.datasourceName} - ${sysName} (${ds.sysCode})`,
        );
      }
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [datasources, systems]);

  const parseCurrentSql = async () => {
    setParsing(true);
    try {
      const parsed = await parseSqlSource(config.sqlText, config.parameters);
      const next = mergeAnalysisDescriptions(parsed, analysis);
      setAnalysis(next);
      onChange({
        ...config,
        operation: next.operation,
        sqlText: next.normalizedSql || config.sqlText,
        parameters: next.parameters,
      });
      toast.success("SQL 已解析");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "SQL 解析失败");
    } finally {
      setParsing(false);
    }
  };

  const updateAnalysis = (updates: Partial<SqlAnalysis>) => {
    setAnalysis((current) => ({ ...current, ...updates }));
  };

  const updateParameter = (
    index: number,
    updates: Partial<SqlSourceParameter>,
  ) => {
    const next = [...analysis.parameters];
    const current = next[index];
    if (!current) return;
    next[index] = { ...current, ...updates };
    updateAnalysis({ parameters: next });
    onChange({ ...config, parameters: next });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-3 border-b px-4 py-2">
        <Button variant="ghost" size="icon-sm" onClick={onCancel}>
          <ArrowLeftIcon className="size-4" />
        </Button>
        <h2 className="text-sm font-semibold">
          {isNew ? "新增 SQL 配置" : `编辑: ${config.sourceCode}`}
        </h2>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            取消
          </Button>
          <Button size="sm" onClick={() => onSave(config)}>
            <SaveIcon className="mr-1 size-3" />
            保存
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl space-y-4 p-4">
          <section className="space-y-3 rounded-lg border bg-card p-4">
            <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
            <div className="grid grid-cols-[minmax(0,1fr)_140px_minmax(180px,240px)_140px] gap-4">
              <div className="space-y-1">
                <Label className="text-xs">SQL 编码</Label>
                <Input
                  value={config.sourceCode}
                  onChange={(e) =>
                    onChange({ ...config, sourceCode: e.target.value })
                  }
                  disabled={!isNew}
                  placeholder="如: queryUserById"
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">状态</Label>
                <Select
                  value={config.status}
                  onValueChange={(v) =>
                    onChange({ ...config, status: v as ConfigStatus })
                  }
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ENABLED" className="text-xs">
                      启用
                    </SelectItem>
                    <SelectItem value="DISABLED" className="text-xs">
                      停用
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">数据源</Label>
                <Select
                  value={config.datasourceCode || "__none__"}
                  onValueChange={(v) =>
                    onChange({
                      ...config,
                      datasourceCode: v === "__none__" ? "" : v,
                    })
                  }
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="选择数据源" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__" className="text-xs">
                      未选择
                    </SelectItem>
                    {datasourceOptions.map((ds) => (
                      <SelectItem key={ds.code} value={ds.code} className="text-xs">
                        {ds.name} ({ds.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">操作类型</Label>
                <Select
                  value={config.operation}
                  onValueChange={(v) =>
                    onChange({ ...config, operation: v as SqlOperation })
                  }
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SQL_OPERATIONS.map((operation) => (
                      <SelectItem
                        key={operation}
                        value={operation}
                        className="text-xs"
                      >
                        {operation}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">描述</Label>
              <Textarea
                value={config.sourceName}
                onChange={(e) =>
                  onChange({ ...config, sourceName: e.target.value })
                }
                placeholder="填写 SQL 的用途、适用场景、关键条件和调用注意事项，例如：按用户 ID 查询账户状态，供下游订单创建前校验用户是否可用。"
                className="min-h-20 resize-y text-xs"
              />
            </div>
          </section>

          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-emerald-600 text-sm font-bold">
                <FileCodeIcon className="size-4" />
                <span>原始 SQL 语句</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 text-[10px]"
                onClick={parseCurrentSql}
                disabled={!config.sqlText.trim() || parsing}
              >
                <ListChecksIcon className="size-3" />
                {parsing ? "解析中..." : "解析 SQL"}
              </Button>
            </div>
            <Textarea
              value={config.sqlText}
              onChange={(e) =>
                onChange({ ...config, sqlText: e.target.value })
              }
              placeholder={'支持直接粘贴可执行 SQL、:userId、#{userId}、${tenantId}，也支持 MyBatis XML 片段。\n\n<select id="queryUser">\n  SELECT u.id, u.name FROM user_account u WHERE u.id = #{userId}\n</select>'}
              className="min-h-[220px] resize-y font-mono text-xs"
            />
            <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
              <Badge variant="outline" className="font-mono">
                {analysis.operation}
              </Badge>
              <span>表 {analysis.tables.length}</span>
              <span>查询字段 {analysis.resultFields.length}</span>
              <span>条件字段 {analysis.conditionFields.length}</span>
              <span>参数 {analysis.parameters.length}</span>
            </div>
          </section>

          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-blue-600 text-sm font-bold">
                <TableIcon className="size-4" />
                <span>操作表说明</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="解析 SQL 后自动展示操作表"
              columns={["表名", "别名", "描述"]}
              rows={analysis.tables}
              renderRow={(row, index) => (
                <div
                  key={row.id}
                  className="grid grid-cols-[1fr_120px_2fr] gap-2 p-1.5"
                >
                  <Input
                    value={row.tableName}
                    onChange={(e) => {
                      const next = [...analysis.tables];
                      next[index] = { ...row, tableName: e.target.value };
                      updateAnalysis({ tables: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.alias}
                    onChange={(e) => {
                      const next = [...analysis.tables];
                      next[index] = { ...row, alias: e.target.value };
                      updateAnalysis({ tables: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description}
                    onChange={(e) => {
                      const next = [...analysis.tables];
                      next[index] = { ...row, description: e.target.value };
                      updateAnalysis({ tables: next });
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
              <div className="flex items-center gap-2 text-cyan-600 text-sm font-bold">
                <DatabaseIcon className="size-4" />
                <span>查询结果字段</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="SELECT SQL 解析后自动展示查询字段"
              columns={["字段名", "来源表", "别名", "描述"]}
              rows={analysis.resultFields}
              renderRow={(row, index) => (
                <div
                  key={row.id}
                  className="grid grid-cols-[1fr_140px_140px_2fr] gap-2 p-1.5"
                >
                  <Input
                    value={row.fieldName}
                    onChange={(e) => {
                      const next = [...analysis.resultFields];
                      next[index] = { ...row, fieldName: e.target.value };
                      updateAnalysis({ resultFields: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.sourceTable}
                    onChange={(e) => {
                      const next = [...analysis.resultFields];
                      next[index] = { ...row, sourceTable: e.target.value };
                      updateAnalysis({ resultFields: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.alias}
                    onChange={(e) => {
                      const next = [...analysis.resultFields];
                      next[index] = { ...row, alias: e.target.value };
                      updateAnalysis({ resultFields: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description}
                    onChange={(e) => {
                      const next = [...analysis.resultFields];
                      next[index] = { ...row, description: e.target.value };
                      updateAnalysis({ resultFields: next });
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
              <div className="flex items-center gap-2 text-amber-600 text-sm font-bold">
                <ListChecksIcon className="size-4" />
                <span>条件字段</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="WHERE、JOIN ON 或 UPDATE 条件解析后自动展示"
              columns={["字段名", "来源表", "参数名", "描述"]}
              rows={analysis.conditionFields}
              renderRow={(row, index) => (
                <div
                  key={row.id}
                  className="grid grid-cols-[1fr_140px_160px_2fr] gap-2 p-1.5"
                >
                  <Input
                    value={row.fieldName}
                    onChange={(e) => {
                      const next = [...analysis.conditionFields];
                      next[index] = { ...row, fieldName: e.target.value };
                      updateAnalysis({ conditionFields: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.sourceTable}
                    onChange={(e) => {
                      const next = [...analysis.conditionFields];
                      next[index] = { ...row, sourceTable: e.target.value };
                      updateAnalysis({ conditionFields: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.paramName}
                    onChange={(e) => {
                      const next = [...analysis.conditionFields];
                      next[index] = { ...row, paramName: e.target.value };
                      updateAnalysis({ conditionFields: next });
                    }}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description}
                    onChange={(e) => {
                      const next = [...analysis.conditionFields];
                      next[index] = { ...row, description: e.target.value };
                      updateAnalysis({ conditionFields: next });
                    }}
                    placeholder="填写条件用途"
                    className="h-7 text-[10px]"
                  />
                </div>
              )}
            />
          </section>

          <section className="space-y-3 rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between border-b pb-2">
              <div className="flex items-center gap-2 text-violet-600 text-sm font-bold">
                <ListChecksIcon className="size-4" />
                <span>SQL 参数定义</span>
              </div>
            </div>
            <EditableMetaTable
              emptyText="解析 SQL 后自动生成参数"
              columns={["参数名", "类型", "必填", "默认值", "描述"]}
              rows={analysis.parameters}
              renderRow={(row, index) => (
                <div
                  key={row.name}
                  className="grid grid-cols-[1fr_120px_100px_1fr_2fr] gap-2 p-1.5"
                >
                  <Input
                    value={row.name}
                    onChange={(e) => updateParameter(index, { name: e.target.value })}
                    className="h-7 text-[10px] font-mono"
                  />
                  <Select
                    value={String(row.type || "string")}
                    onValueChange={(value) => updateParameter(index, { type: value })}
                  >
                    <SelectTrigger className="h-7 text-[10px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FIELD_TYPES.map((type) => (
                        <SelectItem key={type} value={type} className="text-xs">
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={row.required ? "true" : "false"}
                    onValueChange={(value) =>
                      updateParameter(index, { required: value === "true" })
                    }
                  >
                    <SelectTrigger className="h-7 text-[10px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true" className="text-xs">
                        是
                      </SelectItem>
                      <SelectItem value="false" className="text-xs">
                        否
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    value={
                      row.defaultValue === undefined || row.defaultValue === null
                        ? ""
                        : String(row.defaultValue)
                    }
                    onChange={(e) =>
                      updateParameter(index, { defaultValue: e.target.value })
                    }
                    className="h-7 text-[10px] font-mono"
                  />
                  <Input
                    value={row.description ?? ""}
                    onChange={(e) =>
                      updateParameter(index, { description: e.target.value })
                    }
                    placeholder="填写参数用途"
                    className="h-7 text-[10px]"
                  />
                </div>
              )}
            />
          </section>
        </div>
      </div>
    </div>
  );
}

function EditableMetaTable<T>({
  columns,
  rows,
  emptyText,
  renderRow,
}: {
  columns: string[];
  rows: T[];
  emptyText: string;
  renderRow: (row: T, index: number) => React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div
        className="grid gap-2 border-b bg-muted/40 px-3 py-2 text-[10px] font-bold uppercase text-muted-foreground"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}
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

function sanitizeSqlSourceConfig(config: SqlSourceConfig): SqlSourceConfig {
  return {
    ...config,
    parameters: config.parameters,
  };
}

function createInitialAnalysis(config: SqlSourceConfig): SqlAnalysis {
  return {
    normalizedSql: config.sqlText,
    operation: config.operation,
    tables: [],
    resultFields: [],
    conditionFields: [],
    parameters: config.parameters,
  };
}

function mergeAnalysisDescriptions(next: SqlAnalysis, previous: SqlAnalysis): SqlAnalysis {
  return {
    ...next,
    tables: mergeTables(next.tables, previous.tables),
    resultFields: mergeFields(next.resultFields, previous.resultFields),
    conditionFields: mergeConditions(next.conditionFields, previous.conditionFields),
    parameters: mergeParameters(next.parameters, previous.parameters),
  };
}

function mergeTables(
  next: SqlSourceTableMeta[],
  previous: SqlSourceTableMeta[] = [],
): SqlSourceTableMeta[] {
  return next.map((row) => ({
    ...row,
    description:
      previous.find((item) => item.tableName === row.tableName && item.alias === row.alias)
        ?.description ?? "",
  }));
}

function mergeFields(
  next: SqlSourceFieldMeta[],
  previous: SqlSourceFieldMeta[] = [],
): SqlSourceFieldMeta[] {
  return next.map((row) => ({
    ...row,
    description:
      previous.find((item) => item.fieldName === row.fieldName && item.alias === row.alias)
        ?.description ?? "",
  }));
}

function mergeConditions(
  next: SqlSourceConditionMeta[],
  previous: SqlSourceConditionMeta[] = [],
): SqlSourceConditionMeta[] {
  return next.map((row) => ({
    ...row,
    description:
      previous.find(
        (item) => item.fieldName === row.fieldName && item.paramName === row.paramName,
      )?.description ?? "",
  }));
}

function mergeParameters(
  next: SqlSourceParameter[],
  previous: SqlSourceParameter[] = [],
): SqlSourceParameter[] {
  return next.map((row) => {
    const old = previous.find((item) => item.name === row.name);
    return {
      ...row,
      description: old?.description ?? row.description ?? null,
    };
  });
}
