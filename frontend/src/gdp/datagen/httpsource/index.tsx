"use client";

import {
  ArrowLeftIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  ClockIcon,
  CopyIcon,
  DownloadIcon,
  EyeIcon,
  FileTextIcon,
  Loader2Icon,
  MoreHorizontalIcon,
  PencilIcon,
  PlayCircleIcon,
  PlusIcon,
  Trash2Icon,
  SaveIcon,
  SearchIcon,
} from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { systemNameByCode } from "../baseconfig/config-helpers";
import {
  createHttpSource,
  deleteHttpSource,
  listEnvironments,
  listHttpSources,
  listServiceEndpoints,
  listSystems,
  testHttpSource,
  updateHttpSource,
} from "../common/lib/api";
import { createDefaultHttpSource, createDefaultHttpTimeoutConfig } from "../common/lib/defaults";
import { jsonToFields } from "../common/lib/schema-utils";
import type {
  ConfigStatus,
  EnvironmentResponse,
  HttpMethod,
  HttpSourceConfig,
  HttpSourceResponse,
  HttpSourceTestResult,
  HttpStepDefinition,
  InputFieldDefinition,
  ParsedCookie,
  ServiceEndpointResponse,
  SysResponse,
} from "../common/lib/types";
import { HttpResponseMappingEditor } from "../common/source-forms/http-response-mapping-editor";
import { HttpStepForm } from "../common/source-forms/http-step-form";
import { ConfirmDialog } from "../common/ui/confirm-dialog";

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

/* ── 适配器：HttpSourceConfig → HttpStepDefinition ── */

function configToHttpStep(config: HttpSourceConfig): HttpStepDefinition {
  return {
    stepId: config.sourceCode || "__httpsource__",
    stepName: config.sourceName,
    type: "HTTP",
    enabled: true,
    dependsOn: [],
    description: "",
    templateRef: null,
    httpParamMapping: {},
    method: config.method,
    path: config.path,
    sysCode: config.sysCode,
    requestMapping: config.requestMapping,
    timeoutConfig: config.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
    bodySchema: config.bodySchema,
    responseSchema: config.responseSchema,
    responseHeadersSchema: config.responseHeadersSchema,
    responseCookiesSchema: config.responseCookiesSchema,
    responseHandling: config.responseHandling,
    errorMapping: config.errorMapping,
    businessErrorMapping: config.businessErrorMapping,
    outputMapping: config.outputMapping,
    outputMeta: config.outputMeta,
    retryPolicy: config.retryPolicy,
  };
}

function buildResponseImportUpdates(result: HttpSourceTestResult): Partial<HttpSourceConfig> | null {
  if (result.response?.statusCode !== 200) return null;

  return {
    responseSchema: inferResponseSchema(result.response.body),
    responseHeadersSchema: Object.entries(result.response.headers ?? {}).map(
      ([name, value]) => ({
        name,
        type: "string",
        required: false,
        batchEnabled: false,
        defaultValue: value,
      }),
    ),
    responseCookiesSchema: (result.response.cookies ?? []).map((cookie) => ({
      name: cookie.name,
      type: "string",
      required: false,
      batchEnabled: false,
      defaultValue: cookie.value,
      domain: cookie.domain,
      path: cookie.path,
      expires: cookie.expires,
      httpOnly: cookie.httpOnly,
      secure: cookie.secure,
      sameSite: cookie.sameSite,
    }) as InputFieldDefinition),
    requestMapping: {
      _rawResponseSample: formatPreview(result.response.body ?? null),
    },
  };
}

function inferResponseSchema(body: unknown): InputFieldDefinition[] {
  if (Array.isArray(body)) {
    if (body.length === 0) return [];
    const first = body[0];
    if (isPlainRecord(first)) {
      return [
        {
          name: "0",
          label: "数组首项",
          remark: "顶层数组响应的首项结构",
          type: "object",
          required: false,
          batchEnabled: false,
          children: jsonToFields(first),
        },
      ];
    }
    return [
      {
        name: "0",
        label: "数组首项",
        remark: "顶层数组响应的首项示例值",
        type: inferFieldType(first),
        required: false,
        batchEnabled: false,
        defaultValue: first,
      },
    ];
  }

  if (isPlainRecord(body)) {
    return jsonToFields(body);
  }

  return [];
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function inferFieldType(value: unknown): InputFieldDefinition["type"] {
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  if (isPlainRecord(value)) return "object";
  if (Array.isArray(value)) return "array";
  return "string";
}

/* ── 主组件 ── */

export function HttpSourceManagement() {
  const [sources, setSources] = useState<HttpSourceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<HttpSourceConfig | null>(null);
  const [editorMode, setEditorMode] = useState<"edit" | "view" | null>(null);
  const [systems, setSystems] = useState<SysResponse[]>([]);
  const [methodFilter, setMethodFilter] = useState<HttpMethod | "ALL">("ALL");
  const [sysCodeFilter, setSysCodeFilter] = useState("ALL");
  const [pathFilter, setPathFilter] = useState("");
  const [descriptionFilter, setDescriptionFilter] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(10);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [sourceItems, systemItems] = await Promise.all([
        listHttpSources(),
        listSystems(),
      ]);
      setSources(sourceItems);
      setSystems(systemItems);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleNew = () => {
    setEditing(createDefaultHttpSource());
    setEditorMode("edit");
  };

  const handleView = (source: HttpSourceResponse) => {
    setEditing({
      ...source,
      responseSchema: source.responseSchema ?? null,
      responseHeadersSchema: source.responseHeadersSchema ?? null,
      responseCookiesSchema: source.responseCookiesSchema ?? null,
    });
    setEditorMode("view");
  };

  const handleEdit = (source: HttpSourceResponse) => {
    setEditing({
      ...source,
      responseSchema: source.responseSchema ?? null,
      responseHeadersSchema: source.responseHeadersSchema ?? null,
      responseCookiesSchema: source.responseCookiesSchema ?? null,
    });
    setEditorMode("edit");
  };

  const handleCopy = (source: HttpSourceResponse) => {
    setEditing({
      ...source,
      sourceCode: nextCopyCode(
        source.sourceCode,
        sources.map((item) => item.sourceCode),
      ),
      sourceName: `${source.sourceName} 副本`,
      responseSchema: source.responseSchema ?? null,
      responseHeadersSchema: source.responseHeadersSchema ?? null,
      responseCookiesSchema: source.responseCookiesSchema ?? null,
    });
    setEditorMode("edit");
  };

  const closeEditor = () => {
    setEditing(null);
    setEditorMode(null);
  };

  const handleSave = async () => {
    if (!editing) return;
    const isNew = !sources.some((s) => s.sourceCode === editing.sourceCode);
    try {
      if (isNew) {
        await createHttpSource(editing);
        toast.success("接口配置已创建");
      } else {
        await updateHttpSource(editing.sourceCode, editing);
        toast.success("接口配置已保存");
      }
      closeEditor();
      await reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    await deleteHttpSource(deleteTarget);
    toast.success("已删除");
    setDeleteTarget(null);
    await reload();
  };

  const filteredSources = useMemo(() => {
    const pathKeyword = pathFilter.trim().toLowerCase();
    const descriptionKeyword = descriptionFilter.trim().toLowerCase();
    return sources.filter((source) => {
      if (methodFilter !== "ALL" && source.method !== methodFilter) return false;
      if (sysCodeFilter !== "ALL" && source.sysCode !== sysCodeFilter) return false;
      if (pathKeyword && !source.path.toLowerCase().includes(pathKeyword)) return false;
      if (
        descriptionKeyword &&
        !source.sourceName.toLowerCase().includes(descriptionKeyword)
      ) {
        return false;
      }
      return true;
    });
  }, [descriptionFilter, methodFilter, pathFilter, sources, sysCodeFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredSources.length / pageSize));
  const safePage = Math.min(page, totalPages - 1);
  const pageRows = filteredSources.slice(
    safePage * pageSize,
    safePage * pageSize + pageSize,
  );

  const resetFilters = () => {
    setMethodFilter("ALL");
    setSysCodeFilter("ALL");
    setPathFilter("");
    setDescriptionFilter("");
    setPage(0);
  };

  /* ── 编辑视图 ── */
  if (editing && editorMode) {
    const isNew = !sources.some((s) => s.sourceCode === editing.sourceCode);
    return (
      <HttpSourceEditor
        config={editing}
        mode={editorMode}
        isNew={isNew}
        onChange={setEditing}
        onSave={handleSave}
        onCancel={closeEditor}
      />
    );
  }

  /* ── 列表视图 ── */
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <h2 className="text-lg font-semibold">HTTP 接口配置</h2>
        <Button size="sm" onClick={handleNew}>
          <PlusIcon className="mr-1 size-4" /> 新增接口
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-md border bg-muted/20 p-3 md:grid-cols-2 xl:grid-cols-[150px_minmax(180px,1fr)_minmax(160px,1fr)_minmax(160px,1fr)_auto] items-center">
          <Select
            value={methodFilter}
            onValueChange={(value) => {
              setMethodFilter(value as HttpMethod | "ALL");
              setPage(0);
            }}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder="请求方式" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL" className="text-xs">全部方式</SelectItem>
              <SelectItem value="GET" className="text-xs">GET</SelectItem>
              <SelectItem value="POST" className="text-xs">POST</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={sysCodeFilter}
            onValueChange={(value) => {
              setSysCodeFilter(value);
              setPage(0);
            }}
          >
            <SelectTrigger className="h-8 text-xs w-full">
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
              value={pathFilter}
              onChange={(event) => {
                setPathFilter(event.target.value);
                setPage(0);
              }}
              placeholder="筛选 URL 后缀"
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
              placeholder="筛选 URL 描述"
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
          <p className="text-muted-foreground">暂无接口配置，点击“新增接口”创建。</p>
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
                    方式
                  </th>
                  <th className="w-[160px] px-3 py-2 text-xs font-medium text-muted-foreground whitespace-nowrap">
                    所属系统
                  </th>
                  <th className="w-[28%] px-3 py-2 text-xs font-medium text-muted-foreground whitespace-nowrap">
                    URL 后缀
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
                      没有匹配的接口配置
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
                          <span className="truncate text-[11px] text-muted-foreground max-w-[260px]">
                            {source.sourceName}
                          </span>
                        </div>
                      </td>
                      <td className="px-2 py-2.5">
                        <Badge variant="outline" className="text-[10px] px-1.5">
                          {source.method}
                        </Badge>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-xs">
                          {systemNameByCode(systems, source.sysCode)}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="truncate block font-mono text-[11px] text-muted-foreground" title={source.path}>
                          {source.path}
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
                        <HttpRowActions
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
            <TablePager
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
        title="删除接口配置"
        description={`确定删除接口配置 "${deleteTarget}" 吗？此操作不可撤销。`}
      />
    </div>
  );
}

/* ── 行操作（下拉菜单） ── */

function HttpRowActions({
  source: _source,
  onView,
  onEdit,
  onCopy,
  onDelete,
}: {
  source: HttpSourceResponse;
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
            复制为新接口
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

function TablePager({
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

/* ── 富编辑器组件 ── */

function HttpSourceEditor({
  config,
  mode,
  isNew,
  onChange,
  onSave,
  onCancel,
}: {
  config: HttpSourceConfig;
  mode: "edit" | "view";
  isNew: boolean;
  onChange: (config: HttpSourceConfig) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const readOnly = mode === "view";
  /* 根据 HttpSourceConfig 构造一个临时 HTTP 步骤 */
  const httpStep = configToHttpStep(config);
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [testEnvCode, setTestEnvCode] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<HttpSourceTestResult | null>(null);
  const [testDialogOpen, setTestDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    void listEnvironments()
      .then((items) => {
        if (!alive) return;
        setEnvironments(items);
        setTestEnvCode((current) =>
          current !== "" ? current : (items[0]?.envCode ?? ""),
        );
      })
      .catch(() => {
        if (alive) setEnvironments([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  /* ── 请求面板变更处理函数 ── */
  const handleRequestChange = useCallback(
    (updatedStep: HttpStepDefinition) => {
      onChange({
        ...config,
        method: updatedStep.method,
        sysCode: updatedStep.sysCode ?? config.sysCode,
        path: updatedStep.path ?? config.path,
        timeoutConfig: updatedStep.timeoutConfig,
        requestMapping: updatedStep.requestMapping,
      });
    },
    [config, onChange],
  );

  /* ── 响应面板变更处理函数 ── */
  const handleResponseChange = useCallback(
    (updates: Partial<HttpStepDefinition>) => {
      const next = { ...config };
      if (updates.responseSchema !== undefined)
        next.responseSchema = updates.responseSchema;
      if (updates.responseHeadersSchema !== undefined)
        next.responseHeadersSchema = updates.responseHeadersSchema;
      if (updates.responseCookiesSchema !== undefined)
        next.responseCookiesSchema = updates.responseCookiesSchema;
      if (updates.responseHandling !== undefined)
        next.responseHandling = updates.responseHandling;
      if (updates.errorMapping !== undefined)
        next.errorMapping = updates.errorMapping;
      if (updates.businessErrorMapping !== undefined)
        next.businessErrorMapping = updates.businessErrorMapping;
      if (updates.retryPolicy !== undefined)
        next.retryPolicy = updates.retryPolicy;
      if (updates.outputMapping !== undefined)
        next.outputMapping = updates.outputMapping;
      if (updates.outputMeta !== undefined)
        next.outputMeta = updates.outputMeta;
      // _rawResponseSample 存储在 requestMapping 中
      if (updates.requestMapping !== undefined) {
        next.requestMapping = {
          ...config.requestMapping,
          _rawResponseSample: updates.requestMapping._rawResponseSample,
        };
      }
      onChange(next);
    },
    [config, onChange],
  );

  const handleImportResponseConfig = useCallback(
    (result: HttpSourceTestResult) => {
      const updates = buildResponseImportUpdates(result);
      if (!updates) {
        toast.error("仅 HTTP 200 响应可导入响应配置");
        return;
      }

      onChange({
        ...config,
        responseSchema: updates.responseSchema ?? [],
        responseHeadersSchema: updates.responseHeadersSchema ?? [],
        responseCookiesSchema: updates.responseCookiesSchema ?? [],
        requestMapping: {
          ...config.requestMapping,
          ...(updates.requestMapping ?? {}),
        },
      });
      setTestDialogOpen(false);
      toast.success("响应详情已导入响应配置");
    },
    [config, onChange],
  );

  const handleTest = async () => {
    if (!testEnvCode) {
      toast.error("请先选择测试环境");
      return;
    }
    setTesting(true);
    try {
      const result = await testHttpSource(testEnvCode, config);
      setTestResult(result);
      setTestDialogOpen(true);
      if (result.success) {
        toast.success("测试请求已完成");
      } else {
        toast.error(result.error?.message ?? "测试请求异常");
      }
    } catch (error) {
      toast.error(formatHttpSourceTestError(error, testEnvCode, config.sysCode));
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* 头部 */}
      <div className="flex items-center gap-3 border-b px-4 py-2 shrink-0">
        <Button variant="ghost" size="icon-sm" onClick={onCancel}>
          <ArrowLeftIcon className="size-4" />
        </Button>
        <h2 className="text-sm font-semibold">
          {readOnly
            ? `查看: ${config.sourceCode}`
            : isNew
              ? "新增 HTTP 接口"
              : `编辑: ${config.sourceCode}`}
        </h2>
        <div className="ml-auto flex items-center gap-2">
          {readOnly ? (
            <>
              <Badge variant="outline">只读</Badge>
              <Button variant="outline" size="sm" onClick={() => setExportDialogOpen(true)}>
                <DownloadIcon className="mr-1 size-3" /> 导出 curl
              </Button>
              <Button variant="outline" size="sm" onClick={onCancel}>
                返回
              </Button>
            </>
          ) : (
            <>
              <Select value={testEnvCode} onValueChange={setTestEnvCode}>
                <SelectTrigger className="h-8 w-[140px] text-xs">
                  <SelectValue placeholder="测试环境" />
                </SelectTrigger>
                <SelectContent>
                  {environments.length === 0 ? (
                    <SelectItem value="__none__" disabled className="text-xs">
                      暂无环境
                    </SelectItem>
                  ) : (
                    environments.map((env) => (
                      <SelectItem key={env.envCode} value={env.envCode} className="text-xs">
                        {env.envName} ({env.envCode})
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTest}
                disabled={testing || !config.sysCode || !config.path}
              >
                {testing ? (
                  <Loader2Icon className="mr-1 size-3 animate-spin" />
                ) : (
                  <PlayCircleIcon className="mr-1 size-3" />
                )}
                测试接口
              </Button>
              <Button variant="outline" size="sm" onClick={() => setExportDialogOpen(true)}>
                <DownloadIcon className="mr-1 size-3" /> 导出 curl
              </Button>
              <Button variant="outline" size="sm" onClick={onCancel}>
                取消
              </Button>
              <Button size="sm" onClick={onSave}>
                <SaveIcon className="mr-1 size-3" />
                保存
              </Button>
            </>
          )}
        </div>
      </div>
      {!readOnly && (
        <HttpSourceTestDialog
          open={testDialogOpen}
          result={testResult}
          onOpenChange={setTestDialogOpen}
          onImportResponseConfig={handleImportResponseConfig}
        />
      )}

      <ExportCurlDialog
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
        config={config}
        environments={environments}
      />

      {/* 内容 */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-4 space-y-4">
          {/* ── 基本信息 ── */}
          <section className="rounded-lg border bg-card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-foreground">基本信息</h3>
            <div className="grid grid-cols-[minmax(0,1fr)_180px] gap-4">
              <div className="space-y-1">
                <Label className="text-xs">接口编码</Label>
                <Input
                  value={config.sourceCode}
                  onChange={(e) =>
                    onChange({ ...config, sourceCode: e.target.value })
                  }
                  disabled={!isNew || readOnly}
                  readOnly={readOnly}
                  placeholder="如: createUser"
                  className="h-8 text-xs font-mono"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">状态</Label>
                <Select
                  value={config.status}
                  disabled={readOnly}
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
            </div>
            <div className="space-y-1">
              <Label className="text-xs">描述</Label>
              <Textarea
                value={config.sourceName}
                onChange={(e) =>
                  onChange({ ...config, sourceName: e.target.value })
                }
                disabled={readOnly}
                readOnly={readOnly}
                placeholder="填写接口的用途、适用场景、关键入参或调用注意事项，例如：用于创建新用户，调用前需先完成登录并传入业务系统分配的用户标识。"
                className="min-h-20 resize-y text-xs"
              />
            </div>
          </section>

          {/* ── 标签页 ── */}
          <Tabs defaultValue="request" className="space-y-4">
            <TabsList variant="line" className="w-full border-b border-border/40">
              <TabsTrigger value="request" className="text-xs">
                请求配置
              </TabsTrigger>
              <TabsTrigger value="response" className="text-xs">
                响应配置
              </TabsTrigger>
            </TabsList>

            {/* ── 请求标签页 ── */}
            <TabsContent value="request">
              <div className="rounded-lg border bg-card p-4">
                <HttpStepForm
                  step={httpStep}
                  onChange={readOnly ? () => undefined : handleRequestChange}
                  showResponse={false}
                  requestCollapsible={false}
                  disabled={readOnly}
                />
              </div>
            </TabsContent>

            {/* ── 响应标签页 ── */}
            <TabsContent value="response">
              <div className="rounded-lg border bg-card p-4">
                <HttpResponseMappingEditor
                  step={httpStep}
                  onChange={readOnly ? () => undefined : handleResponseChange}
                  disabled={readOnly}
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}

function formatHttpSourceTestError(
  error: unknown,
  envCode: string,
  sysCode: string,
): string {
  const message = error instanceof Error ? error.message : "";
  if (message.includes("enabled service endpoint not found")) {
    return (
      `当前选择的环境「${envCode}」还没有为系统「${sysCode}」配置启用的服务端点。` +
      "请先到「基础配置 > 服务端点」新增或启用对应配置后再测试接口。"
    );
  }
  return message || "测试请求失败";
}
/* ── 方法标签颜色映射 ── */

const METHOD_STYLES: Record<string, string> = {
  GET: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400",
  POST: "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-400",
  PUT: "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400",
  PATCH: "bg-orange-50 text-orange-700 dark:bg-orange-950/50 dark:text-orange-400",
  DELETE: "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-400",
};

function MethodBadge({ method }: { method: string }) {
  const style =
    METHOD_STYLES[method.toUpperCase()] ?? "bg-muted text-muted-foreground";
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-bold tracking-wide ${style}`}>
      {method}
    </span>
  );
}

function StatusPill({
  icon: Icon,
  children,
}: {
  icon: ComponentType<{ className?: string }>;
  children: ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-1 text-[12px] text-muted-foreground">
      <Icon className="size-3 text-muted-foreground/60" />
      {children}
    </span>
  );
}

function HttpSourceTestDialog({
  open,
  result,
  onOpenChange,
  onImportResponseConfig,
}: {
  open: boolean;
  result: HttpSourceTestResult | null;
  onOpenChange: (open: boolean) => void;
  onImportResponseConfig: (result: HttpSourceTestResult) => void;
}) {
  const [mainTab, setMainTab] = useState("response");
  const [responseTab, setResponseTab] = useState("body");

  if (!result) return null;

  const statusCode = result.response?.statusCode;
  const isSuccess = statusCode != null && statusCode >= 200 && statusCode < 300;
  const isRedirect = statusCode != null && statusCode >= 300 && statusCode < 400;
  const isError = statusCode == null || statusCode >= 400;

  const responseBodyText = formatPreview(result.response?.body ?? null);
  const bodySize = new Blob([responseBodyText]).size;
  const sizeLabel =
    bodySize > 1024
      ? `${(bodySize / 1024).toFixed(1)} KB`
      : `${bodySize} B`;

  const curlCommand = buildCurlCommand(result.request);
  const canImportResponseConfig = statusCode === 200;

  const headerCount = result.response ? Object.keys(result.response.headers).length : 0;
  const cookieCount = result.response?.cookies.length ?? 0;
  const outputCount = result.extractedOutputs ? Object.keys(result.extractedOutputs).length : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl max-h-[82vh] flex flex-col gap-0 p-0 overflow-hidden">
        {/* ── 头部 ── */}
        <div className="shrink-0 px-5 pt-5 pb-4 border-b">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <DialogHeader className="space-y-1.5">
                <div className="flex items-center gap-2.5">
                  <DialogTitle className="text-base font-semibold tracking-tight">
                    测试结果
                  </DialogTitle>
                  {isSuccess && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400">
                      <CheckCircleIcon className="size-3" />
                      成功
                    </span>
                  )}
                  {isError && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-600 dark:bg-red-950/50 dark:text-red-400">
                      <AlertTriangleIcon className="size-3" />
                      {statusCode ? "错误" : "异常"}
                    </span>
                  )}
                  {isRedirect && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-400">
                      重定向
                    </span>
                  )}
                </div>
                <DialogDescription className="flex items-center gap-2 text-[13px]">
                  <MethodBadge method={result.request.method} />
                  <span className="truncate font-mono text-muted-foreground">
                    {result.request.url}
                  </span>
                </DialogDescription>
              </DialogHeader>
            </div>
            {canImportResponseConfig && (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 h-8 text-xs gap-1.5"
                onClick={() => onImportResponseConfig(result)}
              >
                <DownloadIcon className="size-3.5" />
                导入响应配置
              </Button>
            )}
          </div>

          {/* 指标条 */}
          <div className="flex items-center gap-4 mt-3 pt-3 border-t border-border/40">
            <div className="inline-flex items-center gap-1.5">
              <span className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider">Status</span>
              <Badge
                variant={isError ? "destructive" : "secondary"}
                className="text-[11px] font-semibold tabular-nums min-w-[36px] justify-center"
              >
                {statusCode ?? "ERR"}
              </Badge>
            </div>
            {result.response?.elapsedMs != null && (
              <StatusPill icon={ClockIcon}>
                <span className="font-medium tabular-nums">{result.response.elapsedMs}</span>
                <span className="text-muted-foreground/60">ms</span>
              </StatusPill>
            )}
            {result.response?.body != null && (
              <StatusPill icon={FileTextIcon}>
                <span className="font-medium tabular-nums">{sizeLabel}</span>
              </StatusPill>
            )}
            {result.businessResult && (
              <span className={`text-[12px] font-medium ${
                result.businessResult.isSuccess
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
              }`}>
                {result.businessResult.isSuccess ? "业务成功" : "业务失败"}
                {!result.businessResult.isSuccess && result.businessResult.reason && (
                  <span className="ml-1 font-normal text-[11px] opacity-60">({result.businessResult.reason})</span>
                )}
              </span>
            )}
            {!result.businessResult && result.success && (
              <span className="text-[11px] text-muted-foreground/60 italic">未配置业务判定</span>
            )}
            {result.retryInfo && result.retryInfo.attempts > 1 && (
              <span className="text-[12px] text-amber-600 dark:text-amber-400 font-medium">
                重试 {result.retryInfo.attempts} 次
              </span>
            )}
          </div>
        </div>

        {/* ── 主标签页 ── */}
        <Tabs value={mainTab} onValueChange={setMainTab} className="flex-1 min-h-0 flex flex-col">
          <div className="px-5 pt-1">
            <TabsList variant="line" className="shrink-0 w-full border-b border-border/30">
              <TabsTrigger value="response" className="text-[13px] font-medium h-9">响应</TabsTrigger>
              <TabsTrigger value="request" className="text-[13px] font-medium h-9">请求</TabsTrigger>
            </TabsList>
          </div>

          {/* ── 响应标签页 ── */}
          <TabsContent value="response" className="mt-0 flex-1 min-h-0 flex flex-col">
            <Tabs value={responseTab} onValueChange={setResponseTab} className="flex-1 min-h-0 flex flex-col px-5">
              <TabsList variant="line" className="shrink-0 w-full border-b border-border/30 mt-1">
                <TabsTrigger value="body" className="text-[12px]">Body</TabsTrigger>
                <TabsTrigger value="headers" className="text-[12px]">
                  Headers
                  {headerCount > 0 && (
                    <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px] font-semibold tabular-nums">
                      {headerCount}
                    </span>
                  )}
                </TabsTrigger>
                <TabsTrigger value="cookies" className="text-[12px]">
                  Cookies
                  {cookieCount > 0 && (
                    <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px] font-semibold tabular-nums">
                      {cookieCount}
                    </span>
                  )}
                </TabsTrigger>
                {outputCount > 0 && (
                  <TabsTrigger value="outputs" className="text-[12px]">
                    输出变量
                    <span className="ml-1 rounded-full bg-blue-100 px-1.5 text-[10px] font-semibold tabular-nums text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                      {outputCount}
                    </span>
                  </TabsTrigger>
                )}
                {result.error && (
                  <TabsTrigger value="error" className="text-[12px] text-destructive font-medium">异常</TabsTrigger>
                )}
              </TabsList>

              <div className="flex-1 min-h-0 overflow-auto py-3">
                {/* 请求体 */}
                <TabsContent value="body" className="mt-0">
                  <div className="relative group">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="absolute top-2 right-2 h-7 px-2 text-[11px] gap-1 opacity-0 group-hover:opacity-100 transition-opacity bg-background/80 backdrop-blur-sm z-10"
                      onClick={() => {
                        void navigator.clipboard.writeText(responseBodyText);
                        toast.success("已复制响应报文");
                      }}
                    >
                      <CopyIcon className="size-3" />
                      复制
                    </Button>
                    <pre className="overflow-auto rounded-lg border bg-muted/20 p-4 text-[12.5px] leading-[1.7] whitespace-pre-wrap break-all font-mono selection:bg-blue-200/50 dark:selection:bg-blue-800/50">
                      {responseBodyText}
                    </pre>
                  </div>
                </TabsContent>

                {/* 响应头 */}
                <TabsContent value="headers" className="mt-0">
                  <div className="rounded-lg border overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-muted/30">
                          <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider w-[35%]">Name</th>
                          <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.response && headerCount > 0 ? (
                          Object.entries(result.response.headers).map(([key, val]) => (
                            <tr key={key} className="border-t hover:bg-muted/20 transition-colors">
                              <td className="px-4 py-2 font-mono text-[12px] font-medium text-foreground">{key}</td>
                              <td className="px-4 py-2 font-mono text-[12px] text-muted-foreground break-all">{val}</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={2} className="px-4 py-10 text-center text-[13px] text-muted-foreground">
                              无响应头
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </TabsContent>

                {/* Cookie 信息 */}
                <TabsContent value="cookies" className="mt-0">
                  <CookieTable cookies={result.response?.cookies ?? []} />
                </TabsContent>

                {/* 输出 */}
                {outputCount > 0 && (
                  <TabsContent value="outputs" className="mt-0">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-[13px] font-medium">输出变量</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-[11px] gap-1"
                          onClick={() => {
                            void navigator.clipboard.writeText(
                              JSON.stringify(result.extractedOutputs, null, 2),
                            );
                            toast.success("已复制");
                          }}
                        >
                          <CopyIcon className="size-3" /> 复制全部
                        </Button>
                      </div>
                      <div className="rounded-lg border overflow-hidden">
                        <table className="w-full">
                          <thead>
                            <tr className="bg-muted/30">
                              <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider w-[30%]">变量名</th>
                              <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">值</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(result.extractedOutputs).map(([name, value]) => (
                              <tr key={name} className="border-t hover:bg-muted/20 transition-colors">
                                <td className="px-4 py-2 font-mono text-[12px] font-medium text-blue-700 dark:text-blue-300">{name}</td>
                                <td className="px-4 py-2 font-mono text-[12px] text-muted-foreground break-all">
                                  {value === null || value === undefined ? (
                                    <span className="italic opacity-40">未提取到</span>
                                  ) : (
                                    formatPreview(value)
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </TabsContent>
                )}

                {/* 错误 */}
                {result.error && (
                  <TabsContent value="error" className="mt-0">
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3">
                        <AlertTriangleIcon className="size-4 text-destructive shrink-0" />
                        <div>
                          <div className="text-[13px] font-semibold text-destructive">{result.error.type}</div>
                          <div className="text-[12px] text-destructive/80 mt-0.5">{result.error.message}</div>
                        </div>
                      </div>
                      <PreviewBlock title="错误详情" value={result.error.detail ?? result.error} />
                    </div>
                  </TabsContent>
                )}
              </div>
            </Tabs>
          </TabsContent>

          {/* ── 请求标签页 ── */}
          <TabsContent value="request" className="mt-0 flex-1 min-h-0 overflow-auto px-5 py-3">
            <div className="space-y-5">
              {/* curl 命令 */}
              <div className="rounded-lg border overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b">
                  <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest">cURL Command</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-[11px] gap-1"
                    onClick={() => {
                      void navigator.clipboard.writeText(curlCommand);
                      toast.success("已复制 curl 命令");
                    }}
                  >
                    <CopyIcon className="size-3" />
                    复制
                  </Button>
                </div>
                <pre className="px-4 py-3 text-[12.5px] leading-[1.7] text-foreground overflow-x-auto whitespace-pre-wrap break-all font-mono">
                  {curlCommand}
                </pre>
              </div>

              {/* 请求头与查询参数 */}
              <div className="grid gap-4 md:grid-cols-2">
                <PreviewBlock title="Request Headers" value={result.request.headers} />
                {Object.keys(result.request.query).length > 0 && (
                  <PreviewBlock title="Query Parameters" value={result.request.query} />
                )}
              </div>

              {/* 请求体 */}
              {result.request.body != null && (
                <PreviewBlock title={`Request Body`} subtitle={result.request.bodyType} value={result.request.body} />
              )}
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

/* ── curl 命令生成 ── */

function buildCurlCommand(req: HttpSourceTestResult["request"]): string {
  const parts: string[] = [`curl -X ${req.method}`];

  parts.push(`'${req.url}'`);

  for (const [key, value] of Object.entries(req.headers || {})) {
    parts.push(`-H '${key}: ${value}'`);
  }

  if (req.method !== "GET" && req.body != null) {
    if (req.bodyType === "raw-json") {
      const jsonStr = typeof req.body === "string" ? req.body : JSON.stringify(req.body);
      parts.push(`-d '${jsonStr}'`);
    } else if (req.bodyType === "x-www-form-urlencoded" && typeof req.body === "object") {
      const params = Object.entries(req.body as Record<string, string>)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join("&");
      parts.push(`-d '${params}'`);
    } else if (req.bodyType === "form-data" && typeof req.body === "object") {
      for (const [k, v] of Object.entries(req.body as Record<string, string>)) {
        parts.push(`-F '${k}=${v}'`);
      }
    } else if (typeof req.body === "string") {
      parts.push(`-d '${req.body}'`);
    }
  }

  return parts.join(" \\\n  ");
}

/* ── Cookie 表格 ── */

function CookieTable({ cookies }: { cookies: ParsedCookie[] }) {
  if (cookies.length === 0) {
    return (
      <div className="rounded-lg border border-dashed py-10 text-center text-[13px] text-muted-foreground">
        响应中无 Cookie
      </div>
    );
  }

  return (
    <div className="rounded-lg border overflow-x-auto">
      <table className="w-full whitespace-nowrap">
        <thead>
          <tr className="bg-muted/30">
            <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Name</th>
            <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Value</th>
            <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Domain</th>
            <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Path</th>
            <th className="px-4 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Expires</th>
            <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">HttpOnly</th>
            <th className="px-4 py-2.5 text-center text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Secure</th>
          </tr>
        </thead>
        <tbody>
          {cookies.map((cookie, idx) => (
            <tr key={`${cookie.name}-${idx}`} className="border-t hover:bg-muted/20 transition-colors">
              <td className="px-4 py-2 font-mono text-[12px] font-medium">{cookie.name}</td>
              <td className="px-4 py-2 font-mono text-[12px] text-muted-foreground max-w-[200px] truncate">
                {cookie.value}
              </td>
              <td className="px-4 py-2 text-[12px] text-muted-foreground">
                {cookie.domain ?? "-"}
              </td>
              <td className="px-4 py-2 text-[12px] text-muted-foreground">
                {cookie.path ?? "/"}
              </td>
              <td className="px-4 py-2 text-[12px] text-muted-foreground">
                {cookie.expires ?? "-"}
              </td>
              <td className="px-4 py-2 text-center">
                {cookie.httpOnly ? (
                  <Badge variant="outline" className="text-[10px] px-1.5 font-medium">Yes</Badge>
                ) : (
                  <span className="text-muted-foreground/30 text-[12px]">-</span>
                )}
              </td>
              <td className="px-4 py-2 text-center">
                {cookie.secure ? (
                  <Badge variant="outline" className="text-[10px] px-1.5 font-medium">Yes</Badge>
                ) : (
                  <span className="text-muted-foreground/30 text-[12px]">-</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── 预览辅助函数 ── */

function PreviewBlock({ title, subtitle, value }: { title: string; subtitle?: string; value: unknown }) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="text-[12px] font-semibold text-foreground">{title}</span>
        {subtitle && (
          <span className="text-[11px] text-muted-foreground/60 font-mono">{subtitle}</span>
        )}
      </div>
      <pre className="max-h-72 overflow-auto rounded-lg border bg-muted/20 p-4 text-[12.5px] leading-[1.7] font-mono">
        {formatPreview(value)}
      </pre>
    </div>
  );
}

function formatPreview(value: unknown): string {
  if (typeof value === "string") return value || "(空)";
  if (value === null || value === undefined) return "(空)";
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  if (typeof value === "symbol") {
    return value.description ? `Symbol(${value.description})` : "Symbol()";
  }
  if (typeof value === "function") return "[Function]";
  try {
    return JSON.stringify(value, null, 2) ?? "(空)";
  } catch {
    return "(无法序列化)";
  }
}

/* ── curl 导出辅助函数 ── */

function configToCurl(config: HttpSourceConfig, baseUrl: string): string {
  const mapping = config.requestMapping;
  const query = toStringRecord(mapping.query);
  const headers: Record<string, string> = {};

  // 复制用户配置的请求头
  for (const [key, value] of Object.entries(toStringRecord(mapping.headers))) {
    headers[key] = value;
  }

  // 处理认证配置
  const auth = toRecord(mapping.authConfig);
  const authType = toStringValue(auth.type, "none");
  if (authType === "bearer") {
    const token = toStringValue(auth.token);
    if (token) headers.Authorization = `Bearer ${token}`;
  } else if (authType === "basic") {
    const username = toStringValue(auth.username);
    if (username) {
      const credentials = btoa(`${username}:${toStringValue(auth.password)}`);
      headers.Authorization = `Basic ${credentials}`;
    }
  } else if (authType === "apikey") {
    const key = toStringValue(auth.key);
    if (key && toStringValue(auth.addTo) === "query") {
      query[key] = toStringValue(auth.value);
    } else if (key) {
      headers[key] = toStringValue(auth.value);
    }
  }

  // 拼接 URL
  const normalizedBase = baseUrl.replace(/\/+$/, "");
  const normalizedPath = config.path.startsWith("/") ? config.path : `/${config.path}`;
  let url = `${normalizedBase}${normalizedPath}`;

  // 拼接查询参数
  const queryEntries = Object.entries(query).filter(([, value]) => value !== "");
  if (queryEntries.length > 0) {
    const qs = queryEntries
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
      .join("&");
    url += `?${qs}`;
  }

  // 构造 curl 命令
  const parts: string[] = [`curl -X ${config.method}`];
  parts.push(`'${url}'`);

  for (const [key, value] of Object.entries(headers)) {
    parts.push(`-H '${key}: ${value}'`);
  }

  // 请求体（仅 POST）
  if (config.method !== "GET") {
    const bodyType = toStringValue(mapping.bodyType, "none");
    if (bodyType === "raw-json") {
      const rawBody = toStringValue(mapping.rawBody);
      if (rawBody.trim()) {
        parts.push(`-H 'Content-Type: application/json'`);
        parts.push(`-d '${escapeSingleQuotedShell(rawBody)}'`);
      }
    } else if (bodyType === "raw-text") {
      const rawBody = toStringValue(mapping.rawBody);
      if (rawBody) {
        parts.push(`-H 'Content-Type: text/plain'`);
        parts.push(`-d '${escapeSingleQuotedShell(rawBody)}'`);
      }
    } else if (bodyType === "raw-xml") {
      const rawBody = toStringValue(mapping.rawBody);
      if (rawBody) {
        parts.push(`-H 'Content-Type: application/xml'`);
        parts.push(`-d '${escapeSingleQuotedShell(rawBody)}'`);
      }
    } else if (bodyType === "x-www-form-urlencoded") {
      const data = toStringRecord(mapping.urlEncodedData);
      const encoded = Object.entries(data)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join("&");
      if (encoded) {
        parts.push(`-H 'Content-Type: application/x-www-form-urlencoded'`);
        parts.push(`-d '${encoded}'`);
      }
    } else if (bodyType === "form-data") {
      const rows = Array.isArray(mapping.formData) ? mapping.formData : [];
      for (const rowValue of rows) {
        const row = toRecord(rowValue);
        const key = toStringValue(row.key);
        if (row.enabled !== false && key) {
          parts.push(`-F '${key}=${toStringValue(row.value)}'`);
        }
      }
    }
  }

  return parts.join(" \\\n  ");
}

function toRecord(value: unknown): Record<string, unknown> {
  return isPlainRecord(value) ? value : {};
}

function toStringRecord(value: unknown): Record<string, string> {
  const record = toRecord(value);
  return Object.fromEntries(
    Object.entries(record).map(([key, item]) => [key, toStringValue(item)]),
  );
}

function toStringValue(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  return fallback;
}

function escapeSingleQuotedShell(value: string): string {
  return value.replace(/'/g, "'\\''");
}

/* ── 导出 curl 对话框 ── */

function ExportCurlDialog({
  open,
  onOpenChange,
  config,
  environments,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: HttpSourceConfig;
  environments: EnvironmentResponse[];
}) {
  const [endpoints, setEndpoints] = useState<ServiceEndpointResponse[]>([]);
  const [envCode, setEnvCode] = useState("");

  // 加载服务端点（当环境变化时）
  useEffect(() => {
    if (!open || !envCode) return;
    let alive = true;
    void listServiceEndpoints({ envCode, sysCode: config.sysCode }).then((items) => {
      if (alive) setEndpoints(items);
    });
    return () => { alive = false; };
  }, [open, envCode, config.sysCode]);

  // 解析 base URL
  const baseUrl = useMemo(() => {
    const ep = endpoints.find((e) => e.sysCode === config.sysCode && e.status === "ENABLED");
    return ep?.baseUrl ?? "";
  }, [endpoints, config.sysCode]);

  const curlCommand = useMemo(() => {
    if (!baseUrl) return "";
    return configToCurl(config, baseUrl);
  }, [config, baseUrl]);

  const envLabel = environments.find((e) => e.envCode === envCode)?.envName ?? envCode;

  const handleDownload = () => {
    const lines = [
      "#!/bin/bash",
      `# ${config.sourceName}`,
      `# 环境: ${envLabel}`,
      `# 导出时间: ${new Date().toLocaleString("zh-CN")}`,
      "",
      curlCommand,
      "",
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `curl-${config.sourceCode}-${envCode}.sh`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("已导出 curl 脚本");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <DownloadIcon className="size-4" />
            导出 curl 命令
          </DialogTitle>
          <DialogDescription>
            {config.sourceName} — [{config.method}] {config.path}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* 环境选择 */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">选择环境（用于解析 Base URL）</Label>
            <Select value={envCode} onValueChange={setEnvCode}>
              <SelectTrigger className="h-9 text-xs w-[300px]">
                <SelectValue placeholder="选择环境" />
              </SelectTrigger>
              <SelectContent>
                {environments.map((env) => (
                  <SelectItem key={env.envCode} value={env.envCode} className="text-xs">
                    {env.envName} ({env.envCode})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Base URL 显示 */}
          {envCode && (
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Base URL</Label>
              <div className={`rounded-md border px-3 py-2 font-mono text-xs ${baseUrl ? "text-emerald-600" : "text-destructive"}`}>
                {baseUrl ? baseUrl : "未配置服务端点"}
              </div>
            </div>
          )}

          {/* curl 命令预览 */}
          {curlCommand && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">curl 命令</Label>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-[11px]"
                  onClick={() => {
                    void navigator.clipboard.writeText(curlCommand);
                    toast.success("已复制到剪贴板");
                  }}
                >
                  <CopyIcon className="mr-1 size-3" />
                  复制
                </Button>
              </div>
              <div className="rounded-md border bg-slate-950 dark:bg-slate-900 p-3">
                <pre className="text-[11px] leading-relaxed text-slate-200 overflow-x-auto whitespace-pre-wrap break-all font-mono max-h-[300px] overflow-y-auto">
                  {curlCommand}
                </pre>
              </div>
            </div>
          )}

          {/* 无 Base URL 警告 */}
          {envCode && !baseUrl && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              系统 {config.sysCode} 在环境 {envLabel} 未配置服务端点，无法生成 curl 命令。请先在基础配置中配置该系统的服务端点。
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleDownload} disabled={!curlCommand}>
            <DownloadIcon className="mr-1 size-4" />
            下载 .sh 脚本
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
