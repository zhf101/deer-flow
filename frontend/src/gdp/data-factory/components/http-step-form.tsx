"use client";

import {
  ChevronDownIcon,
  ChevronRightIcon,
  CodeIcon,
  FileJsonIcon,
  FileTextIcon,
  FileCodeIcon,
  GlobeIcon,
  KeyRoundIcon,
  PlusIcon,
  ShieldIcon,
  TableIcon,
  Trash2Icon,
  VariableIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

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

import { listServiceEndpoints } from "../lib/api";
import { HTTP_METHODS } from "../lib/defaults";
import type {
  HttpMethod,
  SceneDefinition,
  ServiceEndpointResponse,
  StepDefinition,
} from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";

import { FieldMapper } from "./field-mapper";
import { HeaderFieldMapper } from "./header-field-mapper";
import { HttpResponseMappingEditor } from "./http-response-mapping-editor";
import { VariableSelector } from "./variable-selector";
import { BodyTreeEditor } from "./body-tree-editor";

/* ── types ──────────────────────────────────────────────────────── */

interface HttpStepFormProps {
  scene: SceneDefinition;
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
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

/* ── main component ─────────────────────────────────────────────── */

export function HttpStepForm({ scene, step, onChange }: HttpStepFormProps) {
  const [endpoints, setEndpoints] = useState<ServiceEndpointResponse[]>([]);
  const [activeTab, setActiveTab] = useState("body");
  const [requestOpen, setRequestOpen] = useState(true);
  const [responseOpen, setResponseOpen] = useState(true);

  /* load service endpoints */
  const loadEndpoints = useCallback(async () => {
    try {
      setEndpoints(await listServiceEndpoints());
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void loadEndpoints();
  }, [loadEndpoints]);

  const serviceCodes = useMemo(() => {
    const seen = new Map<string, string>();
    for (const ep of endpoints) {
      if (!seen.has(ep.serviceCode)) seen.set(ep.serviceCode, ep.serviceName);
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [endpoints]);

  const selectedEndpoint = endpoints.find((ep) => ep.serviceCode === step.serviceCode);
  const method = step.method ?? "POST";
  const requestMapping = step.requestMapping || {};

  /* ── auth config helpers ──────────────────────────────────────── */
  const authConfig: AuthConfig = (requestMapping as any).authConfig ?? { type: "none" };

  const updateAuthConfig = (next: AuthConfig) => {
    const headers = { ...(requestMapping.headers || {}) } as Record<string, string>;
    const query = { ...(requestMapping.query || {}) } as Record<string, string>;

    // Clean up previous auth-managed entries
    delete headers["Authorization"];
    const prevAuth: AuthConfig = (requestMapping as any).authConfig ?? { type: "none" };
    if (prevAuth.type === "apikey" && prevAuth.key) {
      if (prevAuth.addTo === "query") {
        delete query[prevAuth.key];
      } else {
        delete headers[prevAuth.key];
      }
    }

    if (next.type === "bearer" && next.token) {
      headers["Authorization"] = `Bearer ${next.token}`;
    } else if (next.type === "basic" && next.username) {
      headers["Authorization"] = `Basic {{${next.username}:${next.password || ""}}}`;
    } else if (next.type === "apikey" && next.key) {
      if (next.addTo === "query") {
        query[next.key] = next.value || "";
      } else {
        headers[next.key] = next.value || "";
      }
    }

    onChange({
      ...step,
      requestMapping: { ...requestMapping, headers, query, authConfig: next } as any,
    });
  };

  /* ── body type helpers ────────────────────────────────────────── */
  const bodyType: BodyType = (requestMapping as any).bodyType ?? "raw-json";

  const updateBodyType = (next: BodyType) => {
    const updated = { ...requestMapping, bodyType: next } as any;
    // Auto-set Content-Type header when switching body type
    const headers = { ...(requestMapping.headers || {}) } as Record<string, string>;
    if (next === "raw-json") {
      headers["Content-Type"] = "application/json";
    } else if (next === "raw-xml") {
      headers["Content-Type"] = "application/xml";
    } else if (next === "raw-text") {
      headers["Content-Type"] = "text/plain";
    } else if (next === "x-www-form-urlencoded") {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else if (next === "form-data") {
      delete headers["Content-Type"]; // browser sets multipart boundary
    } else if (next === "none") {
      delete headers["Content-Type"];
    }
    updated.headers = headers;
    onChange({ ...step, requestMapping: updated });
  };

  const rawBodyText = (requestMapping as any).rawBody ?? "";

  const updateRawBody = (text: string) => {
    onChange({
      ...step,
      requestMapping: { ...requestMapping, rawBody: text } as any,
    });
  };

  /* ── request mapping section updater ──────────────────────────── */
  const updateSection = (section: string, value: any) => {
    onChange({ ...step, requestMapping: { ...requestMapping, [section]: value } });
  };

  /* ── tab badge counts ─────────────────────────────────────────── */
  const paramCount = Object.keys(requestMapping.query || {}).length;
  const headerCount = Object.keys(requestMapping.headers || {}).length;
  const hasAuth = authConfig.type !== "none";
  const hasBody = method === "POST" && bodyType !== "none";

  return (
    <div className="space-y-2">
      {/* ═══════════════════ REQUEST (collapsible) ═══════════════════ */}
      <Collapsible open={requestOpen} onOpenChange={setRequestOpen}>
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

        <CollapsibleContent className="space-y-2 pt-2">
          {/* ── ADDRESS BAR ── */}
          <div className="flex items-center gap-1.5 rounded-lg border bg-muted/20 p-1.5">
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
              value={step.serviceCode ?? "__none__"}
              onValueChange={(value) =>
                onChange({ ...step, serviceCode: value === "__none__" ? "" : value })
              }
            >
              <SelectTrigger className="h-8 w-[140px] text-xs shrink-0">
                <SelectValue placeholder="选择服务" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__" className="text-xs">无服务前缀</SelectItem>
                {serviceCodes.map((svc) => (
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
                selectedEndpoint
                  ? `/v1/resource (前缀: ${selectedEndpoint.baseUrl})`
                  : "https://api.example.com/v1/resource"
              }
              className="h-8 flex-1 text-xs font-mono"
            />
          </div>
          {selectedEndpoint && (
            <p className="text-[10px] text-muted-foreground pl-1">
              当前环境前缀:{" "}
              <span className="font-mono text-blue-600">{selectedEndpoint.baseUrl}</span>
            </p>
          )}

          {/* ── REQUEST TABS ── */}
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

            {/* ── Params ── */}
            <TabsContent value="params" className="mt-2">
              <FieldMapper
                label="查询参数"
                description="URL 问号后面的参数, 如 ?id=1&name=test"
                value={requestMapping.query || {}}
                onChange={(v) => updateSection("query", v)}
                scene={scene}
                currentStepId={step.stepId}
                placeholder="Param Key"
                descriptions={(requestMapping as any)._queryDesc || {}}
                onDescriptionsChange={(d) =>
                  onChange({ ...step, requestMapping: { ...requestMapping, _queryDesc: d } as any })
                }
              />
            </TabsContent>

            {/* ── Authorization ── */}
            <TabsContent value="auth" className="mt-2">
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
                    <p className="text-[10px] text-muted-foreground">
                      支持变量引用，如 <code className="font-mono text-blue-600">${"{{steps.login.outputs.token}}"}</code>
                    </p>
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
                        placeholder="密码（支持变量引用）"
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
                        ? `将以 ${authConfig.key || "<key>"}=<value> 追加到 URL 查询参数`
                        : `将以 ${authConfig.key || "<key>"}: <value> 追加到请求头`}
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

            {/* ── Headers ── */}
            <TabsContent value="headers" className="mt-2">
              <HeaderFieldMapper
                label="请求头"
                description="配置 HTTP Header, 输入时自动联想常见 Header"
                value={requestMapping.headers || {}}
                onChange={(v) => updateSection("headers", v)}
                scene={scene}
                currentStepId={step.stepId}
                placeholder="Header Key"
                descriptions={(requestMapping as any)._headersDesc || {}}
                onDescriptionsChange={(d) =>
                  onChange({ ...step, requestMapping: { ...requestMapping, _headersDesc: d } as any })
                }
              />
            </TabsContent>

            {/* ── Body ── */}
            <TabsContent value="body" className="mt-2">
              {method === "GET" ? (
                <div className="rounded-md border border-dashed p-8 text-center text-xs text-muted-foreground">
                  GET 请求通常不包含 Body，如需发送请切换为 POST 方法
                </div>
              ) : (
                <div className="space-y-3">
                  {/* Body type selector (Postman-style radio buttons) */}
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

                  {/* Body content based on type */}
                  {bodyType === "none" && (
                    <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground">
                      该请求不包含 Body
                    </div>
                  )}

                  {/* ── form-data: Key / Value / Description table ── */}
                  {bodyType === "form-data" && (
                    <FormDataEditor
                      scene={scene}
                      step={step}
                      onChange={onChange}
                    />
                  )}

                  {/* ── x-www-form-urlencoded: Key / Value / Description ── */}
                  {bodyType === "x-www-form-urlencoded" && (
                    <FieldMapper
                      label="URL Encoded Form"
                      description="以 application/x-www-form-urlencoded 格式发送，数据编码为 key=value&key2=value2"
                      value={(requestMapping as any).urlEncodedData || {}}
                      onChange={(v) =>
                        onChange({ ...step, requestMapping: { ...requestMapping, urlEncodedData: v } as any })
                      }
                      scene={scene}
                      currentStepId={step.stepId}
                      placeholder="Field Name"
                      descriptions={(requestMapping as any)._urlEncodedDesc || {}}
                      onDescriptionsChange={(d) =>
                        onChange({ ...step, requestMapping: { ...requestMapping, _urlEncodedDesc: d } as any })
                      }
                    />
                  )}

                  {/* ── raw-json: Tree editor with variable support ── */}
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
                        Content-Type: text/plain · 支持变量引用
                      </span>
                      <textarea
                        value={rawBodyText}
                        onChange={(e) => updateRawBody(e.target.value)}
                        placeholder="输入纯文本内容，支持变量引用 ${...}"
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

      {/* ═══════════════════ RESPONSE SECTION ═══════════════════ */}
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
          />
        </CollapsibleContent>
      </Collapsible>

    </div>
  );
}

/* ── form-data table editor ────────────────────────────────────── */

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
  scene: SceneDefinition;
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
}) {
  const requestMapping = step.requestMapping || {};
  const rows: FormDataRow[] = (requestMapping as any).formData ?? [
    { key: "", value: "", description: "", enabled: true },
  ];

  const updateRows = (next: FormDataRow[]) => {
    onChange({
      ...step,
      requestMapping: { ...requestMapping, formData: next } as any,
    });
  };

  const updateRow = (index: number, field: keyof FormDataRow, val: any) => {
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

      {/* Table header */}
      <div className="grid grid-cols-[32px_1fr_1fr_1fr_32px] gap-2 px-2 py-1.5 bg-muted/30 rounded-md text-[10px] font-bold text-muted-foreground uppercase">
        <div className="text-center"></div>
        <div>Key</div>
        <div>Value</div>
        <div>Description</div>
        <div></div>
      </div>

      {/* Table rows */}
      <div className="space-y-1">
        {rows.map((row, idx) => {
          const isVar = row.value && isVariableRef(row.value);
          const displayVal = isVar
            ? resolveVariableLabel(row.value, scene, step.stepId)
            : row.value;

          return (
            <div
              key={idx}
              className="grid grid-cols-[32px_1fr_1fr_1fr_32px] gap-2 items-center"
            >
              {/* Enable checkbox */}
              <div className="flex justify-center">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => updateRow(idx, "enabled", e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                />
              </div>

              {/* Key */}
              <Input
                value={row.key}
                onChange={(e) => updateRow(idx, "key", e.target.value)}
                placeholder="field_name"
                className="h-7 text-[10px] font-mono"
              />

              {/* Value with variable selector */}
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
              </div>

              {/* Description */}
              <Input
                value={row.description}
                onChange={(e) => updateRow(idx, "description", e.target.value)}
                placeholder="字段说明"
                className="h-7 text-[10px]"
              />

              {/* Delete */}
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => removeRow(idx)}
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
    </div>
  );
}
