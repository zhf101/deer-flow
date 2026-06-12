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

import { VariableCommandList } from "../common/editors/variable-selector";
import {
  countFields,
  flattenSchema,
  getFlatIndex,
  jsonToFields,
  parseJsonWithComments,
  updateFieldPropAtPath,
} from "../common/lib/schema-utils";
import type {
  InputFieldDefinition,
  InputFieldType,
  SceneDefinition,
} from "../common/lib/types";
import { resolveVariableLabel } from "../common/lib/variable-utils";

import { SceneSuccessCriteriaPanel } from "./scene-success-criteria-panel";

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

  const schema = useMemo(() => scene.resultSchema ?? [], [scene.resultSchema]);
  const mapping = useMemo(
    () => scene.resultMapping ?? {},
    [scene.resultMapping],
  );
  const errorPolicy = scene.errorPolicy ?? "STOP_ON_ERROR";

  const flatFields = useMemo(() => flattenSchema(schema), [schema]);
  const leafFields = useMemo(
    () => flatFields.filter((f) => f.type !== "object" && f.type !== "array"),
    [flatFields],
  );

  // 结果结构语义完整度：叶子字段中 label+remark 齐全的占比
  const semanticStats = useMemo(() => {
    const total = leafFields.length;
    const complete = leafFields.filter(
      (f) => f.fieldLabel.trim() && f.fieldRemark.trim(),
    ).length;
    return { total, complete };
  }, [leafFields]);

  // 映射完成度：已配置映射值的叶子字段占比
  const mappingStats = useMemo(() => {
    const total = leafFields.length;
    const mapped = leafFields.filter((f) =>
      (mapping[f.path] ?? "").trim(),
    ).length;
    return { total, mapped };
  }, [leafFields, mapping]);

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
    // 构建索引路径，用于定位要删除的字段
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

    // 从树中移除字段及其子节点
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

    // 清理已删除路径对应的映射
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
        name: "",
        label: "",
        remark: "",
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
      name: "",
      label: "",
      remark: "",
      type: "string",
      required: false,
      batchEnabled: false,
    });
    onChange({ ...scene, resultSchema: next });
  };

  return (
    <div
      className={cn("space-y-10", readOnly && "pointer-events-none opacity-80")}
    >
      {/* 第 1 部分：结果 schema 定义 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="text-primary flex items-center gap-2 font-bold">
            <CodeIcon className="size-4" />
            <span>1. 结果结构定义</span>
            {semanticStats.total > 0 && (
              <span
                className={cn(
                  "text-[10px] font-normal tabular-nums",
                  semanticStats.complete === semanticStats.total
                    ? "text-emerald-600"
                    : "text-amber-600",
                )}
              >
                语义 {semanticStats.complete}/{semanticStats.total}
              </span>
            )}
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
        <p className="text-muted-foreground text-xs">
          定义场景最终返回的结果结构，支持嵌套对象和数组。编辑字段路径、中文名和备注。
        </p>
        <div className="bg-card overflow-hidden rounded-lg border">
          <div className="bg-muted/30 text-muted-foreground grid grid-cols-[1fr_120px_80px_150px_1fr_64px] gap-3 border-b px-4 py-2.5 text-[10px] font-bold uppercase">
            <div>字段路径</div>
            <div>中文名</div>
            <div>类型</div>
            <div>示例值</div>
            <div>备注</div>
            <div className="text-center">操作</div>
          </div>
          <div className="divide-border/50 max-h-[360px] divide-y overflow-auto">
            {schema.length === 0 ? (
              <div className="text-muted-foreground py-12 text-center text-xs italic">
                暂未定义结果结构，点击&quot;导入 JSON 样例&quot;或手动添加字段
              </div>
            ) : (
              schema.map((field, idx) => (
                <ResultSchemaRow
                  key={idx}
                  field={field}
                  flatIndex={getFlatIndex(schema, idx)}
                  depth={0}
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
          className="h-8 w-full border border-dashed text-xs"
          onClick={handleAddTopLevelField}
        >
          <PlusIcon className="mr-1 size-3" />
          添加顶层字段
        </Button>
      </section>

      {/* 第 2 部分：字段值映射 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 font-bold text-blue-600">
            <LinkIcon className="size-4" />
            <span>2. 字段值映射</span>
            {mappingStats.total > 0 && (
              <span
                className={cn(
                  "text-[10px] font-normal tabular-nums",
                  mappingStats.mapped === mappingStats.total
                    ? "text-emerald-600"
                    : "text-amber-600",
                )}
              >
                已映射 {mappingStats.mapped}/{mappingStats.total}
              </span>
            )}
          </div>
        </div>
        <p className="text-muted-foreground text-xs">
          为每个叶子字段绑定变量来源。可从输入参数、所有步骤输出或系统变量中选择。
        </p>
        <div className="bg-card overflow-hidden rounded-lg border">
          <div className="bg-muted/40 text-muted-foreground grid grid-cols-[1fr_100px_1fr_48px] gap-3 border-b px-4 py-2 text-[10px] font-bold uppercase">
            <div>字段路径</div>
            <div>中文名</div>
            <div>值来源</div>
            <div />
          </div>
          <div className="divide-border/50 divide-y">
            {leafFields.length === 0 ? (
              <div className="text-muted-foreground py-8 text-center text-[10px] italic">
                请先在上方定义结果结构
              </div>
            ) : (
              leafFields.map((f) => {
                const rawValue = mapping[f.path] ?? "";
                const displayLabel = rawValue
                  ? resolveVariableLabel(rawValue, scene)
                  : "";
                const issueMessages = getResultMappingIssueMessages(
                  f,
                  rawValue,
                );
                return (
                  <div
                    key={f.path}
                    className={cn(
                      "grid grid-cols-[1fr_100px_1fr_48px] items-center gap-2 px-4 py-2",
                      issueMessages.length > 0 &&
                        "border-l-2 border-l-amber-400",
                    )}
                  >
                    <div
                      className="flex min-w-0 items-center gap-1.5 font-mono text-[11px]"
                      title={f.path}
                    >
                      {issueMessages.length > 0 && (
                        <AlertTriangleIcon
                          className="size-3 shrink-0 text-amber-500"
                          aria-label="语义提醒"
                        >
                          <title>{issueMessages.join("\n")}</title>
                        </AlertTriangleIcon>
                      )}
                      <span className="truncate">{f.label}</span>
                    </div>
                    <div className="text-muted-foreground truncate text-[10px]">
                      {f.fieldLabel || "-"}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Popover>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            className={cn(
                              "h-7 flex-1 rounded-md border px-2 text-left text-xs transition-colors",
                              rawValue
                                ? "border-blue-200 bg-blue-50/50 text-blue-700"
                                : issueMessages.length > 0
                                  ? "text-muted-foreground hover:border-primary/40 border-l-2 border-l-amber-400"
                                  : "bg-background text-muted-foreground hover:border-primary/40 border-dashed",
                            )}
                          >
                            {displayLabel || "点击选择变量"}
                          </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-[300px] p-0" align="start">
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
                          className="text-muted-foreground max-w-[80px] truncate font-mono text-[9px]"
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
                          className="text-muted-foreground hover:text-destructive h-6 w-6"
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

      <SceneSuccessCriteriaPanel
        scene={scene}
        onChange={onChange}
        readOnly={readOnly}
      />

      {/* 第 4 部分：错误策略 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <div className="flex items-center gap-2 font-bold text-amber-600">
            <ShieldIcon className="size-4" />
            <span>4. 异常处理策略</span>
          </div>
        </div>
        <p className="text-muted-foreground text-xs">
          定义场景编排中任一步骤执行失败时的处理策略。此策略控制编排流程，与批量迭代失败策略（批量设置页）独立。
        </p>
        <div className="bg-card space-y-3 rounded-lg border p-4">
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
                  <AlertTriangleIcon className="text-destructive size-3.5" />
                  <div>
                    <div className="text-xs font-medium">中断编排</div>
                    <div className="text-muted-foreground text-[10px]">
                      任一步骤失败则终止所有后续步骤
                    </div>
                  </div>
                </div>
              </SelectItem>
              <SelectItem value="CONTINUE_ON_ERROR">
                <div className="flex items-center gap-2">
                  <ShieldIcon className="text-muted-foreground size-3.5" />
                  <div>
                    <div className="text-xs font-medium">继续执行</div>
                    <div className="text-muted-foreground text-[10px]">
                      步骤失败后仍执行后续步骤，最终汇总结果
                    </div>
                  </div>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
          <div
            className={cn(
              "rounded-md border px-3 py-2 text-[10px]",
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

      {/* JSON 导入对话框 */}
      <Dialog open={showJsonDialog} onOpenChange={setShowJsonDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>贴入结果报文样例</DialogTitle>
            <DialogDescription>
              支持 // 行尾注释提取为中文名，例如: &quot;orderNo&quot;:
              &quot;ORD001&quot; // 订单号
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <textarea
              className="border-input bg-muted/20 focus:ring-ring h-[300px] w-full rounded-md border p-3 font-mono text-xs focus:ring-2 focus:outline-none"
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

function getResultSchemaIssueMessages(field: InputFieldDefinition): string[] {
  const messages: string[] = [];
  if (!(field.label ?? "").trim()) {
    messages.push(`结果字段 ${field.name || "(未命名)"} 缺少中文名`);
  }
  if (!(field.remark ?? "").trim()) {
    messages.push(`结果字段 ${field.name || "(未命名)"} 缺少业务说明`);
  }
  return messages;
}

function getResultMappingIssueMessages(
  field: ReturnType<typeof flattenSchema>[number],
  rawValue: string,
): string[] {
  const messages: string[] = [];
  if (!field.fieldLabel.trim()) {
    messages.push(`结果字段 ${field.path} 缺少中文名`);
  }
  if (!field.fieldRemark.trim()) {
    messages.push(`结果字段 ${field.path} 缺少业务说明`);
  }
  if (!rawValue.trim()) {
    messages.push(`结果字段 ${field.path} 尚未配置输出映射`);
  }
  return messages;
}

/* ── 结果 schema 行（递归） ── */

function ResultSchemaRow({
  field,
  flatIndex,
  depth,
  onUpdateField,
  onDeleteField,
  onAddChild,
}: {
  field: InputFieldDefinition;
  flatIndex: number;
  depth: number;
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
  const issueMessages = isContainer ? [] : getResultSchemaIssueMessages(field);

  let childFlatIndex = flatIndex + 1;

  return (
    <div>
      <div className="hover:bg-muted/30 flex items-center gap-3 px-4 py-2 transition-colors">
        <div
          className="flex min-w-0 flex-1 items-center gap-1.5"
          style={{ paddingLeft: `${depth * 16}px` }}
        >
          <Input
            className="bg-background/50 border-border/50 h-6 px-1.5 font-mono text-[11px]"
            value={field.name}
            onChange={(e) => onUpdateField(flatIndex, "name", e.target.value)}
          />
          {isContainer && (
            <span className="text-muted-foreground/50 shrink-0 text-[8px]">
              {field.type === "array" ? "[*]" : "{}"}
            </span>
          )}
          {issueMessages.length > 0 && (
            <AlertTriangleIcon
              className="size-3.5 shrink-0 text-amber-500"
              aria-label="语义提醒"
            >
              <title>{issueMessages.join("\n")}</title>
            </AlertTriangleIcon>
          )}
        </div>
        <div className="w-[120px]">
          <Input
            className={cn(
              "bg-background/50 border-border/50 h-6 px-1.5 text-[10px]",
              !isContainer &&
                !(field.label ?? "").trim() &&
                "border-l-2 border-l-amber-400",
            )}
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
            <SelectTrigger className="h-6 px-1.5 font-mono text-[9px]">
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
              className="bg-background/50 border-border/50 h-6 px-1.5 font-mono text-[10px]"
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
            <span className="text-muted-foreground/50 text-[10px]">-</span>
          )}
        </div>
        <div className="flex-1">
          <Input
            className={cn(
              "bg-background/50 border-border/50 h-6 px-1.5 text-[10px]",
              !isContainer &&
                !(field.remark ?? "").trim() &&
                "border-l-2 border-l-amber-400",
            )}
            value={field.remark ?? ""}
            placeholder="备注"
            onChange={(e) => onUpdateField(flatIndex, "remark", e.target.value)}
          />
        </div>
        <div className="flex w-[64px] items-center justify-center gap-1">
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
            className="text-muted-foreground hover:text-destructive h-5 w-5 p-0"
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
            onUpdateField={onUpdateField}
            onDeleteField={onDeleteField}
            onAddChild={onAddChild}
          />
        );
      })}
    </div>
  );
}
