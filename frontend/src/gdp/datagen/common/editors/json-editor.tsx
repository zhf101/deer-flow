"use client";

import { json } from "@codemirror/lang-json";
import { basicLightInit } from "@uiw/codemirror-theme-basic";
import { monokaiInit } from "@uiw/codemirror-theme-monokai";
import CodeMirror from "@uiw/react-codemirror";
import { useTheme } from "@/components/theme-provider";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { formatJson, parseJsonObject } from "../lib/validation";

interface JsonEditorProps {
  label: string;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  className?: string;
  height?: string;
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

export function JsonEditor({
  label,
  value,
  onChange,
  className,
  height = "180px",
}: JsonEditorProps) {
  const { resolvedTheme } = useTheme();
  const [text, setText] = useState(() => formatJson(value));
  const [error, setError] = useState<string | null>(null);
  const extensions = useMemo(() => [json()], []);

  const apply = (nextText: string) => {
    setText(nextText);
    try {
      const parsed = parseJsonObject(nextText);
      setError(null);
      onChange(parsed);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "JSON 格式错误");
    }
  };

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground text-xs font-medium">{label}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => apply(formatJson(value))}
        >
          格式化
        </Button>
      </div>
      <div className="border-input bg-muted/20 overflow-hidden rounded-md border">
        <CodeMirror
          value={text}
          height={height}
          extensions={extensions}
          theme={resolvedTheme === "dark" ? darkTheme : lightTheme}
          basicSetup={{
            foldGutter: true,
            lineNumbers: false,
            highlightActiveLine: false,
            highlightActiveLineGutter: false,
          }}
          onChange={apply}
        />
      </div>
      {error ? <p className="text-destructive text-xs">{error}</p> : null}
    </div>
  );
}
