"use client";

import {
  AlertTriangleIcon,
  CodeIcon,
  LinkIcon,
  PlusIcon,
  ShieldIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
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
  InputFieldDefinition,
  InputFieldType,
  SceneDefinition,
} from "../lib/types";
import { resolveVariableLabel } from "../lib/variable-utils";

import { VariableCommandList } from "./variable-selector";

interface ResultMappingPanelProps {
  scene: SceneDefinition;
  onChange: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

export function ResultMappingPanel({
  scene,
  onChange,
  readOnly,
}: ResultMappingPanelProps) {
  const [showJsonDialog, setShowJsonDialog] = useState(false);
  const [rawJsonInput, setRawJsonInput] = useState("");

  const schema = scene.resultSchema ?? [];
  const mapping = scene.resultMapping ?? {};
  const errorPolicy = scene.errorPolicy ?? "STOP_ON_ERROR";

  const flatFields = useMemo(() => flattenSchema(schema), [schema]);
  const leafFields = useMemo(
    () => flatFields.filter((f) => f.type !== "object" && f.type !== "array"),
    [flatFields],
  );

  const handleImportJson = () => {
    try {
      const { cleanJson, labels } = parseJsonWithComments(rawJsonInput);
      const parsed = JSON.parse(cleanJson) as Record<string, unknown>;
      const generated = jsonToFields(parsed, labels);
      onChange({ ...scene, resultSchema: generated });
      setShowJsonDialog(false);
      setRawJsonInput("");
      toast.success("结果结构已解析");
    } catch {
      toast.error("JSON 解析失败，请检查格式");
    }
  };

  const handleUpdateField = (
    flatIndex: number,
    prop: "defaultValue" | "label" | "remark" | "name" | "type",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    value: any,
  ) => {
    const next = updateFieldPropAtPath(schema, flatIndex, prop, value);
    onChange({ ...scene, resultSchema: next });
  };

  const handleDeleteField = (flatIndex: number) => {
    // Build index paths to find which field to delete
    const indexPaths: number[][] = [];
    let count = 0;
    const buildPaths = (
      fields: InputFieldDefinition[],
      currentPath: number[],
    ) => {
      for (let i = 0; i < fields.length; i++) {
        indexPaths.push([...currentPath, i]);
        if (count === flatIndex) return;
        count++;
        if (fields[i]!.children) {
          buildPaths(fields[i]!.children!, [...currentPath, i]);
        }
      }
    };
    buildPaths(schema, []);
    const targetPath = indexPaths[flatIndex];
    if (!targetPath) return;

    // Remove the field and its children from the tree
    const next = JSON.parse(JSON.stringify(schema)) as InputFieldDefinition[];
    if (targetPath.length === 1) {
      next.splice(targetPath[0]!, 1);
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let parent: any = next;
      for (let i = 0; i < targetPath.length - 2; i++) {
        parent = parent[targetPath[i]!].children;
      }
      parent[targetPath[targetPath.length - 2]!].children.splice(
        targetPath[targetPath.length - 1]!,
        1,
      );
    }

    // Clean up mapping for deleted paths
    const deletedPaths = flatFields
      .slice(flatIndex)
      .filter(
        (f, i) =>
          i === 0 ||
          flatFields[flatIndex + i]!.path.startsWith(
            flatFields[flatIndex]!.path,
          ),
      )
      .map((f) => f.path);
    const nextMapping = { ...mapping };
    deletedPaths.forEach((p) => {
      delete nextMapping[p];
    });

    onChange({ ...scene, resultSchema: next, resultMapping: nextMapping });
  };

  const handleAddTopLevelField = () => {
    const next = [
      ...schema,
      {
        name: `field${schema.length + 1}`,
        label: "",
        type: "string" as InputFieldType,
        required: false,
        batchEnabled: false,
      },
    ];
    onChange({ ...scene, resultSchema: next });
  };

  const handleAddChildField = (parentFlatIndex: number) => {
    const indexPaths: number[][] = [];
    let count = 0;
    const buildPaths = (
      fields: InputFieldDefinition[],
      currentPath: number[],
    ) => {
      for (let i = 0; i < fields.length; i++) {
        indexPaths.push([...currentPath, i]);
        if (count === parentFlatIndex) return;
        count++;
        if (fields[i]!.children) {
          buildPaths(fields[i]!.children!, [...currentPath, i]);
        }
      }
    };
    buildPaths(schema, []);
    const targetPath = indexPaths[parentFlatIndex];
    if (!targetPath) return;

    const next = JSON.parse(JSON.stringify(schema)) as InputFieldDefinition[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let field: any = next;
    for (let i = 0; i < targetPath.length; i++) {
      field = field[targetPath[i]!];
      if (i < targetPath.length - 1) field = field.children;
    }
    field.children ??= [];
    field.children.push({
      name: `child${field.children.length + 1}`,
      label: "",
      type: "string",
      required: false,
      batchEnabled: false,
    });
    onChange({ ...scene, resultSchema: next });
  };

  return (
    <div className={cn("space-y-10", readOnly && "pointer-events-none opacity-80")}>
      {/* SECTION 1: RESULT SCHEMA DEFINITION */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-primary font-bold">
            <CodeIcon className="size-4" />
            <span>1. 结果结构定义</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowJsonDialog(true)}
            className="h-7 text-xs"
          >
            导入 JSON 样例
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          定义场景最终返回的结果结构，支持嵌套对象和数组。编辑字段路径、中文名和备注。
        </p>
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="grid grid-cols-[1fr_120px_80px_150px_1fr_64px] gap-3 px-4 py-2.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
            <div>字段路径</div>
            <div>中文名</div>
            <div>类型</div>
            <div>示例值</div>
            <div>备注</div>
            <div className="text-center">操作</div>
          </div>
          <div className="max-h-[360px] overflow-auto divide-y divide-border/50">
            {schema.length === 0 ? (
              <div className="py-12 text-center text-xs text-muted-foreground italic">
                暂未定义结果结构，点击&quot;导入 JSON 样例&quot;或手动添加字段
              </div>
            ) : (
              schema.map((field, idx) => (
                <ResultSchemaRow
                  key={idx}
                  field={field}
                  flatIndex={getFlatIndex(schema, idx)}
                  depth={0}
                  flatFields={flatFields}
                  onUpdateField={handleUpdateField}
                  onDeleteField={handleDeleteField}
                  onAddChild={handleAddChildField}
                />
              ))
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 text-xs border border-dashed w-full"
          onClick={handleAddTopLevelField}
        >
          <PlusIcon className="mr-1 size-3" />
          添加顶层字段
        </Button>
      </section>

      {/* SECTION 2: FIELD VALUE MAPPING */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-blue-600 font-bold">
            <LinkIcon className="size-4" />
            <span>2. 字段值映射</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          为每个叶子字段绑定变量来源。可从输入参数、所有步骤输出或系统变量中选择。
        </p>
        <div className="rounded-lg border bg-card overflow-hidden">
          <div className="grid grid-cols-[1fr_100px_1fr_48px] gap-3 px-4 py-2 bg-muted/40 text-[10px] font-bold text-muted-foreground uppercase border-b">
            <div>字段路径</div>
            <div>中文名</div>
            <div>值来源</div>
            <div />
          </div>
          <div className="divide-y divide-border/50">
            {leafFields.length === 0 ? (
              <div className="py-8 text-center text-[10px] text-muted-foreground italic">
                请先在上方定义结果结构
              </div>
            ) : (
              leafFields.map((f) => {
                const rawValue = mapping[f.path] ?? "";
                const displayLabel = rawValue
                  ? resolveVariableLabel(rawValue, scene)
                  : "";
                return (
                  <div
                    key={f.path}
                    className="grid grid-cols-[1fr_100px_1fr_48px] gap-2 items-center px-4 py-2"
                  >
                    <div
                      className="font-mono text-[11px] truncate"
                      title={f.path}
                    >
                      {f.label}
                    </div>
                    <div className="text-[10px] text-muted-foreground truncate">
                      {f.fieldLabel || "-"}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Popover>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            className={cn(
                              "flex-1 h-7 px-2 text-left text-xs rounded-md border transition-colors",
                              rawValue
                                ? "bg-blue-50/50 text-blue-700 border-blue-200"
                                : "bg-background text-muted-foreground border-dashed hover:border-primary/40",
                            )}
                          >
                            {displayLabel || "点击选择变量"}
                          </button>
                        </PopoverTrigger>
                        <PopoverContent
                          className="w-[300px] p-0"
                          align="start"
                        >
                          <VariableCommandList
                            scene={scene}
                            includeAllSteps
                            onSelect={(variable) => {
                              onChange({
                                ...scene,
                                resultMapping: {
                                  ...mapping,
                                  [f.path]: variable,
                                },
                              });
                            }}
                          />
                        </PopoverContent>
                      </Popover>
                      {rawValue && (
                        <span
                          className="text-[9px] text-muted-foreground font-mono max-w-[80px] truncate"
                          title={rawValue}
                        >
                          {rawValue}
                        </span>
                      )}
                    </div>
                    <div className="flex justify-center">
                      {rawValue && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 text-muted-foreground hover:text-destructive"
                          onClick={() => {
                            const next = { ...mapping };
                            delete next[f.path];
                            onChange({
                              ...scene,
                              resultMapping: next,
                            });
                          }}
                        >
                          <XIcon className="size-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>

      {/* SECTION 3: ERROR POLICY */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 text-amber-600 font-bold">
            <ShieldIcon className="size-4" />
            <span>3. 异常处理策略</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          定义场景编排中任一步骤执行失败时的处理策略。此策略控制编排流程，与批量迭代失败策略（批量设置页）独立。
        </p>
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <Select
            value={errorPolicy}
            onValueChange={(value) =>
              onChange({
                ...scene,
                errorPolicy: value as "STOP_ON_ERROR" | "CONTINUE_ON_ERROR",
              })
            }
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="STOP_ON_ERROR">
                <div className="flex items-center gap-2">
                  <AlertTriangleIcon className="size-3.5 text-destructive" />
                  <div>
                    <div className="text-xs font-medium">中断编排</div>
                    <div className="text-[10px] text-muted-foreground">
                      任一步骤失败则终止所有后续步骤
                    </div>
                  </div>
                </div>
              </SelectItem>
              <SelectItem value="CONTINUE_ON_ERROR">
                <div className="flex items-center gap-2">
                  <ShieldIcon className="size-3.5 text-muted-foreground" />
                  <div>
                    <div className="text-xs font-medium">继续执行</div>
                    <div className="text-[10px] text-muted-foreground">
                      步骤失败后仍执行后续步骤，最终汇总结果
                    </div>
                  </div>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
          <div
            className={cn(
              "text-[10px] px-3 py-2 rounded-md border",
              errorPolicy === "STOP_ON_ERROR"
                ? "bg-destructive/5 border-destructive/10 text-destructive"
                : "bg-muted/50 border-border text-muted-foreground",
            )}
          >
            {errorPolicy === "STOP_ON_ERROR"
              ? "当前策略：任一步骤执行异常时，整个编排立即中断，不再执行后续步骤。适用于需要严格保证数据一致性的场景。"
              : "当前策略：步骤执行异常时跳过该步骤继续执行后续步骤。适用于容错性较强的场景。"}
          </div>
        </div>
      </section>

      {/* JSON Import Dialog */}
      <Dialog open={showJsonDialog} onOpenChange={setShowJsonDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>贴入结果报文样例</DialogTitle>
            <DialogDescription>
              支持 // 行尾注释提取为中文名，例如: &quot;orderNo&quot;: &quot;ORD001&quot; // 订单号
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <textarea
              className="w-full h-[300px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder='{"orderNo": "ORD001", // 订单号\n "payAmount": 99.9, // 应付金额\n "buyer": {\n   "userId": "U001" // 买家ID\n }}'
              value={rawJsonInput}
              onChange={(e) => setRawJsonInput(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowJsonDialog(false)}>
              取消
            </Button>
            <Button onClick={handleImportJson} disabled={!rawJsonInput.trim()}>
              确定解析
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ─── Result Schema Row (recursive) ─── */

function ResultSchemaRow({
  field,
  flatIndex,
  depth,
  flatFields,
  onUpdateField,
  onDeleteField,
  onAddChild,
}: {
  field: InputFieldDefinition;
  flatIndex: number;
  depth: number;
  flatFields: ReturnType<typeof flattenSchema>;
  onUpdateField: (
    flatIndex: number,
    prop: "defaultValue" | "label" | "remark" | "name" | "type",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    value: any,
  ) => void;
  onDeleteField: (flatIndex: number) => void;
  onAddChild: (flatIndex: number) => void;
}) {
  const isContainer = field.type === "object" || field.type === "array";

  let childFlatIndex = flatIndex + 1;

  return (
    <div>
      <div className="flex items-center gap-3 px-4 py-2 hover:bg-muted/30 transition-colors">
        <div
          className="flex-1 min-w-0 flex items-center gap-1.5"
          style={{ paddingLeft: `${depth * 16}px` }}
        >
          <Input
            className="h-6 text-[11px] font-mono bg-background/50 border-border/50 px-1.5"
            value={field.name}
            onChange={(e) => onUpdateField(flatIndex, "name", e.target.value)}
          />
          {isContainer && (
            <span className="text-[8px] text-muted-foreground/50 shrink-0">
              {field.type === "array" ? "[*]" : "{}"}
            </span>
          )}
        </div>
        <div className="w-[120px]">
          <Input
            className="h-6 text-[10px] bg-background/50 border-border/50 px-1.5"
            value={field.label ?? ""}
            placeholder="中文名"
            onChange={(e) => onUpdateField(flatIndex, "label", e.target.value)}
          />
        </div>
        <div className="w-[80px]">
          <Select
            value={field.type}
            onValueChange={(val: InputFieldType) =>
              onUpdateField(flatIndex, "type", val)
            }
          >
            <SelectTrigger className="h-6 text-[9px] font-mono px-1.5">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["string", "number", "boolean", "date", "object", "array"].map(
                (t) => (
                  <SelectItem key={t} value={t} className="text-xs">
                    {t}
                  </SelectItem>
                ),
              )}
            </SelectContent>
          </Select>
        </div>
        <div className="w-[150px]">
          {!isContainer ? (
            <Input
              className="h-6 text-[10px] font-mono bg-background/50 border-border/50 px-1.5"
              value={
                field.defaultValue != null
                  ? String(field.defaultValue as string | number | boolean)
                  : ""
              }
              placeholder="示例值"
              onChange={(e) =>
                onUpdateField(flatIndex, "defaultValue", e.target.value)
              }
            />
          ) : (
            <span className="text-[10px] text-muted-foreground/50">-</span>
          )}
        </div>
        <div className="flex-1">
          <Input
            className="h-6 text-[10px] bg-background/50 border-border/50 px-1.5"
            value={field.remark ?? ""}
            placeholder="备注"
            onChange={(e) => onUpdateField(flatIndex, "remark", e.target.value)}
          />
        </div>
        <div className="w-[64px] flex items-center justify-center gap-1">
          {isContainer && (
            <Button
              variant="ghost"
              size="sm"
              className="h-5 w-5 p-0"
              onClick={() => onAddChild(flatIndex)}
              title="添加子字段"
            >
              <PlusIcon className="size-3" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-5 w-5 p-0 text-muted-foreground hover:text-destructive"
            onClick={() => onDeleteField(flatIndex)}
            title="删除字段"
          >
            <Trash2Icon className="size-3" />
          </Button>
        </div>
      </div>
      {field.children?.map((child, i) => {
        const currentIndex = childFlatIndex;
        childFlatIndex += countFields(child);
        return (
          <ResultSchemaRow
            key={i}
            field={child}
            flatIndex={currentIndex}
            depth={depth + 1}
            flatFields={flatFields}
            onUpdateField={onUpdateField}
            onDeleteField={onDeleteField}
            onAddChild={onAddChild}
          />
        );
      })}
    </div>
  );
}
