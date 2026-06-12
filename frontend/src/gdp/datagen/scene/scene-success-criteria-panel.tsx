"use client";

import {
  CheckCircle2Icon,
  PlusIcon,
  ShieldCheckIcon,
  Trash2Icon,
  XCircleIcon,
} from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
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
  CONDITION_OPERATORS,
  createDefaultSceneSuccessCriteria,
} from "../common/lib/defaults";
import { flattenSchema } from "../common/lib/schema-utils";
import type {
  ConditionOperator,
  ConditionRule,
  SceneDefinition,
  SceneSuccessCriteria,
} from "../common/lib/types";

interface SceneSuccessCriteriaPanelProps {
  scene: SceneDefinition;
  onChange: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

const VALUELESS_OPERATORS = new Set<ConditionOperator>([
  "EXISTS",
  "NOT_EXISTS",
  "EMPTY",
  "NOT_EMPTY",
]);

const OPERATOR_LABELS: Record<ConditionOperator, string> = {
  EQ: "等于",
  NE: "不等于",
  NEQ: "不等于",
  GT: "大于",
  GTE: "大于等于",
  LT: "小于",
  LTE: "小于等于",
  IN: "在列表中",
  NOT_IN: "不在列表中",
  EXISTS: "存在",
  NOT_EXISTS: "不存在",
  EMPTY: "为空",
  NOT_EMPTY: "非空",
  CONTAINS: "包含",
  REGEX: "正则匹配",
};

export function SceneSuccessCriteriaPanel({
  scene,
  onChange,
  readOnly,
}: SceneSuccessCriteriaPanelProps) {
  const outputFields = useMemo(
    () =>
      flattenSchema(scene.resultSchema ?? []).filter(
        (field) => field.type !== "object" && field.type !== "array",
      ),
    [scene.resultSchema],
  );
  const criteria = scene.successCriteria ?? null;
  const enabled = criteria?.enabled ?? false;
  const successRules = criteria?.businessSuccess.allOf ?? [];
  const failureRules = criteria?.businessFailure.anyOf ?? [];

  const updateCriteria = (next: SceneSuccessCriteria | null) => {
    onChange({ ...scene, successCriteria: next });
  };

  const ensureCriteria = () =>
    criteria ?? createDefaultSceneSuccessCriteria(outputFields[0]?.path ?? "");

  const setEnabled = (checked: boolean) => {
    if (!checked) {
      updateCriteria(null);
      return;
    }
    updateCriteria({ ...ensureCriteria(), enabled: true });
  };

  const updateRules = (
    type: "success" | "failure",
    nextRules: ConditionRule[],
  ) => {
    const current = ensureCriteria();
    updateCriteria({
      ...current,
      enabled: true,
      businessSuccess:
        type === "success"
          ? { ...current.businessSuccess, allOf: nextRules }
          : current.businessSuccess,
      businessFailure:
        type === "failure"
          ? { ...current.businessFailure, anyOf: nextRules }
          : current.businessFailure,
    });
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between border-b pb-2">
        <div className="flex items-center gap-2 font-bold text-emerald-600">
          <ShieldCheckIcon className="size-4" />
          <span>3. 业务成功判定</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-[11px]">
            {enabled ? "已启用" : "未启用"}
          </span>
          <Switch
            checked={enabled}
            disabled={readOnly}
            onCheckedChange={setEnabled}
            aria-label="启用场景级业务成功判定"
          />
        </div>
      </div>

      <p className="text-muted-foreground text-xs">
        基于场景最终输出判定业务是否成功。失败规则优先短路，成功规则需要全部满足。
      </p>

      <div className={cn("space-y-4", (!enabled || readOnly) && "opacity-60")}>
        <RuleGroup
          tone="failure"
          title="失败规则"
          hint="任一命中即失败"
          rules={failureRules}
          outputFields={outputFields}
          disabled={!enabled || readOnly}
          onChange={(rules) => updateRules("failure", rules)}
        />
        <RuleGroup
          tone="success"
          title="成功规则"
          hint="全部满足才成功"
          rules={successRules}
          outputFields={outputFields}
          disabled={!enabled || readOnly}
          onChange={(rules) => updateRules("success", rules)}
        />
      </div>
    </section>
  );
}

function RuleGroup({
  tone,
  title,
  hint,
  rules,
  outputFields,
  disabled,
  onChange,
}: {
  tone: "success" | "failure";
  title: string;
  hint: string;
  rules: ConditionRule[];
  outputFields: ReturnType<typeof flattenSchema>;
  disabled?: boolean;
  onChange: (rules: ConditionRule[]) => void;
}) {
  const isFailure = tone === "failure";
  const firstPath = outputFields[0]?.path ?? "";
  const accent = isFailure
    ? "border-destructive/15 bg-destructive/[0.02]"
    : "border-emerald-500/15 bg-emerald-500/[0.02]";
  const badge = isFailure
    ? "bg-destructive/10 text-destructive"
    : "bg-emerald-500/10 text-emerald-700";

  return (
    <div className={cn("space-y-2 rounded-lg border p-3", accent)}>
      <div className="flex items-center gap-2">
        {isFailure ? (
          <XCircleIcon className="text-destructive size-3.5" />
        ) : (
          <CheckCircle2Icon className="size-3.5 text-emerald-600" />
        )}
        <span
          className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold", badge)}
        >
          {title}
        </span>
        <span className="text-muted-foreground text-[10px]">{hint}</span>
      </div>

      <div className="space-y-1.5">
        {rules.length === 0 ? (
          <div className="bg-background/70 text-muted-foreground rounded-md border border-dashed px-3 py-2 text-[11px]">
            暂未配置
          </div>
        ) : (
          rules.map((rule, index) => (
            <RuleRow
              key={`${tone}-${index}`}
              rule={rule}
              outputFields={outputFields}
              disabled={disabled}
              onChange={(nextRule) => {
                const next = [...rules];
                next[index] = nextRule;
                onChange(next);
              }}
              onDelete={() => onChange(rules.filter((_, i) => i !== index))}
            />
          ))
        )}
      </div>

      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={cn(
          "h-8 w-full border border-dashed text-xs",
          isFailure
            ? "border-destructive/20 text-destructive hover:bg-destructive/5"
            : "border-emerald-500/20 text-emerald-700 hover:bg-emerald-500/5",
        )}
        disabled={disabled}
        onClick={() =>
          onChange(
            rules.concat({
              path: firstPath,
              op: firstPath ? "NOT_EMPTY" : "EQ",
              value: firstPath ? undefined : "",
            }),
          )
        }
      >
        <PlusIcon className="mr-1 size-3" />
        新增{title}
      </Button>
    </div>
  );
}

function RuleRow({
  rule,
  outputFields,
  disabled,
  onChange,
  onDelete,
}: {
  rule: ConditionRule;
  outputFields: ReturnType<typeof flattenSchema>;
  disabled?: boolean;
  onChange: (rule: ConditionRule) => void;
  onDelete: () => void;
}) {
  const needsValue = !VALUELESS_OPERATORS.has(rule.op);

  return (
    <div className="bg-background grid grid-cols-[minmax(0,1fr)_132px_160px_32px] items-center gap-2 rounded-md border p-2">
      <div className="flex min-w-0 items-center gap-1.5">
        <Input
          className="h-8 min-w-0 font-mono text-xs"
          value={rule.path}
          disabled={disabled}
          placeholder="orderId"
          onChange={(event) => onChange({ ...rule, path: event.target.value })}
        />
        {outputFields.length > 0 && (
          <Select
            value={
              outputFields.some((field) => field.path === rule.path)
                ? rule.path
                : "__custom__"
            }
            disabled={disabled}
            onValueChange={(path) => {
              if (path === "__custom__") return;
              onChange({ ...rule, path });
            }}
          >
            <SelectTrigger className="h-8 w-[96px] text-[10px]">
              <SelectValue placeholder="字段" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__custom__" className="text-xs">
                手填表达式
              </SelectItem>
              {outputFields.map((field) => (
                <SelectItem
                  key={field.path}
                  value={field.path}
                  className="text-xs"
                >
                  {field.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      <Select
        value={rule.op}
        disabled={disabled}
        onValueChange={(op: ConditionOperator) => {
          const next: ConditionRule = { path: rule.path, op };
          if (!VALUELESS_OPERATORS.has(op)) {
            next.value = rule.value ?? "";
          }
          onChange(next);
        }}
      >
        <SelectTrigger className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {CONDITION_OPERATORS.map((operator) => (
            <SelectItem key={operator} value={operator} className="text-xs">
              {OPERATOR_LABELS[operator]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Input
        className="h-8 text-xs"
        value={needsValue ? formatRuleValue(rule.value) : ""}
        disabled={(disabled ?? false) || !needsValue}
        placeholder={needsValue ? "目标值" : "无需目标值"}
        onChange={(event) =>
          onChange({
            ...rule,
            value: parseRuleValue(event.target.value, rule.op),
          })
        }
      />

      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        disabled={disabled}
        onClick={onDelete}
        aria-label="删除业务判定规则"
      >
        <Trash2Icon className="size-3.5" />
      </Button>
    </div>
  );
}

function formatRuleValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function parseRuleValue(value: string, op: ConditionOperator): unknown {
  const trimmed = value.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (trimmed === "null") return null;
  if (op === "IN" || op === "NOT_IN") {
    try {
      const parsed = JSON.parse(trimmed);
      return Array.isArray(parsed) ? parsed : value;
    } catch {
      return value;
    }
  }
  return value;
}
