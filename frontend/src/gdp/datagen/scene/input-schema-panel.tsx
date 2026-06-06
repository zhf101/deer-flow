"use client";

import { json } from "@codemirror/lang-json";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import {
  CodeIcon,
  PlusIcon,
  Settings2Icon,
  Trash2Icon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useMemo, useState } from "react";
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

import { createEnvField, INPUT_FIELD_TYPES } from "../common/lib/defaults";
import type {
  InputFieldDefinition,
  InputFieldType,
  SceneDefinition,
} from "../common/lib/types";

const darkTheme = monokaiInit({
  settings: {
    background: "transparent",
    gutterBackground: "transparent",
    fontSize: "12px",
  },
});

const lightTheme = basicLightInit({
  settings: {
    background: "transparent",
    fontSize: "12px",
  },
});

interface InputSchemaPanelProps {
  scene: SceneDefinition;
  onChange: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

export function InputSchemaPanel({ scene, onChange, readOnly }: InputSchemaPanelProps) {
  const { resolvedTheme } = useTheme();
  const [showJsonDialog, setShowJsonDialog] = useState(false);
  const [jsonInput, setJsonInput] = useState("");
  const extensions = useMemo(() => [json()], []);

  const previewJson = useMemo(() => {
    const build = (fields: InputFieldDefinition[]) => {
      const obj: any = {};
      fields.forEach((f) => {
        if (f.name === "env") return;
        if (f.type === "object" && f.children) {
          obj[f.name] = build(f.children);
        } else if (f.type === "array") {
          obj[f.name] = f.children ? [build(f.children)] : [];
        } else {
          obj[f.name] = `<${f.type}>`;
        }
      });
      return obj;
    };
    return JSON.stringify(build(scene.inputSchema), null, 2);
  }, [scene.inputSchema]);

  const updateFields = (fields: InputFieldDefinition[]) => {
    onChange({ ...scene, inputSchema: fields });
  };

  const addTopLevelField = () => {
    const nextIndex = scene.inputSchema.length + 1;
    updateFields(
      scene.inputSchema.concat({
        name: `field${nextIndex}`,
        label: "",
        type: "string",
        required: false,
        batchEnabled: false,
      }),
    );
  };

  const handleJsonToSchema = () => {
    try {
      // 1. Clean JSON and extract comments mapping
      const { cleanJson, labels } = parseJsonWithComments(jsonInput);
      const parsed = JSON.parse(cleanJson);
      
      // 2. Generate fields recursively with labels
      const generated = jsonToFields(parsed, labels);
      
      // 3. Keep "env" field if exists
      const envField = scene.inputSchema.find((f) => f.name === "env") || createEnvField();
      updateFields([envField, ...generated]);
      setShowJsonDialog(false);
      setJsonInput("");
      toast.success("已根据 JSON 及注释生成参数结构");
    } catch (error) {
      console.error(error);
      toast.error("JSON 解析失败，请检查格式（支持 // 注释）");
    }
  };

  return (
    <div className={cn("space-y-4", readOnly && "pointer-events-none opacity-75")}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings2Icon className="text-muted-foreground size-4" />
          <span className="text-sm font-medium">参数结构</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowJsonDialog(true)}
            className="gap-2"
          >
            <CodeIcon className="size-4" />
            贴入 JSON 生成
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={addTopLevelField} className="gap-2">
            <PlusIcon className="size-4" />
            新增参数
          </Button>
        </div>
      </div>

      <div className="rounded-xl border bg-muted/30 p-4">
        <div className="space-y-4">
          {scene.inputSchema.map((field, index) => (
            <InputFieldTreeItem
              key={field.name + index}
              field={field}
              onUpdate={(updated) => {
                const next = [...scene.inputSchema];
                next[index] = updated;
                updateFields(next);
              }}
              onDelete={() => {
                if (field.name === "env") return;
                updateFields(scene.inputSchema.filter((_, i) => i !== index));
              }}
            />
          ))}
          {scene.inputSchema.length === 0 && (
            <div className="py-10 text-center text-muted-foreground text-sm">
              暂无参数，请手动添加或贴入 JSON 生成
            </div>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <CodeIcon className="text-muted-foreground size-4" />
          <span className="text-sm font-medium">预览最终结构</span>
        </div>
        <div className="border-input bg-card overflow-hidden rounded-md border shadow-sm">
          <CodeMirror
            value={previewJson}
            height="200px"
            extensions={extensions}
            theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
            readOnly
            basicSetup={{
              lineNumbers: true,
              foldGutter: true,
            }}
          />
        </div>
      </div>

      <Dialog open={showJsonDialog} onOpenChange={setShowJsonDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>从 JSON 生成参数结构</DialogTitle>
            <DialogDescription>
              直接贴入目标 JSON 报文，系统将自动识别嵌套关系并转换为参数结构。
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="border-input bg-muted/20 overflow-hidden rounded-md border">
              <CodeMirror
                value={jsonInput}
                height="400px"
                extensions={extensions}
                theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                onChange={(value) => setJsonInput(value)}
                placeholder='在此贴入 JSON 报文...'
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowJsonDialog(false)}>
              取消
            </Button>
            <Button onClick={handleJsonToSchema} disabled={!jsonInput.trim()}>
              生成结构
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function InputFieldTreeItem({
  field,
  onUpdate,
  onDelete,
  depth = 0,
}: {
  field: InputFieldDefinition;
  onUpdate: (field: InputFieldDefinition) => void;
  onDelete: () => void;
  depth?: number;
}) {
  const isEnv = field.name === "env";

  const addChild = () => {
    const children = field.children || [];
    onUpdate({
      ...field,
      type: field.type === "object" || field.type === "array" ? field.type : "object",
      children: [
        ...children,
        {
          name: `item${children.length + 1}`,
          label: "",
          type: "string",
          required: false,
          batchEnabled: false,
        },
      ],
    });
  };

  return (
    <div className={cn("space-y-2", depth > 0 && "ml-6 border-l pl-4")}>
      <div className="flex items-center gap-3">
        <div className="grid flex-1 grid-cols-4 gap-2">
          <Input
            value={field.name}
            disabled={isEnv}
            onChange={(e) => onUpdate({ ...field, name: e.target.value })}
            placeholder="参数编码"
            className="h-8 font-mono text-xs"
          />
          <Input
            value={field.label || ""}
            onChange={(e) => onUpdate({ ...field, label: e.target.value })}
            placeholder="中文描述"
            className="h-8 text-xs"
          />
          <Select
            value={field.type}
            onValueChange={(val) => onUpdate({ ...field, type: val as InputFieldType })}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INPUT_FIELD_TYPES.map((t) => (
                <SelectItem key={t} value={t} className="text-xs">
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-md border px-2 py-1">
              <span className="text-[10px] text-muted-foreground">必填</span>
              <Switch
                checked={field.required}
                disabled={isEnv}
                onCheckedChange={(val) => onUpdate({ ...field, required: val })}
                className="scale-75"
              />
            </div>
            {!isEnv && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onDelete}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2Icon className="size-4" />
              </Button>
            )}
          </div>
        </div>
        {(field.type === "object" || field.type === "array") && (
          <Button variant="ghost" size="icon-sm" onClick={addChild} title="添加子参数">
            <PlusIcon className="size-4" />
          </Button>
        )}
      </div>

      {field.children && field.children.length > 0 && (
        <div className="space-y-2 mt-2">
          {field.children.map((child, idx) => (
            <InputFieldTreeItem
              key={idx}
              field={child}
              depth={depth + 1}
              onUpdate={(updated) => {
                const nextChildren = [...field.children!];
                nextChildren[idx] = updated;
                onUpdate({ ...field, children: nextChildren });
              }}
              onDelete={() => {
                onUpdate({
                  ...field,
                  children: field.children!.filter((_, i) => i !== idx),
                });
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function jsonToFields(obj: any, labels: Record<string, string> = {}): InputFieldDefinition[] {
  if (typeof obj !== "object" || obj === null) return [];
  
  return Object.entries(obj).map(([key, value]) => {
    let type: InputFieldType = "string";
    let children: InputFieldDefinition[] | undefined;

    if (Array.isArray(value)) {
      type = "array";
      if (value.length > 0 && typeof value[0] === "object") {
        children = jsonToFields(value[0], labels);
      }
    } else if (typeof value === "object" && value !== null) {
      type = "object";
      children = jsonToFields(value, labels);
    } else if (typeof value === "number") {
      type = "number";
    } else if (typeof value === "boolean") {
      type = "boolean";
    }

    return {
      name: key,
      label: labels[key] || "",
      type,
      required: false,
      batchEnabled: false,
      children: children?.length ? children : undefined,
    };
  });
}

/**
 * Parses JSON with // comments and extracts them as labels.
 * This is a heuristic parser for the "paste JSON with comments" feature.
 */
function parseJsonWithComments(input: string): { cleanJson: string; labels: Record<string, string> } {
  const labels: Record<string, string> = {};
  const lines = input.split("\n");
  const cleanLines = lines.map(line => {
    // Regex to match "key": value, // comment
    // Group 1: key, Group 2: comment
    const match = /^\s*"([^"]+)"\s*:.*?\/\/\s*(.*)$/.exec(line);
    if (match) {
      const key = match[1];
      const comment = match[2]?.trim();
      if (key && comment) {
        labels[key] = comment;
      }
    }
    // Remove the comment part for standard JSON parsing
    return line.replace(/\/\/.*$/, "");
  });

  return {
    cleanJson: cleanLines.join("\n"),
    labels,
  };
}
