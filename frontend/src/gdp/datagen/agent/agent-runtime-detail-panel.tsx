import { FileJsonIcon, XIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

import type { AgentRuntimeTaskRunResponse } from "../common/lib/types";
import type { TimelineDetailItem } from "./agent-runtime-view-model";

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

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-all font-mono text-foreground">{value ?? "-"}</span>
    </div>
  );
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export function AgentRuntimeDetailPanel({
  taskRun,
  items,
  selectedKey,
  onSelect,
  open,
  onClose,
}: {
  taskRun: AgentRuntimeTaskRunResponse | null;
  items: TimelineDetailItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  open: boolean;
  onClose: () => void;
}) {
  const selectedItem = items.find((item) => item.key === selectedKey) ?? null;

  if (!open) return null;

  return (
    <aside className="flex min-h-0 w-[400px] flex-col border-l bg-muted/10">
      <div className="flex shrink-0 items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">运行细节</h2>
        <Button variant="ghost" size="icon" className="size-7" onClick={onClose}>
          <XIcon className="size-4" />
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 p-4">
          {taskRun ? (
            <section className="space-y-1.5 rounded-md border bg-background p-3">
              <InfoRow label="TaskRun" value={taskRun.task_run_id} />
              <InfoRow label="目标" value={taskRun.user_goal} />
              <InfoRow label="环境" value={taskRun.env_code} />
              <InfoRow label="状态" value={taskRun.status} />
              <InfoRow label="创建" value={formatTime(taskRun.created_at)} />
              <InfoRow label="更新" value={formatTime(taskRun.updated_at)} />
            </section>
          ) : null}

          {taskRun?.failure_reason ? (
            <Alert variant="destructive">
              <AlertTitle>失败原因</AlertTitle>
              <AlertDescription>{taskRun.failure_reason}</AlertDescription>
            </Alert>
          ) : null}

          <Separator />

          {/* 时间线条目列表 */}
          {items.length > 0 ? (
            <div className="space-y-1">
              {items.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => onSelect(item.key)}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left transition-colors",
                    selectedKey === item.key
                      ? "border-primary bg-primary/5"
                      : "bg-background hover:bg-muted/50",
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-xs font-medium">{item.title}</span>
                      {item.status ? (
                        <Badge variant="outline" className={cn("text-[10px]", statusTone(item.status))}>
                          {item.status}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{item.subtitle}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <Alert>
              <FileJsonIcon className="size-4" />
              <AlertTitle>暂无记录</AlertTitle>
              <AlertDescription>启动 TaskRun 后显示运行账本。</AlertDescription>
            </Alert>
          )}

          <Separator />

          {/* 选中条目的 JSON 详情 */}
          {selectedItem ? (
            <section className="space-y-2">
              <div>
                <div className="text-[11px] font-semibold uppercase text-muted-foreground">{selectedItem.kind}</div>
                <h3 className="mt-1 text-sm font-medium">{selectedItem.title}</h3>
                <p className="mt-0.5 break-words text-xs text-muted-foreground">{selectedItem.subtitle}</p>
              </div>
              <pre className="max-h-[400px] overflow-auto rounded-md border bg-background p-3 text-xs leading-5">
                {formatJson(selectedItem.payload)}
              </pre>
            </section>
          ) : null}
        </div>
      </ScrollArea>
    </aside>
  );
}
