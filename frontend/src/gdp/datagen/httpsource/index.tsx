"use client";

import {
  ArrowLeftIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  CopyIcon,
  EyeIcon,
  Loader2Icon,
  MoreHorizontalIcon,
  PencilIcon,
  PlayCircleIcon,
  PlusIcon,
  Trash2Icon,
  SaveIcon,
  SearchIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import {
  createHttpSource,
  deleteHttpSource,
  listEnvironments,
  listHttpSources,
  listSystems,
  testHttpSource,
  updateHttpSource,
} from "../common/lib/api";
import { createDefaultHttpSource } from "../common/lib/defaults";
import type {
  ConfigStatus,
  EnvironmentResponse,
  HttpMethod,
  HttpSourceConfig,
  HttpSourceResponse,
  HttpSourceTestResult,
  StepDefinition,
  SysResponse,
} from "../common/lib/types";
import { systemNameByCode } from "../baseconfig/config-helpers";
import { HttpResponseMappingEditor } from "../common/source-forms/http-response-mapping-editor";
import { HttpStepForm } from "../common/source-forms/http-step-form";
import { ConfirmDialog } from "../common/ui/confirm-dialog";

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

/* ── adapter: HttpSourceConfig → StepDefinition ────────────────── */

function configToFakeStep(config: HttpSourceConfig): StepDefinition {
  return {
    stepId: config.sourceCode || "__httpsource__",
    stepName: config.sourceName,
    type: "HTTP",
    enabled: true,
    dependsOn: [],
    httpParamMapping: {},
    sqlParamMapping: {},
    method: config.method,
    url: config.path,
    sysCode: config.sysCode,
    requestMapping: config.requestMapping,
    bodySchema: config.bodySchema,
    responseSchema: config.responseSchema,
    responseHeadersSchema: config.responseHeadersSchema,
    responseCookiesSchema: config.responseCookiesSchema,
    responseHandling: config.responseHandling,
    errorMapping: config.errorMapping,
    outputMapping: config.outputMapping,
    outputMeta: config.outputMeta,
    retryPolicy: config.retryPolicy,
    paramMapping: {},
    assertions: [],
    assignments: {},
  };
}

/* ── main component ─────────────────────────────────────────────── */

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
    reload();
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

  /* ── editor view ── */
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

  /* ── list view ── */
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <h2 className="text-lg font-semibold">HTTP 接口配置</h2>
        <Button size="sm" onClick={handleNew}>
          <PlusIcon className="mr-1 size-4" /> 新增接口
        </Button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-md border bg-muted/20 p-3 md:grid-cols-2 xl:grid-cols-[150px_220px_minmax(180px,1fr)_minmax(180px,1fr)_auto]">
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
          <p className="text-muted-foreground">暂无接口配置，点击"新增接口"创建。</p>
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

/* ── Row Actions (dropdown menu) ──────────────────────────────── */

function HttpRowActions({
  source,
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

/* ── rich editor component ──────────────────────────────────────── */

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
  /* Build a fake StepDefinition from the HttpSourceConfig */
  const fakeStep = configToFakeStep(config);
  const [environments, setEnvironments] = useState<EnvironmentResponse[]>([]);
  const [testEnvCode, setTestEnvCode] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<HttpSourceTestResult | null>(null);
  const [testDialogOpen, setTestDialogOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    void listEnvironments()
      .then((items) => {
        if (!alive) return;
        setEnvironments(items);
        setTestEnvCode((current) => current || items[0]?.envCode || "");
      })
      .catch(() => {
        if (alive) setEnvironments([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  /* ── request panel change handler ── */
  const handleRequestChange = useCallback(
    (updatedStep: StepDefinition) => {
      onChange({
        ...config,
        method: updatedStep.method ?? config.method,
        sysCode: updatedStep.sysCode ?? config.sysCode,
        path: updatedStep.url ?? config.path,
        requestMapping: updatedStep.requestMapping,
      });
    },
    [config, onChange],
  );

  /* ── response panel change handler ── */
  const handleResponseChange = useCallback(
    (updates: Partial<StepDefinition>) => {
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
      if (updates.retryPolicy !== undefined)
        next.retryPolicy = updates.retryPolicy;
      if (updates.outputMapping !== undefined)
        next.outputMapping = updates.outputMapping;
      if (updates.outputMeta !== undefined)
        next.outputMeta = updates.outputMeta;
      // _rawResponseSample is stored in requestMapping
      if (updates.requestMapping !== undefined) {
        next.requestMapping = {
          ...config.requestMapping,
          _rawResponseSample: (updates.requestMapping as any)._rawResponseSample,
        };
      }
      onChange(next);
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
        toast.error(result.error?.message || "测试请求异常");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试请求失败");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
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
        />
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-4 space-y-4">
          {/* ── Basic Info ── */}
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

          {/* ── Tabs ── */}
          <Tabs defaultValue="request" className="space-y-4">
            <TabsList variant="line" className="w-full border-b border-border/40">
              <TabsTrigger value="request" className="text-xs">
                请求配置
              </TabsTrigger>
              <TabsTrigger value="response" className="text-xs">
                响应配置
              </TabsTrigger>
            </TabsList>

            {/* ── Request Tab ── */}
            <TabsContent value="request">
              <div className="rounded-lg border bg-card p-4">
                <HttpStepForm
                  step={fakeStep}
                  onChange={readOnly ? () => undefined : handleRequestChange}
                  showResponse={false}
                  requestCollapsible={false}
                  disabled={readOnly}
                />
              </div>
            </TabsContent>

            {/* ── Response Tab ── */}
            <TabsContent value="response">
              <div className="rounded-lg border bg-card p-4">
                <HttpResponseMappingEditor
                  step={fakeStep}
                  onChange={readOnly ? () => undefined : handleResponseChange}
                  showExtraction={false}
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
function HttpSourceTestDialog({
  open,
  result,
  onOpenChange,
}: {
  open: boolean;
  result: HttpSourceTestResult | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            {result?.success ? (
              <CheckCircleIcon className="size-4 text-emerald-600" />
            ) : (
              <AlertTriangleIcon className="size-4 text-destructive" />
            )}
            接口测试结果
          </DialogTitle>
          <DialogDescription>
            展示后端实际发出的请求和收到的响应，异常时展示完整错误详情。
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[72vh] pr-3">
          {result ? (
            <div className="space-y-4">
              <section className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{result.request.method}</Badge>
                  <span className="break-all font-mono text-xs">{result.request.url}</span>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <PreviewBlock title="请求 Headers" value={result.request.headers} />
                  <PreviewBlock title="请求 Params" value={result.request.query} />
                </div>
                <PreviewBlock
                  title={`请求报文 (${result.request.bodyType})`}
                  value={result.request.body ?? null}
                />
              </section>

              <section className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">响应报文</span>
                  {result.response?.statusCode != null && (
                    <Badge variant={result.success ? "default" : "secondary"}>
                      HTTP {result.response.statusCode}
                    </Badge>
                  )}
                  {result.response?.elapsedMs != null && (
                    <span className="text-xs text-muted-foreground">
                      {result.response.elapsedMs} ms
                    </span>
                  )}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <PreviewBlock title="响应 Headers" value={result.response?.headers ?? {}} />
                  <PreviewBlock title="响应 Body" value={result.response?.body ?? null} />
                </div>
              </section>

              {result.error && (
                <section className="space-y-2">
                  <div className="flex items-center gap-2 text-destructive">
                    <AlertTriangleIcon className="size-4" />
                    <span className="text-sm font-semibold">
                      {result.error.type}: {result.error.message}
                    </span>
                  </div>
                  <PreviewBlock title="异常详情" value={result.error.detail || result.error} />
                </section>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">暂无测试结果</p>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

function PreviewBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold text-muted-foreground">{title}</div>
      <pre className="max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 text-[11px] leading-relaxed">
        {formatPreview(value)}
      </pre>
    </div>
  );
}

function formatPreview(value: unknown): string {
  if (typeof value === "string") return value || "(空)";
  if (value === null || value === undefined) return "(空)";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
