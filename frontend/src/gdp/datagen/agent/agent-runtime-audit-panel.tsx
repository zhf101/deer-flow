import {
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  CircleIcon,
  ClockIcon,
  DatabaseIcon,
  ExternalLinkIcon,
  ListChecksIcon,
  ListOrderedIcon,
  Loader2Icon,
  SearchIcon,
  ShieldCheckIcon,
  XCircleIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { getSceneRun } from "../common/lib/api";
import type {
  AgentRuntimeVariable,
  ExecutionResult,
} from "../common/lib/types";

import { AgentRuntimeSceneRunDetail } from "./agent-runtime-scene-run-detail";
import type {
  AuditDecision,
  AuditExecution,
  AuditStep,
  ResourceGapTreeNode,
} from "./agent-runtime-view-model";

// ── 工具函数 ─────────────────────────────────────────────────────────────

function sourceTone(source: string) {
  switch (source) {
    case "USER":
      return "border-sky-200 bg-sky-50 text-sky-700";
    case "RULE":
      return "border-violet-200 bg-violet-50 text-violet-700";
    case "CATALOG":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "LLM":
      return "border-amber-200 bg-amber-50 text-amber-700";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

function sourceLabel(source: string) {
  switch (source) {
    case "USER":
      return "用户";
    case "RULE":
      return "规则";
    case "CATALOG":
      return "目录";
    case "LLM":
      return "LLM";
    case "SYSTEM_DEFAULT":
      return "系统";
    default:
      return source;
  }
}

function kindLabel(kind: string) {
  switch (kind) {
    case "SCENE_SEARCH":
      return "场景搜索";
    case "SCENE_SELECTION":
      return "场景选择";
    case "SCENE_CREATION":
      return "场景创建";
    case "APPROVAL_REQUIREMENT":
      return "审批";
    case "STEP_TYPE_SELECTION":
      return "步骤类型";
    case "STEP_ORDERING":
      return "步骤排序";
    case "RECOVERY_SELECTION":
      return "恢复选择";
    default:
      return kind;
  }
}

function statusTone(status?: string) {
  switch (status) {
    case "DONE":
    case "SUCCEEDED":
    case "SUCCESS":
    case "COMPLETED":
    case "SATISFIED":
    case "DECIDED":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "FAILED":
    case "CANCELLED":
      return "border-destructive/30 bg-destructive/10 text-destructive";
    case "WAITING_USER":
    case "BLOCKED":
    case "UNKNOWN_STATE":
    case "NEED_USER":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "RUNNING":
    case "RESOLVING":
      return "border-sky-200 bg-sky-50 text-sky-700";
    case "PENDING":
      return "border-muted bg-muted/50 text-muted-foreground";
    default:
      return "border-border bg-muted/40 text-muted-foreground";
  }
}

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatDuration(ms?: number) {
  if (ms === undefined || ms === null) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

// ── 决策 Tab ─────────────────────────────────────────────────────────────

function DecisionCard({ decision }: { decision: AuditDecision }) {
  const [open, setOpen] = useState(true);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="bg-background hover:bg-muted/50 flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left transition-colors">
        <div className="mt-0.5 shrink-0">
          {open ? (
            <ChevronDownIcon className="text-muted-foreground size-3.5" />
          ) : (
            <ChevronRightIcon className="text-muted-foreground size-3.5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <Badge
              variant="outline"
              className={cn(
                "px-1 py-0 text-[9px]",
                sourceTone(decision.source),
              )}
            >
              {sourceLabel(decision.source)}
            </Badge>
            <span className="text-muted-foreground text-[10px]">
              {kindLabel(decision.kind)}
            </span>
          </div>
          <p className="mt-1 text-xs leading-snug font-medium">
            {decision.summary}
          </p>
          <div className="text-muted-foreground mt-1 flex items-center gap-2 text-[10px]">
            <span>{decision.options.length} 个候选</span>
            {decision.selected ? (
              <>
                <span className="text-border">·</span>
                <span className="text-emerald-600">
                  选中 {decision.selected.label}
                </span>
              </>
            ) : null}
          </div>
        </div>
      </CollapsibleTrigger>

      <CollapsibleContent className="mt-1 ml-5 space-y-2">
        {/* 候选列表 */}
        {decision.options.length > 0 ? (
          <div className="space-y-1">
            <div className="text-muted-foreground text-[10px] font-semibold">
              候选项
            </div>
            {decision.options.map((opt) => {
              const isSelected = decision.selected?.option_id === opt.option_id;
              const rejection = decision.rejections.find(
                (r) => r.option_id === opt.option_id,
              );
              return (
                <div
                  key={opt.option_id}
                  className={cn(
                    "rounded-md border px-2.5 py-1.5 text-xs",
                    isSelected
                      ? "border-emerald-300 bg-emerald-50/50"
                      : rejection
                        ? "border-border/60 bg-muted/20 opacity-60"
                        : "border-border bg-background",
                  )}
                >
                  <div className="flex items-center gap-2">
                    {isSelected ? (
                      <CheckCircle2Icon className="size-3 shrink-0 text-emerald-500" />
                    ) : rejection ? (
                      <XCircleIcon className="text-muted-foreground size-3 shrink-0" />
                    ) : (
                      <CircleIcon className="text-muted-foreground size-3 shrink-0" />
                    )}
                    <span className="font-medium">{opt.label}</span>
                    {opt.score !== null && opt.score !== undefined ? (
                      <span className="text-muted-foreground ml-auto flex items-center gap-1 text-[10px]">
                        评分
                        <span className="text-foreground font-mono font-semibold">
                          {opt.score.toFixed(2)}
                        </span>
                      </span>
                    ) : null}
                  </div>
                  {opt.reasons.length > 0 ? (
                    <ul className="text-muted-foreground mt-1 ml-5 list-disc space-y-0.5 text-[10px]">
                      {opt.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  ) : null}
                  {isSelected && decision.selectedReasons.length > 0 ? (
                    <div className="mt-1.5 ml-5">
                      <div className="text-[10px] font-medium text-emerald-700">
                        选中原因
                      </div>
                      <ul className="mt-0.5 list-disc space-y-0.5 text-[10px] text-emerald-700/80">
                        {decision.selectedReasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {rejection ? (
                    <div className="text-muted-foreground mt-1 ml-5 text-[10px]">
                      未选原因：{rejection.reason}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}

        {/* 判断标准 */}
        {decision.criteria.length > 0 ? (
          <div className="space-y-1">
            <div className="text-muted-foreground text-[10px] font-semibold">
              判断标准
            </div>
            <ul className="text-muted-foreground ml-4 list-disc space-y-0.5 text-[10px]">
              {decision.criteria.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function DecisionTab({ decisions }: { decisions: AuditDecision[] }) {
  if (decisions.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center text-xs">
        <SearchIcon className="text-muted-foreground/40 mx-auto size-5" />
        <p className="mt-2">暂无决策记录</p>
        <p className="mt-1 text-[10px]">启动任务后将显示场景搜索和选择过程</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {decisions.map((d) => (
        <DecisionCard key={d.decision_id} decision={d} />
      ))}
    </div>
  );
}

// ── 编排 Tab ─────────────────────────────────────────────────────────────

function StepCard({ step }: { step: AuditStep }) {
  const [open, setOpen] = useState(true);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        className={cn(
          "flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors",
          step.isActive
            ? "border-sky-300 bg-sky-50/40 ring-1 ring-sky-200 hover:bg-sky-50/60"
            : "bg-background hover:bg-muted/50",
        )}
      >
        {open ? (
          <ChevronDownIcon className="text-muted-foreground size-3.5" />
        ) : (
          <ChevronRightIcon className="text-muted-foreground size-3.5" />
        )}
        <span
          className={cn(
            "flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
            step.isActive
              ? "text-primary-foreground bg-sky-500 shadow-sm"
              : "bg-muted",
          )}
        >
          {step.stepNo}
        </span>
        <span className="min-w-0 flex-1 truncate text-xs font-medium">
          {step.goal}
        </span>
        <Badge
          variant="outline"
          className={cn(
            "shrink-0 px-1 py-0 text-[9px]",
            statusTone(step.status),
          )}
        >
          {step.status}
        </Badge>
      </CollapsibleTrigger>

      <CollapsibleContent className="mt-1 ml-9 space-y-2">
        {step.dependsOn.length > 0 ? (
          <div>
            <div className="text-muted-foreground text-[10px] font-semibold">
              依赖步骤
            </div>
            <div className="mt-0.5 flex flex-wrap gap-1">
              {step.dependsOn.map((dep) => (
                <Badge key={dep} variant="outline" className="text-[10px]">
                  {dep}
                </Badge>
              ))}
            </div>
            {step.incomingEdges && step.incomingEdges.length > 0 ? (
              <div className="mt-1 space-y-1">
                {step.incomingEdges.map((edge, idx) => (
                  <div
                    key={idx}
                    className="text-muted-foreground bg-muted/20 flex flex-wrap items-center gap-1.5 rounded border border-dashed p-1.5 text-[10px]"
                  >
                    <span className="font-medium">
                      来自步骤 {edge.fromStepId}:
                    </span>
                    {edge.variableIds.length > 0 ? (
                      edge.variableIds.map((v) => (
                        <Badge
                          key={v}
                          variant="secondary"
                          className="h-4 px-1 py-0 text-[9px]"
                        >
                          {v}
                        </Badge>
                      ))
                    ) : (
                      <span className="italic">仅控制流</span>
                    )}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {step.consumes.length > 0 ? (
          <div>
            <div className="text-muted-foreground text-[10px] font-semibold">
              输入变量
            </div>
            <div className="mt-0.5 flex flex-wrap gap-1">
              {step.consumes.map((v) => (
                <Badge
                  key={v}
                  variant="outline"
                  className="font-mono text-[10px]"
                >
                  {v}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {step.produces.length > 0 ? (
          <div>
            <div className="text-muted-foreground text-[10px] font-semibold">
              输出变量
            </div>
            <div className="mt-0.5 flex flex-wrap gap-1">
              {step.produces.map((v) => (
                <Badge
                  key={v}
                  variant="outline"
                  className="font-mono text-[10px]"
                >
                  {v}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}

        {!step.dependsOn.length &&
        !step.consumes.length &&
        !step.produces.length ? (
          <p className="text-muted-foreground text-[10px] italic">
            无依赖和变量信息
          </p>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function layerLabel(layer: string) {
  switch (layer) {
    case "SCENE":
      return "场景缺口";
    case "SOURCE":
      return "Source 缺口";
    case "INFRA":
      return "基础配置缺口";
    default:
      return layer;
  }
}

function ResourceGapNode({
  node,
  depth = 0,
}: {
  node: ResourceGapTreeNode;
  depth?: number;
}) {
  const { requirement, proposal } = node;
  const sceneCount = proposal?.candidates.length ?? 0;
  const sourceCount = proposal?.source_candidates.length ?? 0;
  const infraCount = proposal?.infra_candidates.length ?? 0;
  const missingFields =
    proposal?.infra_candidates.flatMap((item) => item.missing_fields) ?? [];

  return (
    <div className={cn("space-y-1.5", depth > 0 && "ml-4 border-l pl-3")}>
      <div className="bg-background rounded-md border px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className={cn(
              "px-1 py-0 text-[9px]",
              statusTone(requirement.status),
            )}
          >
            {requirement.status}
          </Badge>
          <span className="font-medium">{layerLabel(requirement.layer)}</span>
          <span className="text-muted-foreground min-w-0 flex-1 truncate">
            {requirement.goal}
          </span>
        </div>
        <div className="text-muted-foreground mt-1 flex flex-wrap gap-1 text-[10px]">
          {sceneCount > 0 ? (
            <Badge variant="secondary" className="h-4 px-1 text-[9px]">
              Scene {sceneCount}
            </Badge>
          ) : null}
          {sourceCount > 0 ? (
            <Badge variant="secondary" className="h-4 px-1 text-[9px]">
              Source {sourceCount}
            </Badge>
          ) : null}
          {infraCount > 0 ? (
            <Badge variant="secondary" className="h-4 px-1 text-[9px]">
              Infra {infraCount}
            </Badge>
          ) : null}
          {missingFields.length > 0 ? (
            <span className="text-amber-700">
              仍缺：{Array.from(new Set(missingFields)).join("，")}
            </span>
          ) : null}
        </div>
      </div>
      {node.children.length > 0 ? (
        <div className="space-y-1.5">
          {node.children.map((child) => (
            <ResourceGapNode
              key={child.requirement.requirement_id}
              node={child}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ResourceGapTree({ trees }: { trees: ResourceGapTreeNode[] }) {
  if (trees.length === 0) return null;
  return (
    <div className="bg-muted/20 space-y-2 rounded-md border border-dashed p-2.5">
      <div className="text-muted-foreground text-[10px] font-semibold">
        资源缺口树
      </div>
      {trees.map((node) => (
        <ResourceGapNode key={node.requirement.requirement_id} node={node} />
      ))}
    </div>
  );
}

function formatFactValue(value: unknown) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  )
    return `${value}`;
  if (typeof value === "symbol") return value.description ?? "[symbol]";
  if (typeof value === "function") return "[function]";
  try {
    return JSON.stringify(value);
  } catch {
    return "[unserializable]";
  }
}
function OrchestrationTab({
  steps,
  resourceGapTrees,
}: {
  steps: AuditStep[];
  resourceGapTrees: ResourceGapTreeNode[];
}) {
  if (steps.length === 0 && resourceGapTrees.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center text-xs">
        <ListOrderedIcon className="text-muted-foreground/40 mx-auto size-5" />
        <p className="mt-2">暂无编排信息</p>
        <p className="mt-1 text-[10px]">启动任务后将显示步骤规划</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <ResourceGapTree trees={resourceGapTrees} />
      {steps.map((s) => (
        <StepCard key={s.stepId} step={s} />
      ))}
    </div>
  );
}

// ── 执行 Tab ─────────────────────────────────────────────────────────────

function SceneRunLoader({ sceneRunId }: { sceneRunId: string }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (loaded) return;
    setLoading(true);
    try {
      const data = await getSceneRun(sceneRunId);
      setResult(data);
      setLoaded(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载场景运行失败");
    } finally {
      setLoading(false);
    }
  }, [sceneRunId, loaded]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="text-muted-foreground flex items-center gap-2 rounded-md border border-dashed p-3 text-xs">
        <Loader2Icon className="size-3.5 animate-spin" />
        加载场景运行 {sceneRunId.slice(0, 8)}...
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="space-y-1.5">
      <div className="text-muted-foreground flex items-center gap-1.5 text-[10px] font-semibold">
        <ExternalLinkIcon className="size-3" />
        场景运行详情
      </div>
      <AgentRuntimeSceneRunDetail result={result} />
    </div>
  );
}

function ExecutionCard({ execution }: { execution: AuditExecution }) {
  const [open, setOpen] = useState(true);
  const { action, attempts, evidence, verdict } = execution;

  const factsPassed = evidence?.facts.filter((f) => f.passed).length ?? 0;
  const factsFailed = evidence?.facts.filter((f) => !f.passed).length ?? 0;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="bg-background hover:bg-muted/50 flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors">
        {open ? (
          <ChevronDownIcon className="text-muted-foreground size-3.5" />
        ) : (
          <ChevronRightIcon className="text-muted-foreground size-3.5" />
        )}
        <DatabaseIcon className="text-muted-foreground size-3.5" />
        <span className="min-w-0 flex-1 truncate text-xs font-medium">
          {action.scene_code}
        </span>
        <Badge
          variant="outline"
          className={cn(
            "shrink-0 px-1 py-0 text-[9px]",
            statusTone(action.status),
          )}
        >
          {action.status}
        </Badge>
      </CollapsibleTrigger>

      <CollapsibleContent className="mt-1 ml-5 space-y-3">
        {/* 输入预览 */}
        {Object.keys(action.input_preview).length > 0 ? (
          <details className="group">
            <summary className="text-muted-foreground hover:text-foreground flex cursor-pointer items-center gap-1 text-[10px] font-semibold">
              <span className="text-muted-foreground/50 transition-transform group-open:rotate-90">
                ▶
              </span>
              输入参数
            </summary>
            <pre className="bg-muted/30 mt-1 max-h-[150px] overflow-auto rounded border p-2 text-[10px] leading-4">
              {formatJson(action.input_preview)}
            </pre>
          </details>
        ) : null}

        {/* Attempt 详情 */}
        {attempts.length > 0
          ? attempts.map((attempt) => {
              const attemptDuration =
                attempt.started_at && attempt.finished_at
                  ? new Date(attempt.finished_at).getTime() -
                    new Date(attempt.started_at).getTime()
                  : undefined;
              return (
                <div
                  key={attempt.attempt_id}
                  className="bg-muted/10 space-y-2 rounded-md border p-2.5"
                >
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="font-semibold">
                      Attempt #{attempt.attempt_no}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "px-1 py-0 text-[9px]",
                        statusTone(attempt.status),
                      )}
                    >
                      {attempt.status}
                    </Badge>
                    {attemptDuration !== undefined ? (
                      <span className="text-muted-foreground flex items-center gap-0.5">
                        <ClockIcon className="size-2.5" />
                        {formatDuration(attemptDuration)}
                      </span>
                    ) : null}
                  </div>
                  {attempt.error_message ? (
                    <div className="bg-destructive/10 text-destructive rounded px-2 py-1 text-[10px]">
                      {attempt.error_type ? (
                        <span className="font-semibold">
                          {attempt.error_type}:{" "}
                        </span>
                      ) : null}
                      {attempt.error_message}
                    </div>
                  ) : null}

                  {/* 场景运行下钻 */}
                  {attempt.scene_run_id ? (
                    <SceneRunLoader sceneRunId={attempt.scene_run_id} />
                  ) : null}
                </div>
              );
            })
          : null}

        {/* Evidence 事实表 */}
        {evidence && evidence.facts.length > 0 ? (
          <div className="space-y-1">
            <div className="text-muted-foreground flex items-center gap-2 text-[10px] font-semibold">
              <ListChecksIcon className="size-3" />
              事实判定
              <span className="text-emerald-600">{factsPassed} 通过</span>
              {factsFailed > 0 ? (
                <span className="text-destructive">{factsFailed} 未通过</span>
              ) : null}
            </div>
            <div className="overflow-hidden rounded-md border">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="bg-muted/40 border-b">
                    <th className="text-muted-foreground px-2 py-1 text-left font-medium">
                      事实
                    </th>
                    <th className="text-muted-foreground px-2 py-1 text-left font-medium">
                      期望
                    </th>
                    <th className="text-muted-foreground px-2 py-1 text-left font-medium">
                      实际
                    </th>
                    <th className="text-muted-foreground w-8 px-2 py-1 text-center font-medium">
                      结果
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.facts.map((fact, i) => (
                    <tr key={i} className="border-b last:border-b-0">
                      <td className="px-2 py-1">
                        <span className="font-mono">{fact.subject}</span>
                        <span className="text-muted-foreground ml-1">
                          {fact.predicate}
                        </span>
                        {fact.detail ? (
                          <div className="text-muted-foreground mt-0.5">
                            {fact.detail}
                          </div>
                        ) : null}
                      </td>
                      <td className="text-muted-foreground px-2 py-1 font-mono">
                        {formatFactValue(fact.expected)}
                      </td>
                      <td className="px-2 py-1 font-mono">
                        {formatFactValue(fact.actual)}
                      </td>
                      <td className="px-2 py-1 text-center">
                        {fact.passed ? (
                          <CheckCircle2Icon className="mx-auto size-3 text-emerald-500" />
                        ) : (
                          <XCircleIcon className="text-destructive mx-auto size-3" />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {evidence.missing_facts.length > 0 ? (
              <div className="text-[10px] text-amber-600">
                缺失事实：{evidence.missing_facts.join("、")}
              </div>
            ) : null}
            {evidence.unknown_facts.length > 0 ? (
              <div className="text-muted-foreground text-[10px]">
                未知事实：{evidence.unknown_facts.join("、")}
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Verdict */}
        {verdict ? (
          <div
            className={cn(
              "rounded-md border px-2.5 py-2 text-xs",
              verdict.verdict_type === "DONE"
                ? "border-emerald-200 bg-emerald-50"
                : verdict.verdict_type === "FAILED"
                  ? "border-destructive/30 bg-destructive/5"
                  : "border-amber-200 bg-amber-50",
            )}
          >
            <div className="flex items-center gap-2">
              <ShieldCheckIcon
                className={cn(
                  "size-3.5",
                  verdict.verdict_type === "DONE"
                    ? "text-emerald-600"
                    : verdict.verdict_type === "FAILED"
                      ? "text-destructive"
                      : "text-amber-600",
                )}
              />
              <span className="font-semibold">
                {verdict.verdict_type === "DONE"
                  ? "判定通过"
                  : verdict.verdict_type === "FAILED"
                    ? "判定失败"
                    : "结果未知"}
              </span>
            </div>
            <p className="text-muted-foreground mt-1 text-[10px]">
              {verdict.reason}
            </p>
          </div>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}

function ExecutionTab({ executions }: { executions: AuditExecution[] }) {
  if (executions.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center text-xs">
        <DatabaseIcon className="text-muted-foreground/40 mx-auto size-5" />
        <p className="mt-2">暂无执行记录</p>
        <p className="mt-1 text-[10px]">
          场景执行后将显示详细的请求/响应和判定结果
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {executions.map((e) => (
        <ExecutionCard key={e.action.action_id} execution={e} />
      ))}
    </div>
  );
}

function VariableTab({ variables }: { variables: AgentRuntimeVariable[] }) {
  if (variables.length === 0) {
    return (
      <div className="text-muted-foreground py-8 text-center text-xs">
        <DatabaseIcon className="text-muted-foreground/40 mx-auto size-5" />
        <p className="mt-2">暂无变量</p>
        <p className="mt-1 text-[10px]">步骤执行产出的变量将在这里展示</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {variables.map((v) => (
        <div
          key={v.variable_id}
          className="bg-background rounded-md border p-3 text-xs"
        >
          <div className="flex items-center gap-2">
            <span className="font-semibold">{v.name}</span>
            <Badge variant="outline" className="h-4 px-1 py-0 text-[10px]">
              {v.semantic_type}
            </Badge>
            {v.tainted ? (
              <Badge variant="destructive" className="h-4 px-1 py-0 text-[9px]">
                污染 (Tainted)
              </Badge>
            ) : null}
            {v.sensitive ? (
              <Badge variant="secondary" className="h-4 px-1 py-0 text-[9px]">
                敏感
              </Badge>
            ) : null}
          </div>
          <div className="text-muted-foreground mt-2 text-[10px]">
            <div>
              <span className="font-medium">来源: </span>
              {v.provenance.source_type} ({v.provenance.source_id})
            </div>
            {v.consumed_by.length > 0 ? (
              <div className="mt-0.5">
                <span className="font-medium">被消费: </span>
                {v.consumed_by.join(", ")}
              </div>
            ) : null}
          </div>
          <div className="bg-muted/40 mt-2 rounded p-2 font-mono text-[10px] break-all">
            {formatJson(v.value_preview)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── 主组件 ───────────────────────────────────────────────────────────────

export function AgentRuntimeAuditPanel({
  decisions,
  steps,
  executions,
  variables,
  resourceGapTrees,
}: {
  decisions: AuditDecision[];
  steps: AuditStep[];
  executions: AuditExecution[];
  variables: AgentRuntimeVariable[];
  resourceGapTrees: ResourceGapTreeNode[];
}) {
  const [activeTab, setActiveTab] = useState<string>("decisions");

  // 当数据首次到达时自动切到有数据的 Tab
  useEffect(() => {
    if (activeTab === "decisions" && decisions.length === 0) {
      if (executions.length > 0) setActiveTab("execution");
      else if (steps.length > 0) setActiveTab("orchestration");
    }
  }, [decisions.length, steps.length, executions.length, activeTab]);

  return (
    <Tabs
      value={activeTab}
      onValueChange={setActiveTab}
      className="flex min-h-0 flex-1 flex-col"
    >
      <TabsList
        variant="line"
        className="w-full shrink-0 gap-0 rounded-none border-b px-2"
      >
        <TabsTrigger value="decisions" className="flex-1 gap-1 text-[11px]">
          <SearchIcon className="size-3" />
          决策
          {decisions.length > 0 ? (
            <Badge
              variant="outline"
              className="ml-1 h-3.5 px-1 py-0 text-[9px]"
            >
              {decisions.length}
            </Badge>
          ) : null}
        </TabsTrigger>
        <TabsTrigger value="orchestration" className="flex-1 gap-1 text-[11px]">
          <ListOrderedIcon className="size-3" />
          编排
          {steps.length > 0 ? (
            <Badge
              variant="outline"
              className="ml-1 h-3.5 px-1 py-0 text-[9px]"
            >
              {steps.length}
            </Badge>
          ) : null}
        </TabsTrigger>
        <TabsTrigger value="execution" className="flex-1 gap-1 text-[11px]">
          <DatabaseIcon className="size-3" />
          执行
          {executions.length > 0 ? (
            <Badge
              variant="outline"
              className="ml-1 h-3.5 px-1 py-0 text-[9px]"
            >
              {executions.length}
            </Badge>
          ) : null}
        </TabsTrigger>
        <TabsTrigger value="variables" className="flex-1 gap-1 text-[11px]">
          <ListChecksIcon className="size-3" />
          变量
          {variables?.length > 0 ? (
            <Badge
              variant="outline"
              className="ml-1 h-3.5 px-1 py-0 text-[9px]"
            >
              {variables.length}
            </Badge>
          ) : null}
        </TabsTrigger>
      </TabsList>

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-3">
          <TabsContent value="decisions" className="m-0">
            <DecisionTab decisions={decisions} />
          </TabsContent>
          <TabsContent value="orchestration" className="m-0">
            <OrchestrationTab
              steps={steps}
              resourceGapTrees={resourceGapTrees}
            />
          </TabsContent>
          <TabsContent value="execution" className="m-0">
            <ExecutionTab executions={executions} />
          </TabsContent>
          <TabsContent value="variables" className="m-0">
            <VariableTab variables={variables || []} />
          </TabsContent>
        </div>
      </ScrollArea>
    </Tabs>
  );
}
