"use client";

import { json } from "@codemirror/lang-json";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import {
  ChevronDownIcon,
  ChevronRightIcon,
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
} from "../lib/schema-utils";
import type {
  ConditionOperator,
  HttpStepDefinition,
  InputFieldDefinition,
} from "../lib/types";
import { formatUnknownValue, isRecord } from "../lib/value-utils";
import { ConfirmDialog } from "../ui/confirm-dialog";

import {
  bodyExpression,
  cookieExpression,
  headerExpression,
  isSameMapping,
} from "./http-output-extraction-editor";

/* ── 主题 ── */

const darkTheme = monokaiInit({
  settings: { background: "transparent", gutterBackground: "transparent", fontSize: "12px" },
});
const lightTheme = basicLightInit({
  settings: { background: "transparent", fontSize: "12px" },
});

/* ── 类型 ── */

interface HttpResponseMappingEditorProps {
  step: HttpStepDefinition;
  onChange: (updates: Partial<HttpStepDefinition>) => void;
  /** 禁用所有数据输入和按钮，但保留标签切换功能。 */
  disabled?: boolean;
}

type ResponseTab = "body" | "headers" | "cookies";
type SubView = "tree" | "preview";
type BodyFormat = "json" | "xml" | "text";
type ImportFormat = BodyFormat | "headers";

interface ResponseRequestMapping extends Record<string, unknown> {
  _rawResponseSample?: string;
}

interface CookieFieldDefinition extends InputFieldDefinition {
  domain?: string;
  path?: string;
  expires?: string;
  httpOnly?: boolean;
  secure?: boolean;
}

/* ── 常见 HTTP 响应头 ── */

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

/* ── 主组件 ── */

export function HttpResponseMappingEditor({
  step,
  onChange,
  disabled = false,
}: HttpResponseMappingEditorProps) {
  const { resolvedTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<ResponseTab>("body");
  const [bodyView, setBodyView] = useState<SubView>("tree");
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importFormat, setImportFormat] = useState<ImportFormat>("json");
  const [dialogInput, setDialogInput] = useState("");
  const [pendingDelete, setPendingDelete] = useState<{ type: "header" | "cookie" | "failure" | "success"; idx?: number; key?: string } | null>(null);

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

  /* ── 响应体格式检测 ── */
  const bodyFormat: BodyFormat = useMemo(() => {
    const ct = responseHandling.expectedContentType;
    if (ct === "XML") return "xml";
    if (ct === "TEXT") return "text";
    return "json";
  }, [responseHandling.expectedContentType]);

  /* ── 展开后的字段列表 ── */
  const bodyFlatFields = useMemo(() => flattenSchema(schema, "$"), [schema]);
  const extractableBodyFields = useMemo(
    () => bodyFlatFields.filter((f) => f.type !== "object" && f.type !== "array"),
    [bodyFlatFields],
  );

  /* ── CodeMirror 扩展 ── */
  const jsonExtensions = useMemo(() => [json()], []);

  /* ── 错误映射与重试策略（第 4 部分） ── */
  const errorMapping = step.errorMapping ?? {
    messageTemplate: "",
    fields: {},
    fallbackMessage: "",
    exposeRawResponse: false,
  };
  const businessErrorMapping = step.businessErrorMapping ?? {
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

  /* ── 原始响应体文本（存入 requestMapping 用于持久化） ── */
  const rawResponseText = (step.requestMapping as ResponseRequestMapping)._rawResponseSample ?? "";

  /* ── 导入处理函数 ── */
  const handleImportBody = useCallback(() => {
    try {
      if (importFormat === "json") {
        const { cleanJson, labels } = parseJsonWithComments(dialogInput);
        const parsed = JSON.parse(cleanJson);
        const generatedSchema = jsonToFields(parsed, labels);
        const text = JSON.stringify(parsed, null, 2);
        onChange({
          responseSchema: generatedSchema,
          requestMapping: { ...step.requestMapping, _rawResponseSample: text },
        });
        toast.success("JSON 响应结构已解析");
      } else if (importFormat === "xml") {
        const tree = xmlToTree(dialogInput);
        if (tree.length === 0) throw new Error("empty");
        onChange({
          responseSchema: tree,
          requestMapping: { ...step.requestMapping, _rawResponseSample: dialogInput },
        });
        toast.success("XML 响应结构已解析");
      } else {
        // 文本格式无需解析 schema，仅保存为样例
        onChange({
          requestMapping: { ...step.requestMapping, _rawResponseSample: dialogInput },
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

  /* ── 响应体字段属性更新器 ── */
  const updateBodyFieldProp = (flatIndex: number, prop: "defaultValue" | "label" | "remark", value: unknown) => {
    const next = updateFieldPropAtPath(schema, flatIndex, prop, value);
    onChange({ responseSchema: next });
  };

  /* ── 标签徽标数量：这里只表示已定义的响应结构数量，抽取数量在独立区域展示。 ── */
  const bodyFieldCount = useMemo(
    () => schema.reduce((total, field) => total + countFields(field), 0),
    [schema],
  );
  const headersFieldCount = headersSchema.length;
  const cookiesFieldCount = cookiesSchema.length;

  /* ── 用于预览的 treeToJson ── */
  const previewText = useMemo(() => {
    if (bodyFormat === "text") return rawResponseText;
    if (schema.length === 0) return rawResponseText;
    const obj = treeToSample(schema);
    if (bodyFormat === "xml") return jsonToXml(obj);
    return JSON.stringify(obj, null, 2);
  }, [schema, bodyFormat, rawResponseText]);

  return (
    <div className="space-y-4">
      {/* ── 第 1 部分：响应标签页 ── */}
      <section className="space-y-2">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-blue-600 font-bold text-sm">
            <FileJsonIcon className="size-4" />
            <span>响应报文定义</span>
          </div>
        </div>

        {/* 标签栏 */}
        <div className="flex items-center gap-1 border-b border-border/40">
          <TabButton
            active={activeTab === "body"}
            onClick={() => setActiveTab("body")}
            icon={<CodeIcon className="size-3.5" />}
            label="Body"
            badge={bodyFieldCount}
          />
          <TabButton
            active={activeTab === "headers"}
            onClick={() => setActiveTab("headers")}
            icon={<FileTextIcon className="size-3.5" />}
            label="Headers"
            badge={headersFieldCount}
          />
          <TabButton
            active={activeTab === "cookies"}
            onClick={() => setActiveTab("cookies")}
            icon={<CookieIcon className="size-3.5" />}
            label="Cookies"
            badge={cookiesFieldCount}
          />
        </div>

        {/* ── 响应体标签页 ── */}
        {activeTab === "body" && (
          <div className="space-y-2">
            {/* 工具栏：视图切换、格式选择与导入 */}
            <div className="flex items-center gap-2">
              {/* 视图模式切换在只读模式下仍可交互 */}
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

              {/* 内容类型选择器与导入按钮在只读模式下禁用 */}
              <div className={cn("flex items-center gap-2", disabled && "pointer-events-none opacity-50")}>

              {/* 内容类型选择器 */}
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
            </div>

            {/* 树形视图 */}
            {bodyView === "tree" && (
              <div className={cn("rounded-lg border bg-card overflow-hidden", disabled && "pointer-events-none opacity-50")}>
                <div className="grid grid-cols-[1fr_80px_150px_1fr] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
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
                        onUpdateField={updateBodyFieldProp}
                      />
                    ))
                  )}
                </div>
              </div>
            )}

            {/* 预览视图（只读格式化） */}
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

        {/* ── 响应头标签页 ── */}
        {activeTab === "headers" && (
          <div className={cn("space-y-2", disabled && "pointer-events-none opacity-50")}>
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
              <div className="grid grid-cols-[1fr_1fr_1fr_32px] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
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
                  headersSchema.map((header, idx) => (
                    <div key={idx} className="grid grid-cols-[1fr_1fr_1fr_32px] gap-2 items-center px-3 py-1.5 hover:bg-muted/20 transition-colors">
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
                        onClick={() => setPendingDelete({ type: "header", idx })}
                        className="text-muted-foreground hover:text-destructive h-6 w-6"
                      >
                        <Trash2Icon className="size-3" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Cookie 标签页 ── */}
        {activeTab === "cookies" && (
          <div className={cn("space-y-2", disabled && "pointer-events-none opacity-50")}>
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
              <div className="grid grid-cols-[1fr_1fr_100px_80px_100px_56px_56px_32px] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
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
                  cookiesSchema.map((cookie, idx) => (
                    <div key={idx} className="grid grid-cols-[1fr_1fr_100px_80px_100px_56px_56px_32px] gap-2 items-center px-3 py-1.5 hover:bg-muted/20 transition-colors">
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
                        value={(cookie as CookieFieldDefinition).domain ?? ""}
                        onChange={(e) => {
                          const next = [...cookiesSchema];
                          next[idx] = { ...cookie, domain: e.target.value } as CookieFieldDefinition;
                          onChange({ responseCookiesSchema: next });
                        }}
                        placeholder=".example.com"
                        className="h-7 text-[10px] font-mono"
                      />
                      <Input
                        value={(cookie as CookieFieldDefinition).path ?? "/"}
                        onChange={(e) => {
                          const next = [...cookiesSchema];
                          next[idx] = { ...cookie, path: e.target.value } as CookieFieldDefinition;
                          onChange({ responseCookiesSchema: next });
                        }}
                        placeholder="/"
                        className="h-7 text-[10px] font-mono"
                      />
                      <Input
                        value={(cookie as CookieFieldDefinition).expires ?? ""}
                        onChange={(e) => {
                          const next = [...cookiesSchema];
                          next[idx] = { ...cookie, expires: e.target.value } as CookieFieldDefinition;
                          onChange({ responseCookiesSchema: next });
                        }}
                        placeholder="Session"
                        className="h-7 text-[10px] font-mono"
                      />
                      <div className="flex justify-center">
                        <input
                          type="checkbox"
                          checked={(cookie as CookieFieldDefinition).httpOnly === true}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, httpOnly: e.target.checked } as CookieFieldDefinition;
                            onChange({ responseCookiesSchema: next });
                          }}
                          className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                        />
                      </div>
                      <div className="flex justify-center">
                        <input
                          type="checkbox"
                          checked={(cookie as CookieFieldDefinition).secure === true}
                          onChange={(e) => {
                            const next = [...cookiesSchema];
                            next[idx] = { ...cookie, secure: e.target.checked } as CookieFieldDefinition;
                            onChange({ responseCookiesSchema: next });
                          }}
                          className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                        />
                      </div>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setPendingDelete({ type: "cookie", idx })}
                        className="text-muted-foreground hover:text-destructive h-6 w-6"
                      >
                        <Trash2Icon className="size-3" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── 第 2 部分：业务规则 ── */}
      <section className="space-y-3">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-green-600 font-bold text-sm">
            <ShieldCheckIcon className="size-4" />
            <span>业务结果判定规则</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          当 HTTP 状态码为 2xx 时，根据响应报文中的特定字段判定业务是否成功。例如：返回 code === &quot;0000&quot; 表示业务成功，code === &quot;9999&quot; 表示业务失败。
        </p>
        <div className={cn("space-y-4", disabled && "pointer-events-none opacity-50")}>
          {/* 失败规则 */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-destructive/10 text-destructive text-[10px] px-1.5 py-0.5 rounded font-bold">优先判定为失败</span>
              <span className="text-[10px] text-muted-foreground">(任意一条规则命中即判定为业务失败，短路判断)</span>
            </div>
            <div className="rounded-lg border border-destructive/10 bg-destructive/[0.02] p-1.5 space-y-1.5">
              {failureRules.map((rule, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-background p-1.5 rounded border border-destructive/20">
                  <Select
                    value={rule.path}
                    onValueChange={(val) => {
                      const next = [...failureRules];
                      const current = next[idx]!;
                      next[idx] = { path: val, op: current.op ?? "EQ", value: current.value ?? "" };
                      onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                    }}
                  >
                    <SelectTrigger className="h-7 text-[10px] flex-1 border-none shadow-none font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {extractableBodyFields.map((f) => (
                        <SelectItem key={f.path} value={bodyExpression(f.path)} className="text-xs">{f.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={rule.op}
                    onValueChange={(val: ConditionOperator) => {
                      const next = [...failureRules];
                      const current = next[idx]!;
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
                        const current = next[idx]!;
                        next[idx] = { path: current.path ?? "", op: current.op ?? "EQ", value: e.target.value };
                        onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                      }}
                    />
                  )}
                  <Button variant="ghost" size="sm" className="h-6 w-6" onClick={() => setPendingDelete({ type: "failure", idx })}>
                    <Trash2Icon className="size-3" />
                  </Button>
                </div>
              ))}
              <Button variant="ghost" size="sm" className="w-full h-8 text-[10px] border border-dashed text-destructive border-destructive/20 hover:bg-destructive/5" onClick={() => {
                const firstPath = extractableBodyFields[0]?.path;
                const next = [...failureRules, { path: firstPath ? bodyExpression(firstPath) : "", op: "EQ" as ConditionOperator, value: "" }];
                onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
              }}>
                <PlusIcon className="mr-1 size-3" />
                添加失败判定规则 (OR)
              </Button>
            </div>
          </div>

          {/* 成功规则 */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-green-500/10 text-green-600 text-[10px] px-1.5 py-0.5 rounded font-bold">满足条件判定为成功</span>
              <span className="text-[10px] text-muted-foreground">(需全部规则同时命中才判定为业务成功)</span>
            </div>
            <div className="rounded-lg border border-green-500/10 bg-green-500/[0.02] p-1.5 space-y-1.5">
              {successRules.map((rule, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-background p-1.5 rounded border border-green-500/20">
                  <Select
                    value={rule.path}
                    onValueChange={(val) => {
                      const next = [...successRules];
                      const current = next[idx]!;
                      next[idx] = { path: val, op: current.op ?? "EQ", value: current.value ?? "" };
                      onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                    }}
                  >
                    <SelectTrigger className="h-7 text-[10px] flex-1 border-none shadow-none font-mono">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {extractableBodyFields.map((f) => (
                        <SelectItem key={f.path} value={bodyExpression(f.path)} className="text-xs">{f.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={rule.op}
                    onValueChange={(val: ConditionOperator) => {
                      const next = [...successRules];
                      const current = next[idx]!;
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
                        const current = next[idx]!;
                        next[idx] = { path: current.path ?? "", op: current.op ?? "EQ", value: e.target.value };
                        onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                      }}
                    />
                  )}
                  <Button variant="ghost" size="sm" className="h-6 w-6" onClick={() => setPendingDelete({ type: "success", idx })}>
                    <Trash2Icon className="size-3" />
                  </Button>
                </div>
              ))}
              <Button variant="ghost" size="sm" className="w-full h-8 text-[10px] border border-dashed text-green-600 border-green-500/20 hover:bg-green-500/5" onClick={() => {
                const firstPath = extractableBodyFields[0]?.path;
                const next = [...successRules, { path: firstPath ? bodyExpression(firstPath) : "", op: "EQ" as ConditionOperator, value: "" }];
                onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
              }}>
                <PlusIcon className="mr-1 size-3" />
                添加成功判定规则 (AND)
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ── 第 4 部分：错误处理与重试 ── */}
      <section className="space-y-3">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-orange-600 font-bold text-sm">
            <ShieldAlertIcon className="size-4" />
            <span>请求异常与重试策略</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          当请求未返回预期结果时（如 HTTP 状态码为 404、403、502 或网络不可达），定义异常处理方式和自动重试策略。
        </p>
        <div className={cn("space-y-4", disabled && "pointer-events-none opacity-50")}>
          {/* 业务错误映射 */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-rose-500/10 text-rose-600 text-[10px] px-1.5 py-0.5 rounded font-bold">业务异常响应</span>
              <span className="text-[10px] text-muted-foreground">(已收到响应但状态码或业务规则判定失败时使用)</span>
            </div>
            <div className="rounded-lg border border-rose-500/10 bg-rose-500/[0.02] p-3 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <span className="text-[10px] text-muted-foreground">业务错误消息模板</span>
                  <Input
                    value={businessErrorMapping.messageTemplate ?? ""}
                    onChange={(e) =>
                      onChange({
                        businessErrorMapping: { ...businessErrorMapping, messageTemplate: e.target.value },
                      })
                    }
                    placeholder="如: 创建失败：${RES_BODY(message)}"
                    className="h-7 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <span className="text-[10px] text-muted-foreground">兜底业务错误消息</span>
                  <Input
                    value={businessErrorMapping.fallbackMessage ?? ""}
                    onChange={(e) =>
                      onChange({
                        businessErrorMapping: { ...businessErrorMapping, fallbackMessage: e.target.value },
                      })
                    }
                    placeholder="业务处理失败"
                    className="h-7 text-xs"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Switch
                  checked={businessErrorMapping.exposeRawResponse}
                  onCheckedChange={(checked) =>
                    onChange({
                      businessErrorMapping: { ...businessErrorMapping, exposeRawResponse: checked },
                    })
                  }
                />
                暴露原始响应体给调用方
              </label>
            </div>
          </div>

          {/* 错误映射 */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-orange-500/10 text-orange-600 text-[10px] px-1.5 py-0.5 rounded font-bold">网络/传输异常</span>
              <span className="text-[10px] text-muted-foreground">(请求未收到响应时使用，如网络超时、连接失败、DNS 异常)</span>
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
                    placeholder="如: 请求失败：${REQ_HEADER(X-Request-Id)}"
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

          {/* 重试策略 */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 px-1">
              <span className="bg-amber-500/10 text-amber-600 text-[10px] px-1.5 py-0.5 rounded font-bold">
                <RefreshCwIcon className="size-3 inline mr-1" />
                自动重试策略
              </span>
              <span className="text-[10px] text-muted-foreground">(当请求异常发生时，可配置自动重试：设置最大重试次数和每次重试的等待间隔)</span>
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

      {/* ── 导入对话框 ── */}
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

          {/* 响应体导入格式选择器 */}
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

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => { if (!open) setPendingDelete(null); }}
        onConfirm={() => {
          if (!pendingDelete) return;
          const { type, idx } = pendingDelete;
          if (type === "header" && idx != null) {
            const headerPath = headerExpression(headersSchema[idx]?.name ?? `${idx}`);
            const next = headersSchema.filter((_, i) => i !== idx);
            const nextMapping = { ...outputMapping };
            const nextMeta = { ...(step.outputMeta ?? {}) };
            Object.entries(nextMapping).forEach(([k, v]) => {
              if (isSameMapping(v, headerPath)) { delete nextMapping[k]; delete nextMeta[k]; }
            });
            onChange({ responseHeadersSchema: next, outputMapping: nextMapping, outputMeta: nextMeta });
          } else if (type === "cookie" && idx != null) {
            const cookiePath = cookieExpression(cookiesSchema[idx]?.name ?? `${idx}`);
            const next = cookiesSchema.filter((_, i) => i !== idx);
            const nextMapping = { ...outputMapping };
            const nextMeta = { ...(step.outputMeta ?? {}) };
            Object.entries(nextMapping).forEach(([k, v]) => {
              if (isSameMapping(v, cookiePath)) { delete nextMapping[k]; delete nextMeta[k]; }
            });
            onChange({ responseCookiesSchema: next, outputMapping: nextMapping, outputMeta: nextMeta });
          } else if (type === "failure" && idx != null) {
            const next = failureRules.filter((_, i) => i !== idx);
            onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
          } else if (type === "success" && idx != null) {
            const next = successRules.filter((_, i) => i !== idx);
            onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
          }
        }}
        title={
          pendingDelete?.type === "header" || pendingDelete?.type === "cookie" ? "删除字段" :
          "删除规则"
        }
        description={
          pendingDelete?.type === "failure" || pendingDelete?.type === "success"
            ? "确定删除该业务规则吗？"
            : "确定删除该字段吗？已配置的变量提取映射也会同步清理。"
        }
      />
    </div>
  );
}

/* ── 标签按钮 ── */

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

/* ── 响应体树节点（递归） ── */

function BodyTreeNode({
  field,
  flatIndex,
  depth,
  onUpdateField,
}: {
  field: InputFieldDefinition;
  flatIndex: number;
  depth: number;
  onUpdateField: (
    flatIndex: number,
    prop: "defaultValue" | "label" | "remark",
    value: unknown,
  ) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isLeaf = field.type !== "object" && field.type !== "array";

  const typeBadge = !isLeaf
    ? field.type === "array"
      ? `array${field.children ? `[${field.children.length}]` : ""}`
      : "object"
    : field.type;

  let childFlatIndex = flatIndex + 1;

  return (
    <div>
      <div className="grid grid-cols-[1fr_80px_150px_1fr] gap-2 items-center px-3 py-1.5 hover:bg-muted/20 transition-colors">
        {/* 键 */}
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

        {/* 类型 */}
        <div>
          <span className="text-[9px] font-mono text-muted-foreground/70 uppercase bg-muted/50 px-1.5 py-0.5 rounded">
            {typeBadge}
          </span>
        </div>

        {/* 样例值 */}
        <div>
          {isLeaf ? (
            <Input
              className="h-6 text-[10px] font-mono bg-background/50 border-border/50 px-1.5"
              value={formatUnknownValue(field.defaultValue)}
              placeholder="示例值"
              onChange={(e) => onUpdateField(flatIndex, "defaultValue", e.target.value)}
            />
          ) : (
            <span className="text-[10px] text-muted-foreground/50 italic">
              ({field.type === "array" ? `array[${field.children?.length ?? 0}]` : "object"})
            </span>
          )}
        </div>

        {/* 描述 */}
        <Input
          className="h-6 text-[10px] bg-background/50 border-border/50 px-1.5"
          value={field.label ?? ""}
          placeholder="字段说明"
          onChange={(e) => onUpdateField(flatIndex, "label", e.target.value)}
        />
      </div>

      {/* 子节点 */}
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
              onUpdateField={onUpdateField}
            />
          );
        })}
    </div>
  );
}

/* ── 工具函数 ── */

/** 将 bodyTree 转为用于预览的样例 JSON 对象 */
function treeToSample(tree: InputFieldDefinition[]): Record<string, unknown> {
  const obj: Record<string, unknown> = {};
  for (const field of tree) {
    if (field.type === "object" && field.children) {
      obj[field.name] = treeToSample(field.children);
    } else if (field.type === "array" && field.children) {
      obj[field.name] = [treeToSample(field.children)];
    } else {
      const val = field.defaultValue;
      if (val === "" || val === null || val === undefined) {
        obj[field.name] = "";
      } else if (
        typeof val === "string" &&
        val !== "" &&
        !isNaN(Number(val)) &&
        !val.includes(" ")
      ) {
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

/** 简单的 JSON 转 XML 序列化器 */
function jsonToXml(obj: Record<string, unknown>, indent = 0): string {
  const pad = "  ".repeat(indent);
  const lines: string[] = [];
  if (indent === 0) lines.push('<?xml version="1.0" encoding="UTF-8"?>');
  for (const [key, value] of Object.entries(obj)) {
    if (isRecord(value)) {
      lines.push(`${pad}<${key}>`);
      lines.push(jsonToXml(value, indent + 1));
      lines.push(`${pad}</${key}>`);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        if (isRecord(item)) {
          lines.push(`${pad}<${key}>`);
          lines.push(jsonToXml(item, indent + 1));
          lines.push(`${pad}</${key}>`);
        } else {
          lines.push(`${pad}<${key}>${formatUnknownValue(item)}</${key}>`);
        }
      }
    } else {
      lines.push(`${pad}<${key}>${formatUnknownValue(value)}</${key}>`);
    }
  }
  return lines.join("\n");
}

/** 将 XML 字符串解析为 InputFieldDefinition[] */
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
