import { XCircleIcon, XIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { AgentRuntimeTaskRunResponse } from "../common/lib/types";
import { AgentRuntimeAuditPanel } from "./agent-runtime-audit-panel";
import type {
  AuditDecision,
  AuditExecution,
  AuditStep,
} from "./agent-runtime-view-model";

function statusTone(status?: string) {
  switch (status) {
    case "COMPLETED":
    case "DONE":
    case "SUCCEEDED":
    case "SUCCESS":
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
      return "border-sky-200 bg-sky-50 text-sky-700";
    default:
      return "border-border bg-muted/40 text-muted-foreground";
  }
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// ── 详情面板主组件 ──────────────────────────────────────────────────────

export function AgentRuntimeDetailPanel({
  taskRun,
  decisions,
  steps,
  executions,
  open,
  onClose,
}: {
  taskRun: AgentRuntimeTaskRunResponse | null;
  decisions: AuditDecision[];
  steps: AuditStep[];
  executions: AuditExecution[];
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <aside className="flex min-h-0 w-[440px] flex-col border-l bg-muted/10">
      <div className="flex shrink-0 items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">运行审计</h2>
        <Button variant="ghost" size="icon" className="size-7" onClick={onClose}>
          <XIcon className="size-4" />
        </Button>
      </div>

      {/* TaskRun 摘要 */}
      {taskRun ? (
        <div className="shrink-0 border-b p-3">
          <section className="space-y-1 rounded-lg border bg-background p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[11px] text-muted-foreground">
                {taskRun.task_run_id.slice(0, 12)}
              </span>
              <Badge variant="outline" className={cn("text-[10px]", statusTone(taskRun.status))}>
                {taskRun.status}
              </Badge>
            </div>
            <p className="font-medium">{taskRun.user_goal}</p>
            <div className="flex items-center gap-2 text-muted-foreground">
              <span>{taskRun.env_code ?? "-"}</span>
              <span className="text-border">·</span>
              <span>{formatTime(taskRun.created_at)}</span>
            </div>
          </section>

          {taskRun.failure_reason ? (
            <Alert variant="destructive" className="mt-2 text-xs">
              <XCircleIcon className="size-4" />
              <AlertTitle>失败原因</AlertTitle>
              <AlertDescription>{taskRun.failure_reason}</AlertDescription>
            </Alert>
          ) : null}
        </div>
      ) : null}

      {/* 三层审计面板 */}
      <AgentRuntimeAuditPanel
        decisions={decisions}
        steps={steps}
        executions={executions}
      />
    </aside>
  );
}
