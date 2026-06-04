"use client";

import { json } from "@codemirror/lang-json";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import { CodeIcon } from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { FieldMapper } from "./field-mapper";
import { JsonEditor } from "./json-editor";
import { HttpBodyTreeEditor } from "./http-body-tree-editor";
import type { InputFieldDefinition, InputFieldType, SceneDefinition, StepDefinition } from "../lib/types";

interface HttpRequestMappingEditorProps {
  scene: SceneDefinition;
  step: StepDefinition;
  onChange: (updates: Partial<StepDefinition>) => void;
}

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

export function HttpRequestMappingEditor({
  scene,
  step,
  onChange,
}: HttpRequestMappingEditorProps) {
  const { resolvedTheme } = useTheme();
  const value = step.requestMapping || {};
  const [activeTab, setActiveTab] = useState<"headers" | "query" | "body">("body");
  const [showJsonBodyDialog, setShowJsonBodyDialog] = useState(false);
  const [rawJsonInput, setRawJsonBodyInput] = useState("");
  const extensions = useMemo(() => [json()], []);

  const updateSection = (section: string, sectionValue: any) => {
    onChange({ requestMapping: { ...value, [section]: sectionValue } });
  };

  const handleImportJson = () => {
    try {
      const { cleanJson, labels } = parseJsonWithComments(rawJsonInput);
      const parsed = JSON.parse(cleanJson);
      
      const generatedSchema = jsonToFields(parsed, labels);
      
      onChange({
          bodySchema: generatedSchema,
          bodyMapping: {}, 
          requestMapping: { ...value, body: parsed } 
      });
      
      setShowJsonBodyDialog(false);
      setRawJsonBodyInput("");
      toast.success("报文结构及注释已解析");
    } catch (e) {
      toast.error("JSON 解析失败，请检查格式（支持 // 注释）");
    }
  };

  return (
    <div className="space-y-4">
      <Tabs value={activeTab} onValueChange={(v: any) => setActiveTab(v)}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="headers" className="text-xs">Headers</TabsTrigger>
          <TabsTrigger value="query" className="text-xs">Query</TabsTrigger>
          <TabsTrigger value="body" className="text-xs">Body (JSON)</TabsTrigger>
        </TabsList>

        <TabsContent value="headers" className="mt-4 space-y-4">
          <FieldMapper
            label="请求头 (Headers)"
            description="配置 HTTP Header, 如 Content-Type, Authorization 等"
            value={value.headers || {}}
            onChange={(v) => updateSection("headers", v)}
            scene={scene}
            currentStepId={step.stepId}
            placeholder="Header Key"
          />
        </TabsContent>

        <TabsContent value="query" className="mt-4 space-y-4">
          <FieldMapper
            label="查询参数 (Query)"
            description="URL 问号后面的参数, 如 ?id=1&name=test"
            value={value.query || {}}
            onChange={(v) => updateSection("query", v)}
            scene={scene}
            currentStepId={step.stepId}
            placeholder="Param Key"
          />
        </TabsContent>

        <TabsContent value="body" className="mt-4 space-y-4">
          <div className="flex items-center justify-between mb-2">
            <div className="space-y-0.5">
                <span className="text-xs font-semibold text-muted-foreground block">
                  报文可视化映射
                </span>
                <span className="text-[10px] text-muted-foreground italic">
                  支持字段类型、必填校验及注释提取
                </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowJsonBodyDialog(true)}
              className="gap-2 h-7 text-xs"
            >
              <CodeIcon className="size-3.5" />
              贴入 JSON 报文
            </Button>
          </div>
          
          <div className="rounded-md border p-4 bg-muted/10">
             <HttpBodyTreeEditor
                scene={scene}
                step={step}
                onChange={onChange}
              />
          </div>
        </TabsContent>
      </Tabs>

      <Dialog open={showJsonBodyDialog} onOpenChange={setShowJsonBodyDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>贴入原始 JSON 报文</DialogTitle>
            <DialogDescription>
              系统将自动解析报文中的字段，并允许您为每个字段选择对应的变量。支持 // 注释。
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="border-input bg-muted/20 overflow-hidden rounded-md border">
              <CodeMirror
                value={rawJsonInput}
                height="300px"
                extensions={extensions}
                theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
                onChange={(v) => setRawJsonBodyInput(v)}
                placeholder='在此贴入带 // 注释的 JSON 报文...'
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowJsonBodyDialog(false)}>取消</Button>
            <Button onClick={handleImportJson} disabled={!rawJsonInput.trim()}>确定并转换</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
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

function parseJsonWithComments(input: string): { cleanJson: string; labels: Record<string, string> } {
  const labels: Record<string, string> = {};
  const lines = input.split("\n");
  const cleanLines = lines.map(line => {
    const match = /^\s*"([^"]+)"\s*:.*?\/\/\s*(.*)$/.exec(line);
    if (match) {
      const key = match[1];
      const comment = match[2]?.trim();
      if (key && comment) {
        labels[key] = comment;
      }
    }
    return line.replace(/\/\/.*$/, "");
  });

  return {
    cleanJson: cleanLines.join("\n"),
    labels,
  };
}
