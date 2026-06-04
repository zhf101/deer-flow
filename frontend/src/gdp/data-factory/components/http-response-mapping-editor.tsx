"use client";

import { CodeIcon, PlusIcon, ShieldCheckIcon, Trash2Icon, VariableIcon } from "lucide-react";
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

import {
  countFields,
  flattenSchema,
  getFlatIndex,
  jsonToFields,
  parseJsonWithComments,
  updateFieldPropAtPath,
} from "../lib/schema-utils";
import type { InputFieldDefinition, StepDefinition, ConditionRule, ConditionOperator } from "../lib/types";

interface HttpResponseMappingEditorProps {
  step: StepDefinition;
  onChange: (updates: Partial<StepDefinition>) => void;
}

export function HttpResponseMappingEditor({
  step,
  onChange,
}: HttpResponseMappingEditorProps) {
  const [showJsonDialog, setShowJsonDialog] = useState(false);
  const [rawJsonInput, setRawJsonInput] = useState("");

  const schema = step.responseSchema || [];
  const outputMapping = step.outputMapping || {};
  const responseHandling = step.responseHandling || {
      expectedContentType: "JSON",
      statusCode: { success: [200] },
      businessSuccess: { allOf: [] },
      businessFailure: { anyOf: [] }
  };
  const successRules = (responseHandling.businessSuccess?.allOf || []) as ConditionRule[];
  const failureRules = (responseHandling.businessFailure?.anyOf || []) as ConditionRule[];

  const flatFields = useMemo(() => flattenSchema(schema, "$.body"), [schema]);
  // Only leaf fields (non-object, non-array) are extractable
  const extractableFields = useMemo(() => flatFields.filter(f => f.type !== 'object' && f.type !== 'array'), [flatFields]);

  const handleImportJson = () => {
    try {
      const { cleanJson, labels } = parseJsonWithComments(rawJsonInput);
      const parsed = JSON.parse(cleanJson);
      const generatedSchema = jsonToFields(parsed, labels);

      onChange({ responseSchema: generatedSchema });
      setShowJsonDialog(false);
      setRawJsonInput("");
      toast.success("响应结构已解析");
    } catch (e) {
      toast.error("JSON 解析失败，请检查格式");
    }
  };

  const updateFieldProp = (flatIndex: number, prop: "defaultValue" | "label" | "remark", value: unknown) => {
    const next = updateFieldPropAtPath(schema, flatIndex, prop, value);
    onChange({ responseSchema: next });
  };

  return (
    <div className="space-y-10">
      {/* SECTION 1: RESPONSE SCHEMA TABLE */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
            <div className="flex items-center gap-2 text-primary font-bold">
                <CodeIcon className="size-4" />
                <span>1. 响应报文结构</span>
            </div>
            <Button variant="outline" size="sm" onClick={() => setShowJsonDialog(true)} className="h-7 text-xs">
                更新报文样例
            </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          编辑示例值和备注说明，勾选需要提取到下游的字段。
        </p>
        <div className="rounded-lg border bg-card overflow-hidden">
            <div className="grid grid-cols-[32px_1fr_120px_80px_150px_1fr] gap-3 px-4 py-2.5 bg-muted/30 text-[10px] font-bold text-muted-foreground uppercase border-b">
                <div className="text-center">提取</div>
                <div>字段路径</div>
                <div>中文名</div>
                <div>类型</div>
                <div>示例值</div>
                <div>备注</div>
            </div>
            <div className="max-h-[360px] overflow-auto divide-y divide-border/50">
                {schema.length === 0 ? (
                    <div className="py-12 text-center text-xs text-muted-foreground italic">暂未贴入报文示例，点击"更新报文样例"导入</div>
                ) : (
                    schema.map((field, idx) => (
                        <ResponseSampleRow
                            key={idx}
                            field={field}
                            flatIndex={getFlatIndex(schema, idx)}
                            depth={0}
                            outputMapping={outputMapping}
                            flatFields={flatFields}
                            onUpdateField={updateFieldProp}
                            onToggleExtract={(path, checked) => {
                                const baseName = path.split('.').pop()?.replace('[*]', '') || 'field';
                                const matchedField = flatFields.find(f => f.path === path);
                                if (checked) {
                                    const nextMeta = { ...(step.outputMeta ?? {}) };
                                    nextMeta[baseName] = {
                                        label: matchedField?.fieldLabel ?? "",
                                        remark: matchedField?.fieldRemark ?? "",
                                    };
                                    onChange({
                                        outputMapping: { ...outputMapping, [baseName]: path },
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
                            }}
                        />
                    ))
                )}
            </div>
        </div>
      </section>

      {/* SECTION 2: EXTRACTION MANAGER */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
            <div className="flex items-center gap-2 text-blue-600 font-bold">
                <VariableIcon className="size-4" />
                <span>2. 提取响应数据到变量</span>
            </div>
        </div>
        <p className="text-xs text-muted-foreground">
          从响应报文中提取字段，定义下游步骤可引用的变量名。
        </p>
        <div className="space-y-3">
            <div className="rounded-lg border bg-card overflow-hidden">
                <div className="grid grid-cols-[1fr_1fr_120px_1fr_48px] gap-4 px-4 py-2 bg-muted/40 text-[10px] font-bold text-muted-foreground uppercase border-b">
                    <div>响应字段</div>
                    <div>下游变量名</div>
                    <div>中文名</div>
                    <div>备注</div>
                    <div className="text-center">操作</div>
                </div>
                <div className="p-2 space-y-2">
                    {Object.entries(outputMapping).map(([varName, path]) => {
                        const matched = flatFields.find(f => f.path === path);
                        const meta = step.outputMeta?.[varName] ?? {};
                        return (
                            <div key={varName} className="grid grid-cols-[1fr_1fr_120px_1fr_48px] gap-2 items-center bg-muted/10 p-1.5 rounded border border-transparent hover:border-border transition-all">
                                <div className="px-2 text-xs truncate" title={path}>
                                    {matched ? matched.label : path}
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
                                    value={meta.label ?? ""}
                                    placeholder="中文名"
                                    onChange={(e) => {
                                        const nextMeta = { ...(step.outputMeta ?? {}) };
                                        nextMeta[varName] = { ...nextMeta[varName], label: e.target.value };
                                        onChange({ outputMeta: nextMeta });
                                    }}
                                />
                                <Input
                                    className="h-7 text-xs bg-background"
                                    value={meta.remark ?? ""}
                                    placeholder="备注"
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
                        <div className="py-6 text-center text-[10px] text-muted-foreground italic">
                            未配置提取项，在上方表格中勾选字段或点击下方按钮添加
                        </div>
                    )}
                </div>
            </div>
            <div className="flex justify-start">
                <Select onValueChange={(path) => {
                    if (!path) return;
                    const baseName = path.split('.').pop()?.replace('[*]', '') || 'data';
                    let varName = baseName;
                    let suffix = 1;
                    while (varName in outputMapping) {
                        varName = `${baseName}_${suffix++}`;
                    }
                    const matchedField = flatFields.find(f => f.path === path);
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
                    <SelectTrigger className="w-[200px] h-8 text-xs gap-2">
                        <PlusIcon className="size-3" />
                        <SelectValue placeholder="添加提取字段" />
                    </SelectTrigger>
                    <SelectContent>
                        {extractableFields.map(f => (
                            <SelectItem key={f.path} value={f.path} className="text-xs">
                                {f.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>
        </div>
      </section>

      {/* SECTION 3: LOGIC BUILDER */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
            <div className="flex items-center gap-2 text-green-600 font-bold">
                <ShieldCheckIcon className="size-4" />
                <span>3. 业务成功规则配置</span>
            </div>
        </div>
        <div className="space-y-6">
            {/* Failure Rules */}
            <div className="space-y-3">
                <div className="flex items-center gap-2 px-1">
                    <span className="bg-destructive/10 text-destructive text-[10px] px-1.5 py-0.5 rounded font-bold">优先判定失败</span>
                    <span className="text-[10px] text-muted-foreground">(任一规则命中即判定为失败)</span>
                </div>
                <div className="rounded-lg border border-destructive/10 bg-destructive/[0.02] p-2 space-y-2">
                    {failureRules.map((rule, idx) => (
                         <div key={idx} className="flex items-center gap-2 bg-background p-2 rounded border border-destructive/20">
                            <Select
                                value={rule.path}
                                onValueChange={(val) => {
                                    const next = [...failureRules];
                                    const current = next[idx] as any;
                                    next[idx] = { path: val, op: current.op || 'EQ', value: current.value || '' };
                                    onChange({ responseHandling: { ...responseHandling, businessFailure: { anyOf: next } } });
                                }}
                            >
                                <SelectTrigger className="h-7 text-[10px] flex-1 border-none shadow-none font-mono">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {extractableFields.map(f => <SelectItem key={f.path} value={f.path} className="text-xs">{f.label}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <Select
                                value={rule.op}
                                onValueChange={(val: ConditionOperator) => {
                                    const next = [...failureRules];
                                    const current = next[idx] as any;
                                    next[idx] = { path: current.path || '', op: val, value: current.value || '' };
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
                            {rule.op !== 'EXISTS' && (
                                <Input
                                    className="h-7 text-[10px] w-[120px]"
                                    value={String(rule.value || '')}
                                    onChange={(e) => {
                                        const next = [...failureRules];
                                        const current = next[idx] as any;
                                        next[idx] = { path: current.path || '', op: current.op || 'EQ', value: e.target.value };
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
                        const next = [...failureRules, { path: extractableFields[0]?.path || '', op: 'EQ' as ConditionOperator, value: '' }];
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
                <div className="rounded-lg border border-green-500/10 bg-green-500/[0.02] p-2 space-y-2">
                    {successRules.map((rule, idx) => (
                         <div key={idx} className="flex items-center gap-2 bg-background p-2 rounded border border-green-500/20">
                            <Select
                                value={rule.path}
                                onValueChange={(val) => {
                                    const next = [...successRules];
                                    const current = next[idx] as any;
                                    next[idx] = { path: val, op: current.op || 'EQ', value: current.value || '' };
                                    onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                                }}
                            >
                                <SelectTrigger className="h-7 text-[10px] flex-1 border-none shadow-none font-mono">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {extractableFields.map(f => <SelectItem key={f.path} value={f.path} className="text-xs">{f.label}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <Select
                                value={rule.op}
                                onValueChange={(val: ConditionOperator) => {
                                    const next = [...successRules];
                                    const current = next[idx] as any;
                                    next[idx] = { path: current.path || '', op: val, value: current.value || '' };
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
                            {rule.op !== 'EXISTS' && (
                                <Input
                                    className="h-7 text-[10px] w-[120px]"
                                    value={String(rule.value || '')}
                                    onChange={(e) => {
                                        const next = [...successRules];
                                        const current = next[idx] as any;
                                        next[idx] = { path: current.path || '', op: current.op || 'EQ', value: e.target.value };
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
                        const next = [...successRules, { path: extractableFields[0]?.path || '', op: 'EQ' as ConditionOperator, value: '' }];
                        onChange({ responseHandling: { ...responseHandling, businessSuccess: { allOf: next } } });
                    }}>
                        <PlusIcon className="mr-1 size-3" />
                        添加成功判定规则 (AND)
                    </Button>
                </div>
            </div>
        </div>
      </section>

      <Dialog open={showJsonDialog} onOpenChange={setShowJsonDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>贴入响应报文样例</DialogTitle>
            <DialogDescription>支持 // 行尾注释提取为备注说明，例如: &quot;accessToken&quot;: &quot;xxx&quot; // 登录令牌</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <textarea
              className="w-full h-[300px] rounded-md border border-input bg-muted/20 p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder='{"code": "0000", // 成功码\n "message": "成功", // 响应消息\n "data": {\n   "accessToken": "eyJhbG..." // 登录令牌\n }}'
              value={rawJsonInput}
              onChange={(e) => setRawJsonInput(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowJsonDialog(false)}>取消</Button>
            <Button onClick={handleImportJson} disabled={!rawJsonInput.trim()}>确定解析</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ResponseSampleRow({
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
    onToggleExtract: (path: string, checked: boolean) => void;
}) {
    const isLeaf = field.type !== 'object' && field.type !== 'array';
    // Compute the JSON path for this field to check if it's in outputMapping
    const flatEntry = flatFields[flatIndex];
    const fieldPath = flatEntry?.path || '';
    const isExtracted = isLeaf && Object.values(outputMapping).some(v => v === fieldPath);

    let childFlatIndex = flatIndex + 1;

    return (
        <div className="space-y-1">
            <div className="flex items-center gap-3 px-4 py-2 hover:bg-muted/30 transition-colors">
                <div className="w-[32px] flex justify-center">
                    {isLeaf ? (
                        <input
                            type="checkbox"
                            checked={isExtracted}
                            onChange={(e) => onToggleExtract(fieldPath, e.target.checked)}
                            className="h-3.5 w-3.5 rounded border-border accent-blue-600 cursor-pointer"
                        />
                    ) : (
                        <span className="text-[9px] text-muted-foreground/50">-</span>
                    )}
                </div>
                <div className="flex-1 font-mono text-[11px] font-medium" style={{ paddingLeft: `${depth * 16}px` }}>
                    <span className={isLeaf ? "" : "text-muted-foreground"}>{field.name}</span>
                </div>
                <div className="w-[120px]">
                    <Input
                        className="h-6 text-[10px] bg-background/50 border-border/50 px-1.5"
                        value={field.label ?? ""}
                        placeholder="字段中文名"
                        onChange={(e) => onUpdateField(flatIndex, "label", e.target.value)}
                    />
                </div>
                <div className="w-[80px]">
                    <span className="text-[9px] font-mono text-muted-foreground/70 uppercase bg-muted/50 px-1.5 py-0.5 rounded">
                        {field.type}
                    </span>
                </div>
                <div className="w-[150px]">
                    {isLeaf ? (
                        <Input
                            className="h-6 text-[10px] font-mono bg-background/50 border-border/50 px-1.5"
                            value={field.defaultValue !== undefined ? String(field.defaultValue as string | number | boolean) : ""}
                            placeholder="输入示例值"
                            onChange={(e) => onUpdateField(flatIndex, "defaultValue", e.target.value)}
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
            </div>
            {field.children?.map((child, i) => {
                const currentFlatIndex = childFlatIndex;
                childFlatIndex += countFields(child);
                return (
                    <ResponseSampleRow
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
