"use client";

import {
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  CodeIcon,
  FileCodeIcon,
  FileJsonIcon,
  FileTextIcon,
  GlobeIcon,
  KeyRoundIcon,
  PlusIcon,
  ShieldIcon,
  TableIcon,
  Trash2Icon,
  VariableIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { VariableSelector } from "../editors/variable-selector";
import { listServiceEndpoints, listSystems } from "../lib/api";
import { createDefaultHttpTimeoutConfig, HTTP_METHODS } from "../lib/defaults";
import type {
  HttpMethod,
  HttpTimeoutConfig,
  SceneDefinition,
  ServiceEndpointResponse,
  StepDefinition,
  SysResponse,
} from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";
import { ConfirmDialog } from "../ui/confirm-dialog";

import { BodyTreeEditor } from "./body-tree-editor";
import { FieldMapper } from "./field-mapper";
import { HeaderFieldMapper } from "./header-field-mapper";
import { HttpOutputExtractionSection } from "./http-output-extraction-editor";
import { HttpResponseMappingEditor } from "./http-response-mapping-editor";

/* ── 类型 ── */

interface HttpStepFormProps {
  scene?: SceneDefinition;
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
  /** 是否显示响应配置区域。默认 true。 */
  showResponse?: boolean;
  /** 是否在响应区域内显示抽取管理器。默认 true。 */
  showExtraction?: boolean;
  /** 请求配置区域是否可折叠。默认 true。 */
  requestCollapsible?: boolean;
  /** 禁用所有数据输入和按钮，但保留导航交互（标签页、折叠面板）。 */
  disabled?: boolean;
}

type AuthType = "none" | "bearer" | "basic" | "apikey";

interface AuthConfig {
  type: AuthType;
  token?: string;
  username?: string;
  password?: string;
  key?: string;
  value?: string;
  addTo?: "header" | "query";
}

type BodyType = "none" | "form-data" | "x-www-form-urlencoded" | "raw-json" | "raw-text" | "raw-xml";
type TimeoutConfigKey = keyof HttpTimeoutConfig;

const TIMEOUT_FIELDS: Array<{ key: TimeoutConfigKey; label: string }> = [
  { key: "connectTimeoutSeconds", label: "连接" },
  { key: "readTimeoutSeconds", label: "读取" },
  { key: "writeTimeoutSeconds", label: "写入" },
  { key: "poolTimeoutSeconds", label: "连接池" },
];

interface HttpRequestMapping extends Record<string, unknown> {
  authConfig?: AuthConfig;
  bodyType?: BodyType;
  rawBody?: string;
  headers?: Record<string, unknown>;
  query?: Record<string, unknown>;
  _queryDesc?: Record<string, string>;
  _headersDesc?: Record<string, string>;
  urlEncodedData?: Record<string, unknown>;
  _urlEncodedDesc?: Record<string, string>;
  formData?: FormDataRow[];
}

/* ── 主组件 ── */

export function HttpStepForm({
  scene,
  step,
  onChange,
  showResponse = true,
  showExtraction = true,
  requestCollapsible = true,
  disabled = false,
}: HttpStepFormProps) {
  const [endpoints, setEndpoints] = useState<ServiceEndpointResponse[]>([]);
  const [systems, setSystems] = useState<SysResponse[]>([]);
  const [activeTab, setActiveTab] = useState("body");
  const [requestOpen, setRequestOpen] = useState(true);
  const [responseOpen, setResponseOpen] = useState(true);

  /* 加载系统与环境端点 */
  const loadEndpoints = useCallback(async () => {
    try {
      const [endpointItems, systemItems] = await Promise.all([
        listServiceEndpoints(),
        listSystems(),
      ]);
      setEndpoints(endpointItems);
      setSystems(systemItems);
    } catch {
      /* 忽略 */
    }
  }, []);
  useEffect(() => {
    void loadEndpoints();
  }, [loadEndpoints]);

  const systemOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const sys of systems) {
      seen.set(sys.sysCode, sys.sysName);
    }
    for (const ep of endpoints) {
      if (!seen.has(ep.sysCode)) seen.set(ep.sysCode, ep.sysCode);
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [endpoints, systems]);

  const selectedEndpoints = endpoints.filter((ep) => ep.sysCode === step.sysCode);
  const method = step.method ?? "POST";
  const requestMapping = (step.requestMapping ?? {}) as HttpRequestMapping;
  const timeoutConfig = step.timeoutConfig ?? createDefaultHttpTimeoutConfig();

  const updateTimeoutConfig = (key: TimeoutConfigKey, rawValue: string) => {
    const nextValue = Number(rawValue);
    onChange({
      ...step,
      timeoutConfig: {
        ...timeoutConfig,
        [key]: Number.isFinite(nextValue) ? nextValue : 10,
      },
    });
  };

  /* ── 认证配置辅助函数 ── */
  const authConfig: AuthConfig = requestMapping.authConfig ?? { type: "none" };

  const updateAuthConfig = (next: AuthConfig) => {
    const headers = { ...(requestMapping.headers ?? {}) } as Record<string, string>;
    const query = { ...(requestMapping.query ?? {}) } as Record<string, string>;

    // 清理之前由认证配置管理的条目
    delete headers.Authorization;
    const prevAuth: AuthConfig = requestMapping.authConfig ?? { type: "none" };
    if (prevAuth.type === "apikey" && prevAuth.key) {
      if (prevAuth.addTo === "query") {
        delete query[prevAuth.key];
      } else {
        delete headers[prevAuth.key];
      }
    }

    if (next.type === "bearer" && next.token) {
      headers.Authorization = `Bearer ${next.token}`;
    } else if (next.type === "basic" && next.username) {
      headers.Authorization = `Basic {{${next.username}:${next.password ?? ""}}}`;
    } else if (next.type === "apikey" && next.key) {
      if (next.addTo === "query") {
        query[next.key] = next.value ?? "";
      } else {
        headers[next.key] = next.value ?? "";
      }
    }

    onChange({
      ...step,
      requestMapping: { ...requestMapping, headers, query, authConfig: next },
    });
  };

  /* ── 请求体类型辅助函数 ── */
  const bodyType: BodyType = requestMapping.bodyType ?? "raw-json";

  const updateBodyType = (next: BodyType) => {
    const updated: HttpRequestMapping = { ...requestMapping, bodyType: next };
    // 切换请求体类型时自动设置 Content-Type 请求头
    const headers = { ...(requestMapping.headers ?? {}) } as Record<string, string>;
    if (next === "raw-json") {
      headers["Content-Type"] = "application/json";
    } else if (next === "raw-xml") {
      headers["Content-Type"] = "application/xml";
    } else if (next === "raw-text") {
      headers["Content-Type"] = "text/plain";
    } else if (next === "x-www-form-urlencoded") {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else if (next === "form-data") {
      delete headers["Content-Type"]; // 浏览器会设置 multipart 边界
    } else if (next === "none") {
      delete headers["Content-Type"];
    }
    updated.headers = headers;
    onChange({ ...step, requestMapping: updated });
  };

  const rawBodyText = requestMapping.rawBody ?? "";

  const updateRawBody = (text: string) => {
    onChange({
      ...step,
      requestMapping: { ...requestMapping, rawBody: text },
    });
  };

  /* ── 请求映射区域更新器 ── */
  const updateSection = (section: string, value: unknown) => {
    onChange({ ...step, requestMapping: { ...requestMapping, [section]: value } });
  };

  /* ── 标签徽标数量 ── */
  const paramCount = Object.keys(requestMapping.query ?? {}).length;
  const headerCount = Object.keys(requestMapping.headers ?? {}).length;
  const hasAuth = authConfig.type !== "none";
  const hasBody = method === "POST" && bodyType !== "none";

  return (
    <div className="space-y-2">
      {/* ── 请求配置区域 ── */}
      <Collapsible
        open={requestCollapsible ? requestOpen : true}
        onOpenChange={requestCollapsible ? setRequestOpen : undefined}
      >
        {requestCollapsible ? (
          <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 border-b text-sm font-bold text-blue-600 hover:text-blue-700 transition-colors">
            {requestOpen ? (
              <ChevronDownIcon className="size-4" />
            ) : (
              <ChevronRightIcon className="size-4" />
            )}
            请求配置
            <span className="ml-auto text-[10px] font-normal text-muted-foreground">
              {method} {step.url ? (step.url.length > 50 ? step.url.slice(0, 50) + "..." : step.url) : "未配置 URL"}
            </span>
          </CollapsibleTrigger>
        ) : null}

        <CollapsibleContent
          {...(!requestCollapsible ? { forceMount: true as const } : {})}
          className="space-y-2 pt-2"
        >
          {/* ── 地址栏 ── */}
          <div className={cn("flex items-center gap-1.5 rounded-lg border bg-muted/20 p-1.5", disabled && "pointer-events-none opacity-50")}>
            <Select
              value={method}
              onValueChange={(value) => onChange({ ...step, method: value as HttpMethod })}
            >
              <SelectTrigger className="h-8 w-[90px] text-xs font-bold shrink-0">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HTTP_METHODS.map((m) => (
                  <SelectItem key={m} value={m} className="text-xs font-bold">
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={step.sysCode ?? "__none__"}
              onValueChange={(value) =>
                onChange({ ...step, sysCode: value === "__none__" ? "" : value })
              }
            >
              <SelectTrigger className="h-8 w-[140px] text-xs shrink-0">
                <SelectValue placeholder="选择系统" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__" className="text-xs">未选择系统</SelectItem>
                {systemOptions.map((svc) => (
                  <SelectItem key={svc.code} value={svc.code} className="text-xs">
                    {svc.name} ({svc.code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Input
              value={step.url ?? ""}
              onChange={(e) => onChange({ ...step, url: e.target.value })}
              placeholder={
                selectedEndpoints[0]
                  ? `/v1/resource (示例端点: ${selectedEndpoints[0].baseUrl})`
                  : "https://api.example.com/v1/resource"
              }
              className="h-8 flex-1 text-xs font-mono"
            />
          </div>
          {selectedEndpoints.length > 0 && (
            <p className="text-[10px] text-muted-foreground pl-1">
              已配置环境端点:{" "}
              {selectedEndpoints.map((endpoint) => (
                <span key={endpoint.id} className="mr-2 font-mono text-blue-600">
                  {endpoint.envCode}: {endpoint.baseUrl}
                </span>
              ))}
            </p>
          )}

          <div className={cn("grid gap-2 rounded-lg border bg-background p-2 md:grid-cols-4", disabled && "pointer-events-none opacity-50")}>
            {TIMEOUT_FIELDS.map((field) => (
              <label key={field.key} className="space-y-1">
                <span className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground">
                  <ClockIcon className="size-3" />
                  {field.label}超时（秒）
                </span>
                <Input
                  type="number"
                  min={1}
                  max={60}
                  step={1}
                  value={timeoutConfig[field.key]}
                  disabled={disabled}
                  onChange={(event) => updateTimeoutConfig(field.key, event.target.value)}
                  className="h-8 text-xs"
                />
              </label>
            ))}
          </div>

          {/* ── 请求标签页 ── */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList variant="line" className="w-full border-b border-border/40">
              <TabsTrigger value="params" className="text-xs gap-1.5">
                <GlobeIcon className="size-3.5" />
                Params
                {paramCount > 0 && (
                  <span className="ml-1 rounded-full bg-muted px-1.5 text-[9px] font-bold">{paramCount}</span>
                )}
              </TabsTrigger>
              <TabsTrigger value="auth" className="text-xs gap-1.5">
                <KeyRoundIcon className="size-3.5" />
                Auth
                {hasAuth && <span className="ml-1 size-1.5 rounded-full bg-green-500" />}
              </TabsTrigger>
              <TabsTrigger value="headers" className="text-xs gap-1.5">
                <ShieldIcon className="size-3.5" />
                Headers
                {headerCount > 0 && (
                  <span className="ml-1 rounded-full bg-muted px-1.5 text-[9px] font-bold">{headerCount}</span>
                )}
              </TabsTrigger>
              <TabsTrigger value="body" className="text-xs gap-1.5">
                <CodeIcon className="size-3.5" />
                Body
                {hasBody && <span className="ml-1 size-1.5 rounded-full bg-blue-500" />}
              </TabsTrigger>
            </TabsList>

            {/* ── 参数 ── */}
            <TabsContent value="params" className={cn("mt-2", disabled && "pointer-events-none opacity-50")}>
              <FieldMapper
                label="Query Params"
                description="URL 问号后面的参数, 如 ?id=1&name=test"
                value={requestMapping.query ?? {}}
                onChange={(v) => updateSection("query", v)}
                scene={scene}
                currentStepId={step.stepId}
                placeholder="Param Key"
                descriptions={requestMapping._queryDesc ?? {}}
                onDescriptionsChange={(d) =>
                  onChange({ ...step, requestMapping: { ...requestMapping, _queryDesc: d } })
                }
              />
            </TabsContent>

            {/* ── 认证 ── */}
            <TabsContent value="auth" className={cn("mt-2", disabled && "pointer-events-none opacity-50")}>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <span className="text-xs font-medium text-muted-foreground">认证类型</span>
                  <Select
                    value={authConfig.type}
                    onValueChange={(v: AuthType) => updateAuthConfig({ ...authConfig, type: v })}
                  >
                    <SelectTrigger className="h-8 w-[200px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none" className="text-xs">No Auth</SelectItem>
                      <SelectItem value="bearer" className="text-xs">Bearer Token</SelectItem>
                      <SelectItem value="basic" className="text-xs">Basic Auth</SelectItem>
                      <SelectItem value="apikey" className="text-xs">API Key</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {authConfig.type === "bearer" && (
                  <div className="space-y-1.5 rounded-md border bg-muted/10 p-2.5">
                    <span className="text-xs font-medium">Token</span>
                    <Input
                      value={authConfig.token ?? ""}
                      onChange={(e) => updateAuthConfig({ ...authConfig, token: e.target.value })}
                      placeholder="Bearer Token 或变量引用"
                      className="h-8 text-xs font-mono"
                    />
                  </div>
                )}

                {authConfig.type === "basic" && (
                  <div className="space-y-2 rounded-md border bg-muted/10 p-2.5">
                    <div className="space-y-1">
                      <span className="text-xs font-medium">Username</span>
                      <Input
                        value={authConfig.username ?? ""}
                        onChange={(e) => updateAuthConfig({ ...authConfig, username: e.target.value })}
                        placeholder="用户名"
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <span className="text-xs font-medium">Password</span>
                      <Input
                        value={authConfig.password ?? ""}
                        onChange={(e) => updateAuthConfig({ ...authConfig, password: e.target.value })}
                        placeholder="密码"
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                  </div>
                )}

                {authConfig.type === "apikey" && (
                  <div className="space-y-2 rounded-md border bg-muted/10 p-2.5">
                    <div className="grid grid-cols-[1fr_1fr_120px] gap-3">
                      <div className="space-y-1">
                        <span className="text-xs font-medium">Key</span>
                        <Input
                          value={authConfig.key ?? ""}
                          onChange={(e) => updateAuthConfig({ ...authConfig, key: e.target.value })}
                          placeholder="如 X-API-Key"
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                      <div className="space-y-1">
                        <span className="text-xs font-medium">Value</span>
                        <Input
                          value={authConfig.value ?? ""}
                          onChange={(e) => updateAuthConfig({ ...authConfig, value: e.target.value })}
                          placeholder="API Key 或 ${...}"
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                      <div className="space-y-1">
                        <span className="text-xs font-medium">Add to</span>
                        <Select
                          value={authConfig.addTo ?? "header"}
                          onValueChange={(v: "header" | "query") =>
                            updateAuthConfig({ ...authConfig, addTo: v })
                          }
                        >
                          <SelectTrigger className="h-8 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="header" className="text-xs">Header</SelectItem>
                            <SelectItem value="query" className="text-xs">Query Params</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      {authConfig.addTo === "query"
                        ? `将以 ${authConfig.key ?? "<key>"}=<value> 追加到 URL 查询参数`
                        : `将以 ${authConfig.key ?? "<key>"}: <value> 追加到请求头`}
                    </p>
                  </div>
                )}

                {authConfig.type === "none" && (
                  <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground">
                    该请求不使用认证
                  </div>
                )}
              </div>
            </TabsContent>

            {/* ── 请求头 ── */}
            <TabsContent value="headers" className={cn("mt-2", disabled && "pointer-events-none opacity-50")}>
              <HeaderFieldMapper
                label="请求头"
                description="配置 HTTP Header, 输入时自动联想常见 Header"
                value={requestMapping.headers ?? {}}
                onChange={(v) => updateSection("headers", v)}
                scene={scene}
                currentStepId={step.stepId}
                placeholder="Header Key"
                descriptions={requestMapping._headersDesc ?? {}}
                onDescriptionsChange={(d) =>
                  onChange({ ...step, requestMapping: { ...requestMapping, _headersDesc: d } })
                }
              />
            </TabsContent>

            {/* ── 请求体 ── */}
            <TabsContent value="body" className={cn("mt-2", disabled && "pointer-events-none opacity-50")}>
              {method === "GET" ? (
                <div className="rounded-md border border-dashed p-8 text-center text-xs text-muted-foreground">
                  GET 请求通常不包含 Body，如需发送请切换为 POST 方法
                </div>
              ) : (
                <div className="space-y-3">
                  {/* 请求体类型选择器（Postman 风格单选按钮） */}
                  <div className="flex items-center gap-3 text-xs">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="bodyType"
                        checked={bodyType === "none"}
                        onChange={() => updateBodyType("none")}
                        className="accent-blue-600"
                      />
                      none
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="bodyType"
                        checked={bodyType === "form-data"}
                        onChange={() => updateBodyType("form-data")}
                        className="accent-blue-600"
                      />
                      <TableIcon className="size-3" />
                      form-data
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="bodyType"
                        checked={bodyType === "x-www-form-urlencoded"}
                        onChange={() => updateBodyType("x-www-form-urlencoded")}
                        className="accent-blue-600"
                      />
                      urlencoded
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="bodyType"
                        checked={bodyType.startsWith("raw")}
                        onChange={() => updateBodyType("raw-json")}
                        className="accent-blue-600"
                      />
                      raw
                    </label>
                    {bodyType.startsWith("raw") && (
                      <Select value={bodyType} onValueChange={(v: BodyType) => updateBodyType(v)}>
                        <SelectTrigger className="h-7 w-[100px] text-[10px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="raw-json" className="text-xs">
                            <FileJsonIcon className="size-3 mr-1" /> JSON
                          </SelectItem>
                          <SelectItem value="raw-text" className="text-xs">
                            <FileTextIcon className="size-3 mr-1" /> Text
                          </SelectItem>
                          <SelectItem value="raw-xml" className="text-xs">
                            <FileCodeIcon className="size-3 mr-1" /> XML
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  </div>

                  {/* 按类型渲染请求体内容 */}
                  {bodyType === "none" && (
                    <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground">
                      该请求不包含 Body
                    </div>
                  )}

                  {/* ── form-data：键/值/描述表 ── */}
                  {bodyType === "form-data" && (
                    <FormDataEditor
                      scene={scene}
                      step={step}
                      onChange={onChange}
                    />
                  )}

                  {/* ── x-www-form-urlencoded：键/值/描述 ── */}
                  {bodyType === "x-www-form-urlencoded" && (
                    <FieldMapper
                      label="URL Encoded Form"
                      description="以 application/x-www-form-urlencoded 格式发送，数据编码为 key=value&key2=value2"
                      value={requestMapping.urlEncodedData ?? {}}
                      onChange={(v) =>
                        onChange({ ...step, requestMapping: { ...requestMapping, urlEncodedData: v } })
                      }
                      scene={scene}
                      currentStepId={step.stepId}
                      placeholder="Field Name"
                      descriptions={requestMapping._urlEncodedDesc ?? {}}
                      onDescriptionsChange={(d) =>
                        onChange({ ...step, requestMapping: { ...requestMapping, _urlEncodedDesc: d } })
                      }
                    />
                  )}

                  {/* ── raw-json：支持变量的树形编辑器 ── */}
                  {bodyType === "raw-json" && (
                    <BodyTreeEditor
                      format="json"
                      scene={scene}
                      step={step}
                      onChange={(rm) => onChange({ ...step, requestMapping: rm })}
                    />
                  )}

                  {bodyType === "raw-text" && (
                    <div className="space-y-2">
                      <span className="text-[10px] text-muted-foreground">
                        Content-Type: text/plain ·
                      </span>
                      <textarea
                        value={rawBodyText}
                        onChange={(e) => updateRawBody(e.target.value)}
                        placeholder="输入纯文本内容"
                        className="w-full h-[200px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring resize-y"
                      />
                    </div>
                  )}

                  {bodyType === "raw-xml" && (
                    <BodyTreeEditor
                      format="xml"
                      scene={scene}
                      step={step}
                      onChange={(rm) => onChange({ ...step, requestMapping: rm })}
                    />
                  )}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </CollapsibleContent>
      </Collapsible>

      {/* ── 响应配置区域 ── */}
      {showResponse && (
        <Collapsible open={responseOpen} onOpenChange={setResponseOpen}>
          <CollapsibleTrigger className="flex items-center gap-2 w-full py-2 border-b text-sm font-bold text-emerald-600 hover:text-emerald-700 transition-colors">
            {responseOpen ? (
              <ChevronDownIcon className="size-4" />
            ) : (
              <ChevronRightIcon className="size-4" />
            )}
            响应配置
          </CollapsibleTrigger>

          <CollapsibleContent className="space-y-4 pt-3">
            <HttpResponseMappingEditor
              step={step}
              onChange={(updates) => onChange({ ...step, ...updates })}
              disabled={disabled}
            />
          </CollapsibleContent>
        </Collapsible>
      )}

      {showResponse && showExtraction && (
        <HttpOutputExtractionSection
          step={step}
          onChange={(updates) => onChange({ ...step, ...updates })}
          disabled={disabled}
        />
      )}
    </div>
  );
}

/* ── form-data 表格编辑器 ── */

interface FormDataRow {
  key: string;
  value: string;
  description: string;
  enabled: boolean;
}

function FormDataEditor({
  scene,
  step,
  onChange,
}: {
  scene?: SceneDefinition;
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
}) {
  const requestMapping = (step.requestMapping ?? {}) as HttpRequestMapping;
  const rows: FormDataRow[] = requestMapping.formData ?? [
    { key: "", value: "", description: "", enabled: true },
  ];
  const [pendingDeleteIdx, setPendingDeleteIdx] = useState<number | null>(null);

  const updateRows = (next: FormDataRow[]) => {
    onChange({
      ...step,
      requestMapping: { ...requestMapping, formData: next },
    });
  };

  const updateRow = (index: number, field: keyof FormDataRow, val: string | boolean) => {
    const next = [...rows];
    next[index] = { ...next[index]!, [field]: val };
    updateRows(next);
  };

  const removeRow = (index: number) => {
    updateRows(rows.filter((_, i) => i !== index));
  };

  const addRow = () => {
    updateRows([...rows, { key: "", value: "", description: "", enabled: true }]);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground">
          Form Data
          <span className="ml-2 text-[10px] font-normal italic">multipart/form-data</span>
        </span>
        <Button variant="ghost" size="icon-sm" onClick={addRow}>
          <PlusIcon className="size-4" />
        </Button>
      </div>

      {/* 表头 */}
      <div className="grid grid-cols-[32px_1fr_1fr_1fr_32px] gap-2 px-2 py-1.5 bg-muted/30 rounded-md text-[10px] font-bold text-muted-foreground uppercase">
        <div className="text-center"></div>
        <div>Key</div>
        <div>Value</div>
        <div>Description</div>
        <div></div>
      </div>

      {/* 表格行 */}
      <div className="space-y-1">
        {rows.map((row, idx) => {
          const isVar = !!(scene && row.value && isVariableRef(row.value));
          const displayVal = isVar
            ? resolveVariableLabel(row.value, scene, step.stepId)
            : row.value;

          return (
            <div
              key={idx}
              className="grid grid-cols-[32px_1fr_1fr_1fr_32px] gap-2 items-center"
            >
              {/* 启用复选框 */}
              <div className="flex justify-center">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => updateRow(idx, "enabled", e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                />
              </div>

              {/* 键 */}
              <Input
                value={row.key}
                onChange={(e) => updateRow(idx, "key", e.target.value)}
                placeholder="field_name"
                className="h-7 text-[10px] font-mono"
              />

              {/* 带变量选择器的值 */}
              <div className="relative group">
                <Input
                  value={displayVal}
                  onChange={(e) => updateRow(idx, "value", e.target.value)}
                  placeholder="值或 ${...} 变量"
                  className={cn(
                    "h-7 pr-7 text-[10px]",
                    isVar && "bg-blue-50/50 text-blue-700 font-medium dark:bg-blue-950/30 dark:text-blue-300",
                    !isVar && "font-mono",
                  )}
                  readOnly={isVar}
                />
                {scene && (
                <div className="absolute right-0.5 top-1/2 -translate-y-1/2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="ghost" size="icon-sm" className="h-5 w-5">
                        <VariableIcon className="size-3 text-primary" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[300px] p-0" align="end">
                      <VariableSelector
                        scene={scene}
                        currentStepId={step.stepId}
                        onSelect={(v) => updateRow(idx, "value", v)}
                      />
                    </PopoverContent>
                  </Popover>
                </div>
                )}
              </div>

              {/* 描述 */}
              <Input
                value={row.description}
                onChange={(e) => updateRow(idx, "description", e.target.value)}
                placeholder="字段说明"
                className="h-7 text-[10px]"
              />

              {/* 删除 */}
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setPendingDeleteIdx(idx)}
                className="text-muted-foreground hover:text-destructive h-6 w-6"
              >
                <Trash2Icon className="size-3" />
              </Button>
            </div>
          );
        })}
      </div>

      {rows.length === 0 && (
        <div className="py-4 text-center text-[10px] text-muted-foreground italic border border-dashed rounded-md">
          暂无表单字段，点击 + 添加
        </div>
      )}

      <ConfirmDialog
        open={pendingDeleteIdx !== null}
        onOpenChange={(open) => { if (!open) setPendingDeleteIdx(null); }}
        onConfirm={() => { if (pendingDeleteIdx !== null) removeRow(pendingDeleteIdx); }}
        title="删除字段"
        description="确定删除该表单字段吗？"
      />
    </div>
  );
}
