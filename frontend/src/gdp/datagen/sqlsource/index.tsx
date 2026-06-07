"use client";

import {
  ArrowLeftIcon,
  CopyIcon,
  DatabaseIcon,
  EyeIcon,
  FileCodeIcon,
  ListChecksIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SaveIcon,
  SearchIcon,
  TableIcon,
  Trash2Icon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

import { ConfirmDialog } from "../common/ui/confirm-dialog";

import {
  createSqlSource,
  deleteSqlSource,
  listDatasources,
  listSystems,
  listSqlSources,
  parseSqlSource,
  updateSqlSource,
} from "../common/lib/api";
import { createDefaultSqlSource } from "../common/lib/defaults";
import { systemNameByCode } from "../baseconfig/config-helpers";
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
const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

type SqlAnalysis = SqlSourceParseResponse;

export function SqlSourceManagement() {
  const [sources, setSources] = useState<SqlSourceResponse[]>([]);
  const [datasources, setDatasources] = useState<DatasourceResponse[]>([]);
  const [systems, setSystems] = useState<SysResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<SqlSourceConfig | null>(null);
  const [editorMode, setEditorMode] = useState<"edit" | "view" | null>(null);
  const [operationFilter, setOperationFilter] = useState<SqlOperation | "ALL">("ALL");
  const [sysCodeFilter, setSysCodeFilter] = useState("ALL");
  const [sqlTextFilter, setSqlTextFilter] = useState("");
  const [descriptionFilter, setDescriptionFilter] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(10);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

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
    setEditorMode("edit");
  };

  const handleView = (source: SqlSourceResponse) => {
    setEditing({ ...source });
    setEditorMode("view");
  };

  const handleEdit = (source: SqlSourceResponse) => {
    setEditing({ ...source });
    setEditorMode("edit");
  };

  const handleCopy = (source: SqlSourceResponse) => {
    setEditing({
      ...source,
      sourceCode: nextCopyCode(
        source.sourceCode,
        sources.map((item) => item.sourceCode),
      ),
      sourceName: `${source.sourceName} 副本`,
      status: "ENABLED",
    });
    setEditorMode("edit");
  };

  const closeEditor = () => {
    setEditing(null);
    setEditorMode(null);
  };

  const handleSave = async (config: SqlSourceConfig) => {
    const isNew = !sources.some((s) => s.sourceCode === config.sourceCode);
    try {
      const payload = sanitizeSqlSourceConfig(config);
      if (isNew) {
        await createSqlSource(payload);
        toast.success("SQL 配置已创建");
      } else {
        await updateSqlSource(payload.sourceCode, payload);
        toast.success("SQL 配置已保存");
      }
      closeEditor();
      await reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    await deleteSqlSource(deleteTarget);
    toast.success("已删除");
    setDeleteTarget(null);
    await reload();
  };

  const filteredSources = useMemo(() => {
    const sqlKeyword = sqlTextFilter.trim().toLowerCase();
    const descriptionKeyword = descriptionFilter.trim().toLowerCase();
    return sources.filter((source) => {
      if (operationFilter !== "ALL" && source.operation !== operationFilter) return false;
      if (sysCodeFilter !== "ALL" && source.sysCode !== sysCodeFilter) return false;
      if (sqlKeyword && !source.sqlText.toLowerCase().includes(sqlKeyword)) return false;
      if (
        descriptionKeyword &&
        !source.sourceName.toLowerCase().includes(descriptionKeyword)
      ) {
        return false;
      }
      return true;
    });
  }, [descriptionFilter, operationFilter, sources, sqlTextFilter, sysCodeFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredSources.length / pageSize));
  const safePage = Math.min(page, totalPages - 1);
  const pageRows = filteredSources.slice(
    safePage * pageSize,
    safePage * pageSize + pageSize,
  );

  const resetFilters = () => {
    setOperationFilter("ALL");
    setSysCodeFilter("ALL");
    setSqlTextFilter("");
    setDescriptionFilter("");
    setPage(0);
  };

  if (editing && editorMode) {
    const isNew = !sources.some((s) => s.sourceCode === editing.sourceCode);
    return (
      <SqlSourceEditor
        config={editing}
        datasources={datasources}
        systems={systems}
        mode={editorMode}
        isNew={isNew}
        onChange={setEditing}
        onCancel={closeEditor}
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
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-md border bg-muted/20 p-3 md:grid-cols-2 xl:grid-cols-[160px_220px_minmax(180px,1fr)_minmax(180px,1fr)_auto]">
          <Select
            value={operationFilter}
            onValueChange={(value) => {
              setOperationFilter(value as SqlOperation | "ALL");
              setPage(0);
            }}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder="操作类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">全部类型</SelectItem>
              {SQL_OPERATIONS.map((operation) => (
                <SelectItem key={operation} value={operation} className="text-xs">
                  {operation}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={sysCodeFilter}
            onValueChange={(value) => {
              setSysCodeFilter(value);
              setPage(0);
            }}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder="所属系统" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">全部系统</SelectItem>
              {systems.map((sys) => (
                <SelectItem key={sys.sysCode} value={sys.sysCode} className="text-xs">
                  {sys.sysName} ({sys.sysCode})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-2 top-2 size-4 text-muted-foreground" />
            <Input
              value={sqlTextFilter}
              onChange={(event) => {
                setSqlTextFilter(event.target.value);
                setPage(0);
              }}
              placeholder="筛选 SQL 内容"
              className="h-8 pl-8 text-xs"
            />
          </div>
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-2 top-2 size-4 text-muted-foreground" />
            <Input
              value={descriptionFilter}
              onChange={(event) => {
                setDescriptionFilter(event.target.value);
                setPage(0);
              }}
              placeholder="筛选 SQL 描述"
              className="h-8 pl-8 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={resetFilters}>
            重置
          </Button>
        </div>

        {loading ? (
          <p className="text-muted-foreground">加载中...</p>
        ) : sources.length === 0 ? (
          <p className="text-muted-foreground">
            暂无 SQL 配置，点击&quot;新增 SQL&quot;创建。
          </p>
        ) : (
          <div className="rounded-lg border bg-card">
            <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-xs font-medium text-muted-foreground whitespace-nowrap">
                    编码 / 描述
                  </th>
                  <th className="w-[80px] px-2 py-2 text-xs font-medium text-muted-foreground whitespace-nowrap">
                    类型
                  </th>
                  <th className="w-[160px] px-3 py-2 text-xs font-medium text-muted-foreground whitespace-nowrap">
                    系统 / 数据源
                  </th>
                  <th className="w-[30%] px-3 py-2 text-xs font-medium text-muted-foreground whitespace-nowrap">
                    SQL
                  </th>
                  <th className="w-[72px] px-2 py-2 text-center text-xs font-medium text-muted-foreground whitespace-nowrap">
                    状态
                  </th>
                  <th className="w-[120px] px-2 py-2 text-right text-xs font-medium text-muted-foreground whitespace-nowrap">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-10 text-center text-muted-foreground">
                      没有匹配的 SQL 配置
                    </td>
                  </tr>
                ) : (
                  pageRows.map((source) => (
                    <tr key={source.id} className="border-b last:border-b-0 hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-2.5">
                        <div className="flex flex-col gap-0.5">
                          <span className="font-mono text-xs font-medium text-foreground">
                            {source.sourceCode}
                          </span>
                          <span className="truncate text-[11px] text-muted-foreground max-w-[220px]">
                            {source.sourceName}
                          </span>
                        </div>
                      </td>
                      <td className="px-2 py-2.5">
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[10px] px-1.5",
                            source.operation === "SELECT" && "text-blue-600 border-blue-200",
                            source.operation === "INSERT" && "text-emerald-600 border-emerald-200",
                            source.operation === "UPDATE" && "text-amber-600 border-amber-200",
                            source.operation === "DELETE" && "text-red-600 border-red-200",
                          )}
                        >
                          {source.operation}
                        </Badge>
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-xs">
                            {systemNameByCode(systems, source.sysCode)}
                          </span>
                          <span className="truncate font-mono text-[10px] text-muted-foreground" title={source.datasourceCode}>
                            {source.datasourceCode || "-"}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className="block font-mono text-[11px] text-muted-foreground"
                          title={source.sqlText}
                        >
                          {source.sqlText.length > 50
                            ? source.sqlText.slice(0, 50) + "..."
                            : source.sqlText}
                        </span>
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        <Badge
                          variant={source.status === "ENABLED" ? "default" : "secondary"}
                          className="text-[10px] px-1.5"
                        >
                          {source.status === "ENABLED" ? "启用" : "停用"}
                        </Badge>
                      </td>
                      <td className="px-2 py-2.5">
                        <SqlRowActions
                          source={source}
                          onView={() => handleView(source)}
                          onEdit={() => handleEdit(source)}
                          onCopy={() => handleCopy(source)}
                          onDelete={() => setDeleteTarget(source.sourceCode)}
                        />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
            <SqlTablePager
              page={safePage}
              pageSize={pageSize}
              total={filteredSources.length}
              onPageChange={setPage}
              onPageSizeChange={(next) => {
                setPageSize(next);
                setPage(0);
              }}
            />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        onConfirm={confirmDelete}
        title="删除 SQL 配置"
        description={`确定删除 SQL 配置 "${deleteTarget}" 吗？此操作不可撤销。`}
      />
    </div>
  );
}

/* ── Row Actions (dropdown menu) ──────────────────────────────── */

function SqlRowActions({
  source,
  onView,
  onEdit,
  onCopy,
  onDelete,
}: {
  source: SqlSourceResponse;
  onView: () => void;
  onEdit: () => void;
  onCopy: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-end gap-0.5">
      <Button
        variant="ghost"
        size="icon-sm"
        title="查看"
        onClick={onView}
        className="text-muted-foreground hover:text-foreground"
      >
        <EyeIcon className="size-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        title="编辑"
        onClick={onEdit}
        className="text-muted-foreground hover:text-foreground"
      >
        <PencilIcon className="size-3.5" />
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            title="更多操作"
            className="text-muted-foreground hover:text-foreground"
          >
            <MoreHorizontalIcon className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onCopy}>
            <CopyIcon className="mr-2 size-3.5" />
            复制为新 SQL
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={onDelete}
            className="text-destructive focus:text-destructive"
          >
            <Trash2Icon className="mr-2 size-3.5" />
            删除
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

function SqlTablePager({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : page * pageSize + 1;
  const end = Math.min(total, (page + 1) * pageSize);

  return (
    <div className="flex items-center justify-between border-t px-3 py-2">
      <div className="text-xs text-muted-foreground">
        显示 {start}-{end} / 共 {total} 条
      </div>
      <div className="flex items-center gap-2">
        <Select
          value={String(pageSize)}
          onValueChange={(value) => onPageSizeChange(Number(value))}
        >
          <SelectTrigger className="h-8 w-[96px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <SelectItem key={size} value={String(size)} className="text-xs">
                {size} 条/页
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 0}
          onClick={() => onPageChange(page - 1)}
        >
          上一页
        </Button>
        <span className="text-xs text-muted-foreground">
          {page + 1} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages - 1}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  );
}

function nextCopyCode(code: string, existingCodes: string[]) {
  const existing = new Set(existingCodes);
  let candidate = `${code}_copy`;
  let index = 2;
  while (existing.has(candidate)) {
    candidate = `${code}_copy_${index}`;
    index += 1;
  }
  return candidate;
}

function SqlSourceEditor({
  config,
  datasources,
  systems,
  mode,
  isNew,
  onChange,
  onCancel,
  onSave,
}: {
  config: SqlSourceConfig;
  datasources: DatasourceResponse[];
  systems: SysResponse[];
  mode: "edit" | "view";
  isNew: boolean;
  onChange: (config: SqlSourceConfig) => void;
  onCancel: () => void;
  onSave: (config: SqlSourceConfig) => void;
}) {
  const readOnly = mode === "view";
  const [analysis, setAnalysis] = useState<SqlAnalysis>(() =>
    createInitialAnalysis(config),
  );
  const [parsing, setParsing] = useState(false);

  const datasourceOptions = useMemo(() => {
    const seen = new Map<string, { code: string; name: string; envCodes: string[] }>();
    for (const ds of datasources) {
      if (ds.sysCode !== config.sysCode) continue;
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
  }, [config.sysCode, datasources]);

  const parseCurrentSql = async () => {
    setParsing(true);
    try {
      const parsed = await parseSqlSource(config.sqlText, config.parameters);
      const next = mergeAnalysisDescriptions(parsed, analysis);
      setAnalysis(next);
      onChange({
        ...config,
        operation: next.operation,
        normalizedSql: next.normalizedSql,
        tables: next.tables,
        resultFields: next.resultFields,
        conditionFields: next.conditionFields,
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
    const next = { ...analysis, ...updates };
    setAnalysis(next);
    onChange({
      ...config,
      normalizedSql: next.normalizedSql,
      operation: next.operation,
      tables: next.tables,
      resultFields: next.resultFields,
      conditionFields: next.conditionFields,
      parameters: next.parameters,
    });
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
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-3 border-b px-4 py-2">
        <Button variant="ghost" size="icon-sm" onClick={onCancel}>
          <ArrowLeftIcon className="size-4" />
        </Button>
        <h2 className="text-sm font-semibold">
          {readOnly
            ? `查看: ${config.sourceCode}`
            : isNew
              ? "新增 SQL 配置"
              : `编辑: ${config.sourceCode}`}
        </h2>
        <div className="ml-auto flex items-center gap-2">
          {readOnly ? (
            <>
              <Badge variant="outline">只读</Badge>
              <Button variant="outline" size="sm" onClick={onCancel}>
                返回
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={onCancel}>
                取消
              </Button>
              <Button size="sm" onClick={() => onSave(config)}>
                <SaveIcon className="mr-1 size-3" />
                保存
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className={readOnly ? "pointer-events-none mx-auto max-w-6xl space-y-4 p-4 opacity-50" : "mx-auto max-w-6xl space-y-4 p-4"}>
          <section className="space-y-3 rounded-lg border bg-card p-4">
            <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
            <div className="grid grid-cols-4 gap-x-4 gap-y-3">
              {/* Row 1: SQL编码 + 操作类型 + 状态 */}
              <div className="col-span-2 space-y-1">
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
                      <SelectItem key={operation} value={operation} className="text-xs">
                        {operation}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                    <SelectItem value="ENABLED" className="text-xs">启用</SelectItem>
                    <SelectItem value="DISABLED" className="text-xs">停用</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: 所属系统 + 数据源 */}
              <div className="col-span-2 space-y-1">
                <Label className="text-xs">所属系统</Label>
                <Select
                  value={config.sysCode || "__none__"}
                  onValueChange={(v) =>
                    onChange({
                      ...config,
                      sysCode: v === "__none__" ? "" : v,
                      datasourceCode: "",
                    })
                  }
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="选择系统" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__" className="text-xs">未选择</SelectItem>
                    {systems.map((sys) => (
                      <SelectItem key={sys.sysCode} value={sys.sysCode} className="text-xs">
                        {sys.sysName} ({sys.sysCode})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2 space-y-1">
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
                    <SelectValue placeholder={config.sysCode ? "选择数据源" : "先选择系统"} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__" className="text-xs">未选择</SelectItem>
                    {datasourceOptions.map((ds) => (
                      <SelectItem key={ds.code} value={ds.code} className="text-xs">
                        {ds.name} ({ds.code}) - {ds.envCodes.join(", ")}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Row 3: 描述 (full width) */}
              <div className="col-span-4 space-y-1">
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
    normalizedSql: config.normalizedSql || config.sqlText,
    tables: config.tables ?? [],
    resultFields: config.resultFields ?? [],
    conditionFields: config.conditionFields ?? [],
    parameters: config.parameters ?? [],
  };
}

function createInitialAnalysis(config: SqlSourceConfig): SqlAnalysis {
  return {
    normalizedSql: config.normalizedSql || config.sqlText,
    operation: config.operation,
    tables: config.tables ?? [],
    resultFields: config.resultFields ?? [],
    conditionFields: config.conditionFields ?? [],
    parameters: config.parameters ?? [],
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
