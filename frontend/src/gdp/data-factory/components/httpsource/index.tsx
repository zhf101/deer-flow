"use client";

import {
  ArrowLeftIcon,
  PlusIcon,
  PencilIcon,
  Trash2Icon,
  PowerIcon,
  SaveIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import {
  createHttpSource,
  deleteHttpSource,
  disableHttpSource,
  listHttpSources,
  updateHttpSource,
} from "../../lib/api";
import { createDefaultHttpSource } from "../../lib/defaults";
import type {
  ConfigStatus,
  HttpSourceConfig,
  HttpSourceResponse,
  StepDefinition,
} from "../../lib/types";

import { HttpStepForm } from "../http/http-step-form";
import { HttpResponseMappingEditor } from "../http/http-response-mapping-editor";

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
    serviceCode: config.serviceCode,
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
  const [isNew, setIsNew] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setSources(await listHttpSources());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleNew = () => {
    setEditing(createDefaultHttpSource());
    setIsNew(true);
  };

  const handleEdit = (source: HttpSourceResponse) => {
    setEditing({
      ...source,
      responseSchema: source.responseSchema ?? null,
      responseHeadersSchema: source.responseHeadersSchema ?? null,
      responseCookiesSchema: source.responseCookiesSchema ?? null,
    });
    setIsNew(false);
  };

  const handleSave = async () => {
    if (!editing) return;
    try {
      if (isNew) {
        await createHttpSource(editing);
        toast.success("接口配置已创建");
      } else {
        await updateHttpSource(editing.sourceCode, editing);
        toast.success("接口配置已保存");
      }
      setEditing(null);
      await reload();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    }
  };

  const handleDelete = async (code: string) => {
    if (confirm(`确定删除接口配置 "${code}" 吗？`)) {
      await deleteHttpSource(code);
      toast.success("已删除");
      await reload();
    }
  };

  const handleDisable = async (code: string) => {
    await disableHttpSource(code);
    toast.success("已停用");
    await reload();
  };

  /* ── editor view ── */
  if (editing) {
    return (
      <HttpSourceEditor
        config={editing}
        isNew={isNew}
        onChange={setEditing}
        onSave={handleSave}
        onCancel={() => setEditing(null)}
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
        {loading ? (
          <p className="text-muted-foreground">加载中...</p>
        ) : sources.length === 0 ? (
          <p className="text-muted-foreground">暂无接口配置，点击"新增接口"创建。</p>
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
                    <Badge variant="outline">{s.method}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {s.sourceName} — {s.serviceCode}
                    {s.path}
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
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(s.sourceCode)}
                  >
                    <Trash2Icon className="size-4" />
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

/* ── rich editor component ──────────────────────────────────────── */

function HttpSourceEditor({
  config,
  isNew,
  onChange,
  onSave,
  onCancel,
}: {
  config: HttpSourceConfig;
  isNew: boolean;
  onChange: (config: HttpSourceConfig) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  /* Build a fake StepDefinition from the HttpSourceConfig */
  const fakeStep = configToFakeStep(config);

  /* ── request panel change handler ── */
  const handleRequestChange = useCallback(
    (updatedStep: StepDefinition) => {
      onChange({
        ...config,
        method: updatedStep.method ?? config.method,
        serviceCode: updatedStep.serviceCode ?? config.serviceCode,
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

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b px-4 py-2 shrink-0">
        <Button variant="ghost" size="icon-sm" onClick={onCancel}>
          <ArrowLeftIcon className="size-4" />
        </Button>
        <h2 className="text-sm font-semibold">
          {isNew ? "新增 HTTP 接口" : `编辑: ${config.sourceCode}`}
        </h2>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            取消
          </Button>
          <Button size="sm" onClick={onSave}>
            <SaveIcon className="mr-1 size-3" />
            保存
          </Button>
        </div>
      </div>

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
                  disabled={!isNew}
                  placeholder="如: createUser"
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
            </div>
            <div className="space-y-1">
              <Label className="text-xs">描述</Label>
              <Textarea
                value={config.sourceName}
                onChange={(e) =>
                  onChange({ ...config, sourceName: e.target.value })
                }
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
                  onChange={handleRequestChange}
                  showResponse={false}
                  requestCollapsible={false}
                />
              </div>
            </TabsContent>

            {/* ── Response Tab ── */}
            <TabsContent value="response">
              <div className="rounded-lg border bg-card p-4">
                <HttpResponseMappingEditor
                  step={fakeStep}
                  onChange={handleResponseChange}
                  showExtraction={false}
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
