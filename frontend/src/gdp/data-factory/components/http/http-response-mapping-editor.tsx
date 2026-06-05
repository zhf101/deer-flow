"use client";

import { json } from "@codemirror/lang-json";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import {
  ChevronDownIcon,
  ChevronRightIcon,
  ClipboardCopyIcon,
  CodeIcon,
  CookieIcon,
  EyeIcon,
  FileCodeIcon,
  FileJsonIcon,
  FileTextIcon,
  PlusIcon,
  RefreshCwIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  Trash2Icon,
  TreePineIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import {
  countFields,
  flattenSchema,
  getFlatIndex,
  jsonToFields,
  parseJsonWithComments,
  updateFieldPropAtPath,
} from "../../lib/schema-utils";
import type {
  ConditionOperator,
  ConditionRule,
  InputFieldDefinition,
  StepDefinition,
} from "../../lib/types";

/* ── themes ─────────────────────────────────────────────────────── */

const darkTheme = monokaiInit({
  settings: { background: "transparent", gutterBackground: "transparent", fontSize: "12px" },
});
const lightTheme = basicLightInit({
  settings: { background: "transparent", fontSize: "12px" },
});

/* ── types ──────────────────────────────────────────────────────── */

interface HttpResponseMappingEditorProps {
  step: StepDefinition;
  onChange: (updates: Partial<StepDefinition>) => void;
}

type ResponseTab = "body" | "headers" | "cookies";
type SubView = "tree" | "preview";
type BodyFormat = "json" | "xml" | "text";
type ImportFormat = BodyFormat | "headers";

/* ── common HTTP response headers ───────────────────────────────── */

const COMMON_RESPONSE_HEADERS = [
  { name: "Content-Type", desc: "内容类型" },
  { name: "Content-Length", desc: "内容长度" },
  { name: "Set-Cookie", desc: "设置 Cookie" },
  { name: "Cache-Control", desc: "缓存控制" },
  { name: "ETag", desc: "资源标识" },
  { name: "Location", desc: "重定向地址" },
  { name: "X-Request-Id", desc: "请求追踪 ID" },
  { name: "X-Rate-Limit-Limit", desc: "限流上限" },
  { name: "X-Rate-Limit-Remaining", desc: "限流剩余" },
  { name: "X-Total-Count", desc: "总记录数" },
  { name: "X-Trace-Id", desc: "链路追踪 ID" },
  { name: "Authorization", desc: "认证令牌" },
  { name: "Access-Control-Allow-Origin", desc: "CORS 允许来源" },
];

/* ── main component ─────────────────────────────────────────────── */

export function HttpResponseMappingEditor({
  step,
  onChange,
}: HttpResponseMappingEditorProps) {
  const { resolvedTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<ResponseTab>("body");
  const [bodyView, setBodyView] = useState<SubView>("tree");
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importFormat, setImportFormat] = useState<ImportFormat>("json");
  const [dialogInput, setDialogInput] = useState("");

  const schema = useMemo(() => step.responseSchema ?? [], [step.responseSchema]);
  const headersSchema = useMemo(() => step.responseHeadersSchema ?? [], [step.responseHeadersSchema]);
  const cookiesSchema = useMemo(() => step.responseCookiesSchema ?? [], [step.responseCookiesSchema]);
  const outputMapping = step.outputMapping ?? {};
  const responseHandling = step.responseHandling ?? {
    expectedContentType: "JSON",
    statusCode: { success: [200] },
    businessSuccess: { allOf: [] },
    businessFailure: { anyOf: [] },
  };
  const successRules = responseHandling.businessSuccess?.allOf ?? [];
  const failureRules = responseHandling.businessFailure?.anyOf ?? [];

  /* ── body format detection ────────────────────────────────────── */
  const bodyFormat: BodyFormat = useMemo(() => {
    const ct = responseHandling.expectedContentType;
    if (ct === "XML") return "xml";
    if (ct === "TEXT") return "text";
    return "json";
  }, [responseHandling.expectedContentType]);

  /* ── flat field lists ─────────────────────────────────────────── */
  const bodyFlatFields = useMemo(() => flattenSchema(schema, "$.body"), [schema]);
  const extractableBodyFields = useMemo(
    () => bodyFlatFields.filter((f) => f.type !== "object" && f.type !== "array"),
    [bodyFlatFields],
  );

  const headerExtractable = useMemo(
    () => headersSchema.filter((h) => h.type !== "object" && h.type !== "array"),
    [headersSchema],
  );
  const cookieExtractable = useMemo(
    () => cookiesSchema.filter((c) => c.type !== "object" && c.type !== "array"),
    [cookiesSchema],
  );

  /* ── CodeMirror extensions ────────────────────────────────────── */
  const jsonExtensions = useMemo(() => [json()], []);

  /* ── error mapping & retry policy (section 4) ─────────────────── */
  const errorMapping = step.errorMapping ?? {
    messageTemplate: "",
    fields: {},
    fallbackMessage: "",
    exposeRawResponse: false,
  };
  const retryPolicy = step.retryPolicy ?? {
    enabled: false,
    maxAttempts: 1,
    intervalMs: 1000,
    retryOn: [],
  };

  /* ── raw body text (stored in requestMapping for persistence) ── */
  const rawResponseText = (step.requestMapping as any)._rawResponseSample ?? "";

  /* ── import handlers ──────────────────────────────────────────── */
  const handleImportBody = useCallback(() => {
    try {
      if (importFormat === "json") {
        const { cleanJson, labels } = parseJsonWithComments(dialogInput);
        const parsed = JSON.parse(cleanJson);
        const generatedSchema = jsonToFields(parsed, labels);
        const text = JSON.stringify(parsed, null, 2);
        onChange({
          responseSchema: generatedSchema,
          requestMapping: { ...step.requestMapping, _rawResponseSample: text } as any,
        });
        toast.success("JSON 响应结构已解析");
      } else if (importFormat === "xml") {
        const tree = xmlToTree(dialogInput);
        if (tree.length === 0) throw new Error("empty");
        onChange({
          responseSchema: tree,
          requestMapping: { ...step.requestMapping, _rawResponseSample: dialogInput } as any,
        });
        toast.success("XML 响应结构已解析");
      } else {
        // text — no schema to parse, just store as sample
        onChange({
          requestMapping: { ...step.requestMapping, _rawResponseSample: dialogInput } as any,
        });
        toast.success("文本响应样例已保存");
      }
      setShowImportDialog(false);
      setDialogInput("");
    } catch {
      toast.error(`${importFormat.toUpperCase()} 解析失败，请检查格式`);
    }
  }, [dialogInput, importFormat, step.requestMapping, onChange]);

  const handleImportHeaders = useCallback((rawText: string) => {
    try {
      const lines = rawText.split("\n").filter((l) => l.trim());
      const fields: InputFieldDefinition[] = lines.map((line) => {
        const colonIdx = line.indexOf(":");
        if (colonIdx === -1) return null;
        const name = line.slice(0, colonIdx).trim();
        const value = line.slice(colonIdx + 1).trim();
        if (!name) return null;
        return {
          name,
          type: "string" as const,
          required: false,
          batchEnabled: false,
          defaultValue: value,
          label: COMMON_RESPONSE_HEADERS.find((h) => h.name.toLowerCase() === name.toLowerCase())?.desc ?? "",
        };
      }).filter(Boolean) as InputFieldDefinition[];

      if (fields.length > 0) {
        onChange({ responseHeadersSchema: fields });
        toast.success(`已解析 ${fields.length} 个响应头`);
      } else {
        toast.error("未检测到有效的 Header 行");
      }
    } catch {
      toast.error("Headers 解析失败");
    }
  }, [onChange]);

  /* ── body field prop updater ──────────────────────────────────── */
  const updateBodyFieldProp = (flatIndex: number, prop: "defaultValue" | "label" | "remark", value: unknown) => {
    const next = updateFieldPropAtPath(schema, flatIndex, prop, value);
    onChange({ responseSchema: next });
  };

  /* ── extract toggle (generic for all sources) ─────────────────── */
  const toggleExtract = (path: string, displayName: string, checked: boolean, label?: string, remark?: string) => {
    if (checked) {
      const nextMeta = { ...(step.outputMeta ?? {}) };
      nextMeta[displayName] = { label: label ?? "", remark: remark ?? "" };
      onChange({
        outputMapping: { ...outputMapping, [displayName]: path },
        outputMeta: nextMeta,
      });
    } else {
      const next = { ...outputMapping };
      const nextMeta = { ...(step.outputMeta ?? {}) };
      Object.entries(next).forEach(([k, v]) => {
        if (v === path) {
          delete next[k];
          delete nextMeta[k];
        }
      });
      onChange({ outputMapping: next, outputMeta: nextMeta });
    }
  };

  /* ── tab badge counts ─────────────────────────────────────────── */
  const bodyExtractCount = Object.values(outputMapping).filter((v) => v.startsWith("$.body.")).length;
  const headersExtractCount = Object.values(outputMapping).filter((v) => v.startsWith("$.headers.")).length;
  const cookiesExtractCount = Object.values(outputMapping).filter((v) => v.startsWith("$.cookies.")).length;

  /* ── treeToJson for preview ───────────────────────────────────── */
  const previewText = useMemo(() => {
    if (bodyFormat === "text") return rawResponseText;
    if (schema.length === 0) return rawResponseText;
    const obj = treeToSample(schema);
    if (bodyFormat === "xml") return jsonToXml(obj);
    return JSON.stringify(obj, null, 2);
  }, [schema, bodyFormat, rawResponseText]);

  return (
    <div className="space-y-4">
      {/* ═══ SECTION 1: Response Tabs ═══ */}
      <section className="space-y-2">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-primary font-bold text-sm">
            <FileJsonIcon className="size-4" />
            <span>1. 响应报文定义</span>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex items-center gap-1 border-b border-border/40">
          <TabButton
            active={activeTab === "body"}
            onClick={() => setActiveTab("body")}
            icon={<CodeIcon className="size-3.5" />}
            label="Body"
            badge={bodyExtractCount}
          />
          <TabButton
            active={activeTab === "headers"}
            onClick={() => setActiveTab("headers")}
            icon={<FileTextIcon className="size-3.5" />}
            label="Headers"
            badge={headersExtractCount}
          />
          <TabButton
            active={activeTab === "cookies"}
            onClick={() => setActiveTab("cookies")}
            icon={<CookieIcon className="size-3.5" />}
            label="Cookies"
            badge={cookiesExtractCount}
          />
        </div>

        {/* ── BODY TAB ── */}
        {activeTab === "body" && (
          <div className="space-y-2">
            {/* Toolbar: view switcher + format + import */}
            <div className="flex items-center gap-2">
              {/* View mode switch */}
              <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
                <button
                  type="button"
                  onClick={() => setBodyView("tree")}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
                    bodyView === "tree"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <TreePineIcon className="size-3" />
                  树状
                </button>
                <button
                  type="button"
                  onClick={() => setBodyView("preview")}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
                    bodyView === "preview"
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <EyeIcon className="size-3" />
                  预览
                </button>
              </div>

              {/* Content type selector */}
              <Select
                value={bodyFormat}
                onValueChange={(v: BodyFormat) => {
                  const ctMap: Record<BodyFormat, "JSON" | "XML" | "TEXT"> = {
                    json: "JSON",
                    xml: "XML",
                    text: "TEXT",
                  };
                  onChange({
                    responseHandling: { ...responseHandling, expectedContentType: ctMap[v] },
                  });
                }}
              >
                <SelectTrigger className="h-7 w-[100px] text-[10px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="json" className="text-xs">
                    <FileJsonIcon className="size-3 mr-1" /> JSON
                  </SelectItem>
                  <SelectItem value="xml" className="text-xs">
                    <FileCodeIcon className="size-3 mr-1" /> XML
                  </SelectItem>
                  <SelectItem value="text" className="text-xs">
                    <FileTextIcon className="size-3 mr-1" /> Text
                  </SelectItem>
                </SelectContent>
              </Select>

              <div className="ml-auto">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setImportFormat(bodyFormat);
                    setShowImportDialog(true);
                  }}
                  className="gap-1.5 h-7 text-[10px]"
                >
                  {bodyFormat === "json" && <FileJsonIcon className="size-3" />}
                  {bodyFormat === "xml" && <FileCodeIcon className="size-3" />}
                  {bodyFormat === "text" && <FileTextIcon className="size-3" />}
                  贴入报文样例
                </Button>
              </div>
            </div>

            {/* Tree view */}
            {bodyView === "tree" && (
              <div className="rounded-lg border bg-card overflow-hidden">
                <div className="grid grid-cols-[32px_1fr_80px_150px_1fr] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
                  <div className="text-center">提取</div>
                  <div>Key</div>
                  <div>Type</div>
                  <div>示例值</div>
                  <div>Description</div>
                </div>
                <div className="max-h-[400px] overflow-auto divide-y divide-border/50">
                  {schema.length === 0 ? (
                    <div className="py-8 text-center text-xs text-muted-foreground italic">
                      暂无报文结构，点击&ldquo;贴入报文样例&rdquo;导入
                    </div>
                  ) : (
                    schema.map((field, idx) => (
                      <BodyTreeNode
                        key={idx}
                        field={field}
                        flatIndex={getFlatIndex(schema, idx)}
                        depth={0}
                        outputMapping={outputMapping}
                        flatFields={bodyFlatFields}
                        onUpdateField={updateBodyFieldProp}
                        onToggleExtract={toggleExtract}
                      />
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Preview view - read-only formatted */}
            {bodyView === "preview" && (
              <div className="space-y-1">
                <span className="text-[10px] text-muted-foreground">
                  预览模式 · 基于树状结构生成的 {bodyFormat.toUpperCase()} 样例
                </span>
                {bodyFormat === "json" ? (
                  <div className="json-preview-cm rounded-md border border-input overflow-hidden">
                    <style>{`
                      .json-preview-cm .cm-property { color: #64748b !important; }
                      .json-preview-cm .cm-string { color: #2563eb !important; }
                      .json-preview-cm .cm-number { color: #2563eb !important; }
                      .json-preview-cm .cm-bool { color: #2563eb !important; }
                      .json-preview-cm .cm-null { color: #2563eb !important; }
                    `}</style>
                    <CodeMirror
                      value={previewText ?? "{\n  \n}"}
                      height="300px"
                      extensions={jsonExtensions}
                      theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                      editable={false}
                      readOnly
                    />
                  </div>
                ) : (
                  <div className="rounded-md border bg-muted/10 p-3 font-mono text-xs whitespace-pre-wrap min-h-[200px] max-h-[400px] overflow-auto">
                    {previewText ?? <span className="italic text-muted-foreground">暂无{bodyFormat === "xml" ? "XML" : "文本"}样例</span>}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── HEADERS TAB ── */}
        {activeTab === "headers" && (
          <div className="space-y-2">
            <div className="flex items-center justify-end gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setImportFormat("headers");
                  setShowImportDialog(true);
                }}
                className="gap-1.5 h-7 text-[10px]"
              >
                <FileTextIcon className="size-3" />
                贴入 Headers
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => {
                  onChange({
                    responseHeadersSchema: [
                      ...headersSchema,
                      { name: `header_${headersSchema.length + 1}`, type: "string", required: false, batchEnabled: false, defaultValue: "", label: "" },
                    ],
                  });
                }}
              >
                <PlusIcon className="size-4" />
              </Button>
            </div>

            <div className="rounded-lg border bg-card overflow-hidden">
              <div className="grid grid-cols-[32px_1fr_1fr_1fr_32px] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
                <div className="text-center">提取</div>
                <div>KEY</div>
                <div>VALUE</div>
                <div>DESCRIPTION</div>
                <div></div>
              </div>
              <div className="max-h-[360px] overflow-auto divide-y divide-border/50">
                {headersSchema.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground italic">
                    暂未定义响应头，点击&ldquo;贴入 Headers&rdquo;或 + 添加
                  </div>
                ) : (
                  headersSchema.map((header, idx) => {
                    const headerPath = `$.headers.${header.name}`;
                    const isExtracted = Object.values(outputMapping).some((v) => v === headerPath);
                    return (
                      <div key={idx} className="grid grid-cols-[32px_1fr_1fr_1fr_32px] gap-2 items-center px-3 py-1.5 hover:bg-muted/20 transition-colors">
                        <div className="flex justify-center">
                          <input
                            type="checkbox"
                            checked={isExtracted}
                            onChange={(e) =>
                              toggleExtract(headerPath, header.name, e.target.checked, header.label ?? "", header.remark ?? "")
                            }
                            className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                          />
                        </div>
                        <Input
                          value={header.name}
                          onChange={(e) => {
                            const next = [...headersSchema];
                            next[idx] = { ...header, name: e.target.value };
                            onChange({ responseHeadersSchema: next });
                          }}
                          placeholder="Header Name"
                          className="h-7 text-[10px] font-mono"
                        />
                        <Input
                          value={header.defaultValue != null ? `${header.defaultValue as string | number | boolean}` : ""}
                          onChange={(e) => {
                            const next = [...headersSchema];
                            next[idx] = { ...header, defaultValue: e.target.value };
                            onChange({ responseHeadersSchema: next });
                          }}
                          placeholder="示例值"
                          className="h-7 text-[10px] font-mono"
                        />
                        <Input
                          value={header.label ?? ""}
                          onChange={(e) => {
                            const next = [...headersSchema];
                            next[idx] = { ...header, label: e.target.value };
                            onChange({ responseHeadersSchema: next });
                          }}
                          placeholder="说明"
                          className="h-7 text-[10px]"
                        />
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => {
                            const next = headersSchema.filter((_, i) => i !== idx);
                            // Clean up any extraction mapping for this header
                            const nextMapping = { ...outputMapping };
                            const nextMeta = { ...(step.outputMeta ?? {}) };
                            Object.entries(nextMapping).forEach(([k, v]) => {
                              if (v === headerPath) {
                                delete nextMapping[k];
                                delete nextMeta[k];
                              }
                            });
                            onChange({
                              responseHeadersSchema: next,
                              outputMapping: nextMapping,
                              outputMeta: nextMeta,
                            });
                          }}
                          className="text-muted-foreground hover:text-destructive h-6 w-6"
                        >
                          <Trash2Icon className="size-3" />
                        </Button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── COOKIES TAB ── */}
        {activeTab === "cookies" && (
          <div className="space-y-2">
            <div className="flex items-center justify-end">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => {
                  onChange({
                    responseCookiesSchema: [
                      ...cookiesSchema,
                      { name: `cookie_${cookiesSchema.length + 1}`, type: "string", required: false, batchEnabled: false, defaultValue: "", label: "" },
                    ],
                  });
                }}
              >
                <PlusIcon className="size-4" />
              </Button>
            </div>

            <div className="rounded-lg border bg-card overflow-hidden">
              <div className="grid grid-cols-[32px_1fr_1fr_100px_80px_100px_56px_56px_32px] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
                <div className="text-center">提取</div>
                <div>Name</div>
                <div>Value</div>
                <div>Domain</div>
                <div>Path</div>
                <div>Expires</div>
                <div className="text-center">HttpOnly</div>
                <div className="text-center">Secure</div>
                <div></div>
              </div>
              <div className="max-h-[360px] overflow-auto divide-y divide-border/50">
                {cookiesSchema.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground italic">
                    暂未定义 Cookie，点击 + 添加服务器返回的 Set-Cookie
                  </div>
                ) : (
                  cookiesSchema.map((cookie, idx) => {
                    const cookiePath = `$.cookies.${cookie.name}`;
                    const isExtracted = Object.values(outputMapping).some((v) => v === cookiePath);
                    return (
                      <div key={idx} className="grid grid-cols-[32px_1fr_1fr_100px_80px_100px_56px_56px_32px] gap-2 items-center px-3 py-1.5 hover:bg-muted/20 transition-colors">
                        <div className="flex justify-center">
                          <input
                            type="checkbox"
                            checked={isExtracted}
                            onChange={(e) =>
                              toggleExtract(cookiePath, cookie.name, e.target.checked, cookie.label ?? "", cookie.remark ?? "")
                            }
                            className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                          />
                        </div>
                        <Input
                          value={cookie.name}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, name: e.target.value };
                            onChange({ responseCookiesSchema: next });
                          }}
                          placeholder="SESSIONID"
                          className="h-7 text-[10px] font-mono"
                        />
                        <Input
                          value={cookie.defaultValue != null ? `${cookie.defaultValue as string | number | boolean}` : ""}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, defaultValue: e.target.value };
                            onChange({ responseCookiesSchema: next });
                          }}
                          placeholder="abc123"
                          className="h-7 text-[10px] font-mono"
                        />
                        <Input
                          value={(cookie as any).domain ?? ""}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, domain: e.target.value } as any;
                            onChange({ responseCookiesSchema: next });
                          }}
                          placeholder=".example.com"
                          className="h-7 text-[10px] font-mono"
                        />
                        <Input
                          value={(cookie as any).path ?? "/"}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, path: e.target.value } as any;
                            onChange({ responseCookiesSchema: next });
                          }}
                          placeholder="/"
                          className="h-7 text-[10px] font-mono"
                        />
                        <Input
                          value={(cookie as any).expires ?? ""}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, expires: e.target.value } as any;
                            onChange({ responseCookiesSchema: next });
                          }}
                          placeholder="Session"
                          className="h-7 text-[10px] font-mono"
                        />
                        <div className="flex justify-center">
                          <input
                            type="checkbox"
                            checked={(cookie as any).httpOnly === true}
                            onChange={(e) => {
                              const next = [...cookiesSchema];
                              next[idx] = { ...cookie, httpOnly: e.target.checked } as any;
                              onChange({ responseCookiesSchema: next });
                            }}
                            className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                          />
                        </div>
                        <div className="flex justify-center">
                          <input
                            type="checkbox"
                            checked={(cookie as any).secure === true}
                            onChange={(e) => {
                              const next = [...cookiesSchema];
                              next[idx] = { ...cookie, secure: e.target.checked } as any;
                              onChange({ responseCookiesSchema: next });
                            }}
                            className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                          />
                        </div>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => {
                            const next = cookiesSchema.filter((_, i) => i !== idx);
                            const nextMapping = { ...outputMapping };
                            const nextMeta = { ...(step.outputMeta ?? {}) };
                            Object.entries(nextMapping).forEach(([k, v]) => {
                              if (v === cookiePath) {
                                delete nextMapping[k];
                                delete nextMeta[k];
                              }
                            });
                            onChange({
                              responseCookiesSchema: next,
                              outputMapping: nextMapping,
                              outputMeta: nextMeta,
                            });
                          }}
                          className="text-muted-foreground hover:text-destructive h-6 w-6"
                        >
                          <Trash2Icon className="size-3" />
                        </Button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ═══ SECTION 2: Extraction Manager ═══ */}
      <section className="space-y-3">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-blue-600 font-bold text-sm">
            <ClipboardCopyIcon className="size-4" />
            <span>2. 提取响应数据到变量</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          从 Body / Headers / Cookies 中提取字段，定义下游步骤可引用的变量名。
        </p>
        <div className="space-y-2">
          <div className="rounded-lg border bg-card overflow-hidden">
            <div className="grid grid-cols-[80px_1fr_1fr_1fr_48px] gap-3 px-3 py-2 bg-muted/40 text-[10px] font-bold text-muted-foreground uppercase border-b">
              <div>来源</div>
              <div>响应字段</div>
              <div>下游变量名</div>
              <div>Description</div>
              <div className="text-center">操作</div>
            </div>
            <div className="p-1.5 space-y-1.5">
              {Object.entries(outputMapping).map(([varName, path]) => {
                const source = path.startsWith("$.body.")
                  ? "Body"
                  : path.startsWith("$.headers.")
                    ? "Headers"
                    : path.startsWith("$.cookies.")
                      ? "Cookies"
                      : "Body";
                const sourceColor =
                  source === "Body"
                    ? "bg-emerald-500/10 text-emerald-600"
                    : source === "Headers"
                      ? "bg-blue-500/10 text-blue-600"
                      : "bg-amber-500/10 text-amber-600";

                const matched = bodyFlatFields.find((f) => f.path === path);
                const meta = step.outputMeta?.[varName] ?? {};

                return (
                  <div key={varName} className="grid grid-cols-[80px_1fr_1fr_1fr_48px] gap-2 items-center bg-muted/10 p-1 rounded border border-transparent hover:border-border transition-all">
                    <div className="flex justify-center">
                      <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded", sourceColor)}>
                        {source}
                      </span>
                    </div>
                    <div className="px-2 text-xs truncate font-mono" title={path}>
                      {matched ? matched.label : path.split(".").pop()?.replace("[*]", "") ?? path}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-muted-foreground shrink-0">=</span>
                      <Input
                        className="h-7 text-xs font-mono bg-background"
                        value={varName}
                        placeholder="输入变量名"
                        onChange={(e) => {
                          const newName = e.target.value;
                          if (newName === varName) return;
                          const next: Record<string, string> = {};
                          const nextMeta = { ...(step.outputMeta ?? {}) };
                          Object.entries(outputMapping).forEach(([k, v]) => {
                            const targetKey = k === varName ? newName : k;
                            next[targetKey] = v;
                            if (k === varName) {
                              nextMeta[targetKey] = nextMeta[varName] ?? {};
                              delete nextMeta[varName];
                            }
                          });
                          onChange({ outputMapping: next, outputMeta: nextMeta });
                        }}
                      />
                    </div>
                    <Input
                      className="h-7 text-xs bg-background"
                      value={meta.remark ?? ""}
                      placeholder="Description"
                      onChange={(e) => {
                        const nextMeta = { ...(step.outputMeta ?? {}) };
                        nextMeta[varName] = { ...nextMeta[varName], remark: e.target.value };
                        onChange({ outputMeta: nextMeta });
                      }}
                    />
                    <div className="flex justify-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 text-muted-foreground hover:text-destructive"
                        onClick={() => {
                          const next = { ...outputMapping };
                          const nextMeta = { ...(step.outputMeta ?? {}) };
                          delete next[varName];
                          delete nextMeta[varName];
                          onChange({ outputMapping: next, outputMeta: nextMeta });
                        }}
                      >
                        <Trash2Icon className="size-3" />
                      </Button>
                    </div>
                  </div>
                );
              })}
              {Object.keys(outputMapping).length === 0 && (
                <div className="py-4 text-center text-[10px] text-muted-foreground italic">
                  未配置提取项，在上方各页签中勾选字段或点击下方按钮添加
                </div>
              )}
            </div>
          </div>

          {/* Quick add dropdown */}
          <div className="flex gap-2">
            {extractableBodyFields.length > 0 && (
              <Select onValueChange={(path) => {
                if (!path) return;
                const baseName = path.split(".").pop()?.replace("[*]", "") ?? "data";
                let varName = baseName;
                let suffix = 1;
                while (varName in outputMapping) {
                  varName = `${baseName}_${suffix++}`;
                }
                const matchedField = bodyFlatFields.find((f) => f.path === path);
                const nextMeta = { ...(step.outputMeta ?? {}) };
                nextMeta[varName] = {
                  label: matchedField?.fieldLabel ?? "",
                  remark: matchedField?.fieldRemark ?? "",
                };
                onChange({
                  outputMapping: { ...outputMapping, [varName]: path },
                  outputMeta: nextMeta,
                });
              }}>
                <SelectTrigger className="w-[180px] h-8 text-xs gap-2">
                  <PlusIcon className="size-3" />
                  <SelectValue placeholder="+ Body 字段" />
                </SelectTrigger>
                <SelectContent>
                  {extractableBodyFields.map((f) => (
                    <SelectItem key={f.path} value={f.path} className="text-xs">
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {headerExtractable.length > 0 && (
              <Select onValueChange={(name) => {
                if (!name) return;
                const path = `$.headers.${name}`;
                let varName = name.replace(/-/g, "_").toLowerCase();
                let suffix = 1;
                while (varName in outputMapping) {
                  varName = `${name.replace(/-/g, "_").toLowerCase()}_${suffix++}`;
                }
                const header = headersSchema.find((h) => h.name === name);
                const nextMeta = { ...(step.outputMeta ?? {}) };
                nextMeta[varName] = { label: header?.label ?? "", remark: "" };
                onChange({
                  outputMapping: { ...outputMapping, [varName]: path },
                  outputMeta: nextMeta,
                });
              }}>
                <SelectTrigger className="w-[180px] h-8 text-xs gap-2">
                  <PlusIcon className="size-3" />
                  <SelectValue placeholder="+ Header" />
                </SelectTrigger>
                <SelectContent>
                  {headerExtractable.map((h) => (
                    <SelectItem key={h.name} value={h.name} className="text-xs">
                      {h.name} {h.label ? `(${h.label})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {cookieExtractable.length > 0 && (
              <Select onValueChange={(name) => {
                if (!name) return;
                const path = `$.cookies.${name}`;
                let varName = name;
                let suffix = 1;
                while (varName in outputMapping) {
                  varName = `${name}_${suffix++}`;
                }
                const cookie = cookiesSchema.find((c) => c.name === name);
                const nextMeta = { ...(step.outputMeta ?? {}) };
                nextMeta[varName] = { label: cookie?.label ?? "", remark: "" };
                onChange({
                  outputMapping: { ...outputMapping, [varName]: path },
                  outputMeta: nextMeta,
                });
              }}>
                <SelectTrigger className="w-[180px] h-8 text-xs gap-2">
                  <PlusIcon className="size-3" />
                  <SelectValue placeholder="+ Cookie" />
                </SelectTrigger>
                <SelectContent>
                  {cookieExtractable.map((c) => (
                    <SelectItem key={c.name} value={c.name} className="text-xs">
                      {c.name} {c.label ? `(${c.label})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>
      </section>

      {/* ═══ SECTION 3: Business Rules ═══ */}
      <section className="space-y-3">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-green-600 font-bold text-sm">
            <ShieldCheckIcon className="size-4" />
            <span>3. 业务成功规则配置</span>
          </div>
        </div>
        <div className="space-y-4">
          {/* Failure Rules */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-destructive/10 text-destructive text-[10px] px-1.5 py-0.5 rounded font-bold">优先判定失败</span>
              <span className="text-[10px] text-muted-foreground">(任一规则命中即判定为失败)</span>
            </div>
            <div className="rounded-lg border border-destructive/10 bg-destructive/[0.02] p-1.5 space-y-1.5">
              {failureRules.map((rule, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-background p-1.5 rounded border border-destructive/20">
                  <Select
                    value={rule.path}
                    onValueChange={(val) => {
                      const next = [...failureRules];
                      const current = next[idx] as any;
                      next[idx] = { path: val, op: current.op ?? "EQ", value: current.value ?? "" };
                      onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                    }}
                  >
                    <SelectTrigger className="h-7 text-[10px] flex-1 border-none shadow-none font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {extractableBodyFields.map((f) => (
                        <SelectItem key={f.path} value={f.path} className="text-xs">{f.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={rule.op}
                    onValueChange={(val: ConditionOperator) => {
                      const next = [...failureRules];
                      const current = next[idx] as any;
                      next[idx] = { path: current.path ?? "", op: val, value: current.value ?? "" };
                      onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                    }}
                  >
                    <SelectTrigger className="h-7 text-[10px] w-[80px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="EQ" className="text-xs">等于</SelectItem>
                      <SelectItem value="NEQ" className="text-xs">不等于</SelectItem>
                      <SelectItem value="EXISTS" className="text-xs">存在</SelectItem>
                    </SelectContent>
                  </Select>
                  {rule.op !== "EXISTS" && (
                    <Input
                      className="h-7 text-[10px] w-[120px]"
                      value={rule.value != null ? `${rule.value as string | number | boolean}` : ""}
                      onChange={(e) => {
                        const next = [...failureRules];
                        const current = next[idx] as any;
                        next[idx] = { path: current.path ?? "", op: current.op ?? "EQ", value: e.target.value };
                        onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                      }}
                    />
                  )}
                  <Button variant="ghost" size="sm" className="h-6 w-6" onClick={() => {
                    const next = failureRules.filter((_, i) => i !== idx);
                    onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                  }}>
                    <Trash2Icon className="size-3" />
                  </Button>
                </div>
              ))}
              <Button variant="ghost" size="sm" className="w-full h-8 text-[10px] border border-dashed text-destructive border-destructive/20 hover:bg-destructive/5" onClick={() => {
                const next = [...failureRules, { path: extractableBodyFields[0]?.path ?? "", op: "EQ" as ConditionOperator, value: "" }];
                onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
              }}>
                <PlusIcon className="mr-1 size-3" />
                添加失败判定规则 (OR)
              </Button>
            </div>
          </div>

          {/* Success Rules */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-green-500/10 text-green-600 text-[10px] px-1.5 py-0.5 rounded font-bold">满足条件成功</span>
              <span className="text-[10px] text-muted-foreground">(需全部规则同时命中判定为成功)</span>
            </div>
            <div className="rounded-lg border border-green-500/10 bg-green-500/[0.02] p-1.5 space-y-1.5">
              {successRules.map((rule, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-background p-1.5 rounded border border-green-500/20">
                  <Select
                    value={rule.path}
                    onValueChange={(val) => {
                      const next = [...successRules];
                      const current = next[idx] as any;
                      next[idx] = { path: val, op: current.op ?? "EQ", value: current.value ?? "" };
                      onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                    }}
                  >
                    <SelectTrigger className="h-7 text-[10px] flex-1 border-none shadow-none font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {extractableBodyFields.map((f) => (
                        <SelectItem key={f.path} value={f.path} className="text-xs">{f.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={rule.op}
                    onValueChange={(val: ConditionOperator) => {
                      const next = [...successRules];
                      const current = next[idx] as any;
                      next[idx] = { path: current.path ?? "", op: val, value: current.value ?? "" };
                      onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                    }}
                  >
                    <SelectTrigger className="h-7 text-[10px] w-[80px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="EQ" className="text-xs">等于</SelectItem>
                      <SelectItem value="NEQ" className="text-xs">不等于</SelectItem>
                      <SelectItem value="EXISTS" className="text-xs">存在</SelectItem>
                    </SelectContent>
                  </Select>
                  {rule.op !== "EXISTS" && (
                    <Input
                      className="h-7 text-[10px] w-[120px]"
                      value={rule.value != null ? `${rule.value as string | number | boolean}` : ""}
                      onChange={(e) => {
                        const next = [...successRules];
                        const current = next[idx] as any;
                        next[idx] = { path: current.path ?? "", op: current.op ?? "EQ", value: e.target.value };
                        onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                      }}
                    />
                  )}
                  <Button variant="ghost" size="sm" className="h-6 w-6" onClick={() => {
                    const next = successRules.filter((_, i) => i !== idx);
                    onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                  }}>
                    <Trash2Icon className="size-3" />
                  </Button>
                </div>
              ))}
              <Button variant="ghost" size="sm" className="w-full h-8 text-[10px] border border-dashed text-green-600 border-green-500/20 hover:bg-green-500/5" onClick={() => {
                const next = [...successRules, { path: extractableBodyFields[0]?.path ?? "", op: "EQ" as ConditionOperator, value: "" }];
                onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
              }}>
                <PlusIcon className="mr-1 size-3" />
                添加成功判定规则 (AND)
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ═══ SECTION 4: Error Handling & Retry ═══ */}
      <section className="space-y-3">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-orange-600 font-bold text-sm">
            <ShieldAlertIcon className="size-4" />
            <span>4. 请求异常配置</span>
          </div>
        </div>
        <div className="space-y-4">
          {/* Error Mapping */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-orange-500/10 text-orange-600 text-[10px] px-1.5 py-0.5 rounded font-bold">响应异常处理</span>
              <span className="text-[10px] text-muted-foreground">(定义错误消息映射和暴露策略)</span>
            </div>
            <div className="rounded-lg border border-orange-500/10 bg-orange-500/[0.02] p-3 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <span className="text-[10px] text-muted-foreground">错误消息模板</span>
                  <Input
                    value={errorMapping.messageTemplate ?? ""}
                    onChange={(e) =>
                      onChange({
                        errorMapping: { ...errorMapping, messageTemplate: e.target.value },
                      })
                    }
                    placeholder="如: 创建失败：${error.bizCode}"
                    className="h-7 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-[10px] text-muted-foreground">兜底错误消息</span>
                  <Input
                    value={errorMapping.fallbackMessage ?? ""}
                    onChange={(e) =>
                      onChange({
                        errorMapping: { ...errorMapping, fallbackMessage: e.target.value },
                      })
                    }
                    placeholder="请求失败，请稍后重试"
                    className="h-7 text-xs"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Switch
                  checked={errorMapping.exposeRawResponse}
                  onCheckedChange={(checked) =>
                    onChange({
                      errorMapping: { ...errorMapping, exposeRawResponse: checked },
                    })
                  }
                />
                暴露原始响应体给调用方
              </label>
            </div>
          </div>

          {/* Retry Policy */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-amber-500/10 text-amber-600 text-[10px] px-1.5 py-0.5 rounded font-bold">
                <RefreshCwIcon className="size-3 inline mr-1" />
                重试策略
              </span>
              <span className="text-[10px] text-muted-foreground">(失败时自动重试配置)</span>
            </div>
            <div className="rounded-lg border border-amber-500/10 bg-amber-500/[0.02] p-3 space-y-3">
              <label className="flex items-center justify-between gap-3 rounded-md border bg-background p-2.5 text-xs font-medium">
                失败自动重试
                <Switch
                  checked={retryPolicy.enabled}
                  onCheckedChange={(checked) =>
                    onChange({ retryPolicy: { ...retryPolicy, enabled: checked } })
                  }
                />
              </label>
              {retryPolicy.enabled && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <span className="text-[10px] text-muted-foreground">最大重试次数</span>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      value={retryPolicy.maxAttempts}
                      onChange={(e) =>
                        onChange({
                          retryPolicy: { ...retryPolicy, maxAttempts: Number(e.target.value || 1) },
                        })
                      }
                      className="h-7 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] text-muted-foreground">重试间隔 (ms)</span>
                    <Input
                      type="number"
                      min={0}
                      value={retryPolicy.intervalMs}
                      onChange={(e) =>
                        onChange({
                          retryPolicy: { ...retryPolicy, intervalMs: Number(e.target.value || 0) },
                        })
                      }
                      className="h-7 text-xs"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ═══ Import Dialog ═══ */}
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {importFormat === "headers"
                ? "贴入响应头"
                : `贴入${importFormat.toUpperCase()}响应报文样例`}
            </DialogTitle>
            <DialogDescription>
              {importFormat === "json" && '支持 // 行尾注释提取为 Description，例如: "accessToken": "xxx" // 登录令牌'}
              {importFormat === "xml" && "系统将解析 XML 结构为树状表格，支持嵌套元素和属性。"}
              {importFormat === "text" && "贴入纯文本响应样例内容。"}
              {importFormat === "headers" && "每行一个 Header，格式为 Key: Value，例如 Content-Type: application/json"}
            </DialogDescription>
          </DialogHeader>

          {/* Format selector for body import */}
          {importFormat !== "headers" && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">报文格式:</span>
              <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
                {(["json", "xml", "text"] as BodyFormat[]).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setImportFormat(f)}
                    className={cn(
                      "flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors",
                      importFormat === f
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {f === "json" && <FileJsonIcon className="size-3" />}
                    {f === "xml" && <FileCodeIcon className="size-3" />}
                    {f === "text" && <FileTextIcon className="size-3" />}
                    {f.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="py-3">
            {importFormat === "json" || importFormat === "headers" ? (
              <div className="border-input bg-muted/20 overflow-hidden rounded-md border">
                <CodeMirror
                  value={dialogInput}
                  height="300px"
                  extensions={importFormat === "json" ? jsonExtensions : []}
                  theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                  onChange={(v) => setDialogInput(v)}
                  placeholder={
                    importFormat === "headers"
                      ? "Content-Type: application/json\nX-Request-Id: abc123\nSet-Cookie: token=xyz; Path=/"
                      : '{"code": "0000", "data": { ... }}'
                  }
                />
              </div>
            ) : (
              <textarea
                className="w-full h-[300px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring resize-y"
                placeholder={
                  importFormat === "xml"
                    ? '<?xml version="1.0"?>\n<response>\n  <code>0000</code>\n</response>'
                    : "输入纯文本响应样例..."
                }
                value={dialogInput}
                onChange={(e) => setDialogInput(e.target.value)}
              />
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowImportDialog(false)}>取消</Button>
            <Button
              onClick={() => {
                if (importFormat === "headers") {
                  handleImportHeaders(dialogInput);
                  setShowImportDialog(false);
                  setDialogInput("");
                } else {
                  handleImportBody();
                }
              }}
              disabled={!dialogInput.trim()}
            >
              确定解析
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ── tab button ─────────────────────────────────────────────────── */

function TabButton({
  active,
  onClick,
  icon,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px",
        active
          ? "border-blue-600 text-blue-600"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {icon}
      {label}
      {badge > 0 && (
        <span className="ml-1 rounded-full bg-blue-500/10 text-blue-600 px-1.5 text-[9px] font-bold">
          {badge}
        </span>
      )}
    </button>
  );
}

/* ── body tree node (recursive) ─────────────────────────────────── */

function BodyTreeNode({
  field,
  flatIndex,
  depth,
  outputMapping,
  flatFields,
  onUpdateField,
  onToggleExtract,
}: {
  field: InputFieldDefinition;
  flatIndex: number;
  depth: number;
  outputMapping: Record<string, string>;
  flatFields: { label: string; name: string; path: string; type: string; depth: number }[];
  onUpdateField: (flatIndex: number, prop: "defaultValue" | "label" | "remark", value: any) => void;
  onToggleExtract: (path: string, displayName: string, checked: boolean, label?: string, remark?: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isLeaf = field.type !== "object" && field.type !== "array";
  const flatEntry = flatFields[flatIndex];
  const fieldPath = flatEntry?.path ?? "";
  const isExtracted = isLeaf && Object.values(outputMapping).some((v) => v === fieldPath);

  const typeBadge = !isLeaf
    ? field.type === "array"
      ? `array${field.children ? `[${field.children.length}]` : ""}`
      : "object"
    : field.type;

  let childFlatIndex = flatIndex + 1;

  return (
    <div>
      <div className="grid grid-cols-[32px_1fr_80px_150px_1fr] gap-2 items-center px-3 py-1.5 hover:bg-muted/20 transition-colors">
        {/* Extract checkbox */}
        <div className="flex justify-center">
          {isLeaf ? (
            <input
              type="checkbox"
              checked={isExtracted}
              onChange={(e) => {
                const baseName = fieldPath.split(".").pop()?.replace("[*]", "") ?? "field";
                onToggleExtract(fieldPath, baseName, e.target.checked, field.label ?? "", field.remark ?? "");
              }}
              className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
            />
          ) : (
            <span className="text-[9px] text-muted-foreground/50">-</span>
          )}
        </div>

        {/* Key */}
        <div className="flex items-center gap-1 min-w-0">
          {!isLeaf ? (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              className="shrink-0 p-0.5 rounded hover:bg-muted transition-colors"
            >
              {expanded ? (
                <ChevronDownIcon className="size-3 text-muted-foreground" />
              ) : (
                <ChevronRightIcon className="size-3 text-muted-foreground" />
              )}
            </button>
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <span
            className="text-[11px] font-mono font-medium truncate"
            style={{ paddingLeft: `${depth * 12}px` }}
          >
            {field.name}
          </span>
        </div>

        {/* Type */}
        <div>
          <span className="text-[9px] font-mono text-muted-foreground/70 uppercase bg-muted/50 px-1.5 py-0.5 rounded">
            {typeBadge}
          </span>
        </div>

        {/* Sample value */}
        <div>
          {isLeaf ? (
            <Input
              className="h-6 text-[10px] font-mono bg-background/50 border-border/50 px-1.5"
              value={field.defaultValue !== undefined ? String(field.defaultValue as string | number | boolean) : ""}
              placeholder="示例值"
              onChange={(e) => onUpdateField(flatIndex, "defaultValue", e.target.value)}
            />
          ) : (
            <span className="text-[10px] text-muted-foreground/50 italic">
              ({field.type === "array" ? `array[${field.children?.length ?? 0}]` : "object"})
            </span>
          )}
        </div>

        {/* Description */}
        <Input
          className="h-6 text-[10px] bg-background/50 border-border/50 px-1.5"
          value={field.label ?? ""}
          placeholder="字段说明"
          onChange={(e) => onUpdateField(flatIndex, "label", e.target.value)}
        />
      </div>

      {/* Children */}
      {!isLeaf && expanded &&
        field.children?.map((child, i) => {
          const currentFlatIndex = childFlatIndex;
          childFlatIndex += countFields(child);
          return (
            <BodyTreeNode
              key={i}
              field={child}
              flatIndex={currentFlatIndex}
              depth={depth + 1}
              outputMapping={outputMapping}
              flatFields={flatFields}
              onUpdateField={onUpdateField}
              onToggleExtract={onToggleExtract}
            />
          );
        })}
    </div>
  );
}

/* ── utilities ──────────────────────────────────────────────────── */

/** Convert bodyTree to a sample JSON object for preview */
function treeToSample(tree: InputFieldDefinition[]): Record<string, any> {
  const obj: Record<string, any> = {};
  for (const field of tree) {
    if (field.type === "object" && field.children) {
      obj[field.name] = treeToSample(field.children);
    } else if (field.type === "array" && field.children) {
      obj[field.name] = [treeToSample(field.children)];
    } else {
      const val = field.defaultValue;
      if (val === "" || val === null || val === undefined) {
        obj[field.name] = "";
      } else if (typeof val === "string" && val !== "" && !isNaN(Number(val)) && !val.includes(" ")) {
        obj[field.name] = Number(val);
      } else if (val === "true") {
        obj[field.name] = true;
      } else if (val === "false") {
        obj[field.name] = false;
      } else {
        obj[field.name] = val;
      }
    }
  }
  return obj;
}

/** Simple JSON-to-XML serializer */
function jsonToXml(obj: Record<string, any>, indent = 0): string {
  const pad = "  ".repeat(indent);
  const lines: string[] = [];
  if (indent === 0) lines.push('<?xml version="1.0" encoding="UTF-8"?>');
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      lines.push(`${pad}<${key}>`);
      lines.push(jsonToXml(value, indent + 1));
      lines.push(`${pad}</${key}>`);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === "object" && item !== null) {
          lines.push(`${pad}<${key}>`);
          lines.push(jsonToXml(item, indent + 1));
          lines.push(`${pad}</${key}>`);
        } else {
          lines.push(`${pad}<${key}>${item ?? ""}</${key}>`);
        }
      }
    } else {
      lines.push(`${pad}<${key}>${value ?? ""}</${key}>`);
    }
  }
  return lines.join("\n");
}

/** Parse XML string into InputFieldDefinition[] */
function xmlToTree(xmlStr: string): InputFieldDefinition[] {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlStr.trim(), "text/xml");
  const errorNode = doc.querySelector("parsererror");
  if (errorNode) throw new Error(errorNode.textContent ?? "XML parse error");

  function elementToField(el: Element): InputFieldDefinition {
    const children = Array.from(el.children);
    if (children.length > 0) {
      const tagNames = new Set(children.map((c) => c.tagName));
      const isArray = tagNames.size === 1 && children.length > 1;

      if (isArray) {
        return {
          name: el.tagName,
          type: "array",
          required: false,
          batchEnabled: false,
          children: [elementToField(children[0]!)],
        };
      }

      return {
        name: el.tagName,
        type: "object",
        required: false,
        batchEnabled: false,
        children: children.map(elementToField),
      };
    }

    const text = el.textContent?.trim() ?? "";
    let type: InputFieldDefinition["type"] = "string";
    if (text !== "" && !isNaN(Number(text)) && !text.includes(" ")) {
      type = "number";
    } else if (text === "true" || text === "false") {
      type = "boolean";
    }

    return {
      name: el.tagName,
      type,
      required: false,
      batchEnabled: false,
      defaultValue: text,
    };
  }

  const root = doc.documentElement;
  if (!root) return [];
  return [elementToField(root)];
}
