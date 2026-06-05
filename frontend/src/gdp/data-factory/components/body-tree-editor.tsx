"use client";

import { json } from "@codemirror/lang-json";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import {
  ChevronDownIcon,
  ChevronRightIcon,
  CodeIcon,
  EyeIcon,
  FileCodeIcon,
  FileJsonIcon,
  PaperclipIcon,
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import type { InputFieldDefinition, SceneDefinition } from "../lib/types";
import { isVariableRef, resolveVariableLabel } from "../lib/variable-utils";
import { parseJsonWithComments, jsonToFields } from "../lib/schema-utils";
import { VariableSelector } from "./variable-selector";

/* ── themes ─────────────────────────────────────────────────────── */

const darkTheme = monokaiInit({
  settings: { background: "transparent", gutterBackground: "transparent", fontSize: "12px" },
});
const lightTheme = basicLightInit({
  settings: { background: "transparent", fontSize: "12px" },
});

/* ── types ──────────────────────────────────────────────────────── */

interface BodyTreeEditorProps {
  format: "json" | "xml";
  scene: SceneDefinition;
  step: { stepId: string; requestMapping: Record<string, unknown> };
  onChange: (requestMapping: Record<string, unknown>) => void;
}

type SubView = "tree" | "raw" | "preview";

/* ── main component ─────────────────────────────────────────────── */

export function BodyTreeEditor({
  format,
  scene,
  step,
  onChange,
}: BodyTreeEditorProps) {
  const { resolvedTheme } = useTheme();
  const rm = step.requestMapping;

  const bodyTree: InputFieldDefinition[] = (rm as any).bodyTree ?? [];
  const bodyView: SubView = ((rm as any).bodyView as SubView) ?? "tree";
  const rawBodyText = (rm as any).rawBody ?? "";

  const [showJsonDialog, setShowJsonDialog] = useState(false);
  const [showXmlDialog, setShowXmlDialog] = useState(false);
  const [dialogInput, setDialogInput] = useState("");

  const cmExtensions = useMemo(() => [json()], []);

  /* ── view switch ──────────────────────────────────────────────── */
  const switchView = useCallback(
    (next: SubView) => {
      if (next === "raw" && bodyTree.length > 0) {
        const obj = treeToJson(bodyTree);
        const text = format === "xml" ? jsonToXml(obj) : JSON.stringify(obj, null, 2);
        onChange({ ...rm, bodyView: next, rawBody: text });
      } else if (next === "preview" && bodyTree.length > 0) {
        const obj = treeToJson(bodyTree);
        const text = format === "xml" ? jsonToXml(obj) : JSON.stringify(obj, null, 2);
        onChange({ ...rm, bodyView: next, rawBody: text });
      } else {
        onChange({ ...rm, bodyView: next });
      }
    },
    [bodyTree, format, rm, onChange],
  );

  /* ── tree update ──────────────────────────────────────────────── */
  const updateTree = useCallback(
    (next: InputFieldDefinition[]) => {
      onChange({ ...rm, bodyTree: next });
    },
    [rm, onChange],
  );

  /* ── import JSON ──────────────────────────────────────────────── */
  const handleImportJson = useCallback(() => {
    try {
      const { cleanJson, labels } = parseJsonWithComments(dialogInput);
      const parsed = JSON.parse(cleanJson);
      const tree = jsonToFields(parsed, labels);
      const text = JSON.stringify(parsed, null, 2);
      onChange({ ...rm, bodyTree: tree, rawBody: text, bodyView: "tree" });
      setShowJsonDialog(false);
      setDialogInput("");
      toast.success("JSON 报文已解析为树状结构");
    } catch {
      toast.error("JSON 解析失败，请检查格式");
    }
  }, [dialogInput, rm, onChange]);

  /* ── import XML ───────────────────────────────────────────────── */
  const handleImportXml = useCallback(() => {
    try {
      const tree = xmlToTree(dialogInput);
      if (tree.length === 0) throw new Error("empty");
      onChange({ ...rm, bodyTree: tree, rawBody: dialogInput, bodyView: "tree" });
      setShowXmlDialog(false);
      setDialogInput("");
      toast.success("XML 报文已解析为树状结构");
    } catch {
      toast.error("XML 解析失败，请检查格式");
    }
  }, [dialogInput, rm, onChange]);

  /* ── raw text update ──────────────────────────────────────────── */
  const updateRawBody = useCallback(
    (text: string) => {
      onChange({ ...rm, rawBody: text });
    },
    [rm, onChange],
  );

  /* ── generate preview text ────────────────────────────────────── */
  const previewText = useMemo(() => {
    if (bodyTree.length === 0) return "";
    const obj = treeToJson(bodyTree);
    return format === "xml" ? jsonToXml(obj) : JSON.stringify(obj, null, 2);
  }, [bodyTree, format]);

  return (
    <div className="space-y-2">
      {/* ── toolbar: 3-mode toggle + import buttons ── */}
      <div className="flex items-center gap-2">
        <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
          <button
            type="button"
            onClick={() => switchView("tree")}
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
            onClick={() => switchView("raw")}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] font-medium transition-colors",
              bodyView === "raw"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <CodeIcon className="size-3" />
            Raw
          </button>
          <button
            type="button"
            onClick={() => switchView("preview")}
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

        <div className="ml-auto flex items-center gap-1.5">
          {format === "json" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowJsonDialog(true)}
              className="gap-1.5 h-7 text-[10px]"
            >
              <FileJsonIcon className="size-3" />
              贴入 JSON
            </Button>
          )}
          {format === "xml" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowXmlDialog(true)}
              className="gap-1.5 h-7 text-[10px]"
            >
              <FileCodeIcon className="size-3" />
              贴入 XML
            </Button>
          )}
        </div>
      </div>

      {/* ── tree view ── */}
      {bodyView === "tree" && (
        <div className="rounded-md border bg-card overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_1fr_1fr] gap-2 px-3 py-1.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
            <div>Key</div>
            <div className="text-blue-600">Value</div>
            <div>Description</div>
          </div>

          {bodyTree.length === 0 ? (
            <div className="py-8 text-center text-[10px] text-muted-foreground italic">
              暂无结构定义，点击&ldquo;贴入 {format.toUpperCase()}&rdquo; 导入报文样例
            </div>
          ) : (
            <div className="max-h-[400px] overflow-auto">
              {bodyTree.map((field, idx) => (
                <TreeNode
                  key={idx}
                  field={field}
                  depth={0}
                  scene={scene}
                  currentStepId={step.stepId}
                  onUpdate={(updated) => {
                    const next = [...bodyTree];
                    next[idx] = updated;
                    updateTree(next);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── raw editable ── */}
      {bodyView === "raw" && (
        <div className="space-y-1">
          <span className="text-[10px] text-muted-foreground">
            {format === "json"
              ? "Content-Type: application/json · 支持 // 注释和 /* 块注释 */（发送时自动剥离）"
              : "Content-Type: application/xml"}
          </span>
          {format === "json" ? (
            <div className="json-raw-cm rounded-md border border-input overflow-hidden">
              <style>{`
                .json-raw-cm .cm-property { color: #64748b !important; }
                .json-raw-cm .cm-string { color: #2563eb !important; }
                .json-raw-cm .cm-number { color: #2563eb !important; }
                .json-raw-cm .cm-bool { color: #2563eb !important; }
                .json-raw-cm .cm-null { color: #2563eb !important; }
              `}</style>
              <CodeMirror
                value={rawBodyText || "{\n  \n}"}
                height="260px"
                extensions={cmExtensions}
                theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                onChange={updateRawBody}
              />
            </div>
          ) : (
            <textarea
              value={rawBodyText}
              onChange={(e) => updateRawBody(e.target.value)}
              placeholder={'<?xml version="1.0"?>\n<root>\n  <field>value</field>\n</root>'}
              className="w-full h-[260px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring resize-y"
            />
          )}
        </div>
      )}

      {/* ── preview (read-only) ── */}
      {bodyView === "preview" && (
        <div className="space-y-1">
          <span className="text-[10px] text-muted-foreground">
            {format === "json"
              ? "Content-Type: application/json · 只读预览（变量引用保持原样显示）"
              : "Content-Type: application/xml · 只读预览"}
          </span>
          {format === "json" ? (
            <div className="json-preview-cm rounded-md border border-input overflow-hidden opacity-90">
              <style>{`
                .json-preview-cm .cm-property { color: #64748b !important; }
                .json-preview-cm .cm-string { color: #2563eb !important; }
                .json-preview-cm .cm-number { color: #2563eb !important; }
                .json-preview-cm .cm-bool { color: #2563eb !important; }
                .json-preview-cm .cm-null { color: #2563eb !important; }
                .json-preview-cm .cm-content { cursor: default !important; }
              `}</style>
              <CodeMirror
                value={previewText || "{\n  \n}"}
                height="260px"
                extensions={cmExtensions}
                theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                editable={false}
                readOnly={true}
              />
            </div>
          ) : (
            <textarea
              value={previewText}
              readOnly
              className="w-full h-[260px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none resize-y cursor-default opacity-90"
            />
          )}
        </div>
      )}

      {/* ── JSON import dialog ── */}
      <Dialog open={showJsonDialog} onOpenChange={setShowJsonDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>贴入 JSON 报文</DialogTitle>
            <DialogDescription>
              支持 // 行注释，注释内容将自动提取为字段的 Description。例如: &quot;userId&quot;: &quot;abc&quot; // 用户ID
            </DialogDescription>
          </DialogHeader>
          <div className="py-3">
            <div className="border-input bg-muted/20 overflow-hidden rounded-md border">
              <CodeMirror
                value={dialogInput}
                height="300px"
                extensions={cmExtensions}
                theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                onChange={(v) => setDialogInput(v)}
                placeholder='在此贴入 JSON 报文...'
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowJsonDialog(false)}>取消</Button>
            <Button onClick={handleImportJson} disabled={!dialogInput.trim()}>解析并导入</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── XML import dialog ── */}
      <Dialog open={showXmlDialog} onOpenChange={setShowXmlDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>贴入 XML 报文</DialogTitle>
            <DialogDescription>
              系统将解析 XML 结构为树状表格，支持嵌套元素和属性。
            </DialogDescription>
          </DialogHeader>
          <div className="py-3">
            <textarea
              className="w-full h-[300px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring resize-y"
              value={dialogInput}
              onChange={(e) => setDialogInput(e.target.value)}
              placeholder='<?xml version="1.0"?>\n<request>\n  <userId>abc</userId>\n</request>'
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowXmlDialog(false)}>取消</Button>
            <Button onClick={handleImportXml} disabled={!dialogInput.trim()}>解析并导入</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ── tree node (recursive) ─────────────────────────────────────── */

function TreeNode({
  field,
  depth,
  scene,
  currentStepId,
  onUpdate,
}: {
  field: InputFieldDefinition;
  depth: number;
  scene: SceneDefinition;
  currentStepId: string;
  onUpdate: (updated: InputFieldDefinition) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = field.type === "object" || field.type === "array";
  const isLeaf = !hasChildren;

  const rawVal = typeof field.defaultValue === "string" ? field.defaultValue : String(field.defaultValue ?? "");
  const isVar = rawVal && isVariableRef(rawVal);
  const displayVal = isVar
    ? resolveVariableLabel(rawVal, scene, currentStepId)
    : rawVal;

  const typeBadge = hasChildren
    ? field.type === "array"
      ? `array${field.children ? `[${field.children.length}]` : ""}`
      : "object"
    : field.type;

  return (
    <div>
      <div
        className={cn(
          "grid grid-cols-[1fr_1fr_1fr] gap-2 items-center px-3 py-1.5 border-b border-border/30 hover:bg-muted/20 transition-colors",
        )}
      >
        {/* Key column */}
        <div className="flex items-center gap-1 min-w-0">
          {hasChildren ? (
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
          <span className="text-[8px] text-muted-foreground/60 bg-muted/50 px-1 py-0.5 rounded shrink-0 uppercase">
            {typeBadge}
          </span>
        </div>

        {/* Value column (blue highlight) */}
        {isLeaf ? (
          <div className="relative group">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Input
                    value={displayVal}
                    onChange={(e) =>
                      onUpdate({ ...field, defaultValue: e.target.value })
                    }
                    placeholder="值或 ${...}"
                    className={cn(
                      "h-7 pr-7 text-[10px]",
                      isVar && "bg-blue-50/50 text-blue-700 font-medium dark:bg-blue-950/30 dark:text-blue-300",
                      !isVar && "font-mono",
                    )}
                    readOnly={!!isVar}
                  />
                </TooltipTrigger>
                {isVar && (
                  <TooltipContent side="top" className="max-w-xs">
                    <p className="font-mono text-[10px]">{rawVal}</p>
                  </TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
            <div className="absolute right-0.5 top-1/2 -translate-y-1/2">
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="icon-sm" className="h-5 w-5">
                    <PaperclipIcon className="size-3 text-primary" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[300px] p-0" align="end">
                  <VariableSelector
                    scene={scene}
                    currentStepId={currentStepId}
                    onSelect={(v) => onUpdate({ ...field, defaultValue: v })}
                  />
                </PopoverContent>
              </Popover>
            </div>
          </div>
        ) : (
          <span className="text-[10px] text-muted-foreground/50 italic pl-2">
            ({field.type === "array" ? `array[${field.children?.length ?? 0}]` : "object"})
          </span>
        )}

        {/* Description column */}
        <Input
          value={field.label ?? ""}
          onChange={(e) => onUpdate({ ...field, label: e.target.value })}
          placeholder="字段说明"
          className="h-7 text-[10px]"
        />
      </div>

      {/* Children */}
      {hasChildren && expanded && field.children?.map((child, i) => (
        <TreeNode
          key={i}
          field={child}
          depth={depth + 1}
          scene={scene}
          currentStepId={currentStepId}
          onUpdate={(updated) => {
            const nextChildren = [...(field.children || [])];
            nextChildren[i] = updated;
            onUpdate({ ...field, children: nextChildren });
          }}
        />
      ))}
    </div>
  );
}

/* ── utilities ──────────────────────────────────────────────────── */

/** Convert bodyTree (InputFieldDefinition[]) back to a plain JSON object */
function treeToJson(tree: InputFieldDefinition[]): Record<string, any> {
  const obj: Record<string, any> = {};
  for (const field of tree) {
    if (field.type === "object" && field.children) {
      obj[field.name] = treeToJson(field.children);
    } else if (field.type === "array" && field.children) {
      obj[field.name] = [treeToJson(field.children)];
    } else {
      const val = field.defaultValue;
      if (val === "" || val === null || val === undefined) {
        obj[field.name] = "";
      } else if (typeof val === "string" && isVariableRef(val)) {
        obj[field.name] = val;
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

/** Simple JSON-to-XML serializer (for preview when format is xml) */
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
  if (errorNode) throw new Error(errorNode.textContent || "XML parse error");

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
