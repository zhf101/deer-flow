import { BotIcon, Loader2Icon, SendIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { ActionCard } from "./agent-runtime-action-cards";
import { AgentRuntimeMessage } from "./agent-runtime-message";
import { AgentRuntimeResultCard } from "./agent-runtime-result-card";
import type { ChatMessage, CompletionResult, WaitingInteraction } from "./agent-runtime-view-model";
import type { AgentRuntimeSceneCandidate } from "../common/lib/types";

export function AgentRuntimeChat({
  messages,
  interaction,
  completionResult,
  busy,
  canStart,
  onStart,
  onSelectCandidate,
  onApprove,
  onCancel,
  onSupplySceneCode,
  onSupplyInput,
  onConfirmUnknownState,
  onViewAttempts,
  onViewDetails,
  userGoal,
  onUserGoalChange,
}: {
  messages: ChatMessage[];
  interaction: WaitingInteraction | null;
  completionResult: CompletionResult | null;
  busy: boolean;
  canStart: boolean;
  onStart: () => void;
  onSelectCandidate: (candidate: AgentRuntimeSceneCandidate, approved: boolean) => void;
  onApprove: () => void;
  onCancel: () => void;
  onSupplySceneCode: (sceneCode: string) => void;
  onSupplyInput: (inputs: Record<string, unknown>) => void;
  onConfirmUnknownState: () => void;
  onViewAttempts: () => void;
  onViewDetails?: () => void;
  userGoal: string;
  onUserGoalChange: (value: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, interaction, completionResult]);

  const hasMessages = messages.length > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ScrollArea className="min-h-0 flex-1">
        <div ref={scrollRef} className="mx-auto max-w-3xl space-y-4 px-4 py-6">
          {!hasMessages ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <BotIcon className="size-12 text-muted-foreground/50" />
              <h3 className="mt-4 text-lg font-medium">GDP Agent 运行台</h3>
              <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                输入造数目标，选择环境，Agent 会自动搜索并执行匹配的场景。
              </p>
            </div>
          ) : (
            messages.map((message) => <AgentRuntimeMessage key={message.id} message={message} />)
          )}

          {completionResult ? (
            <AgentRuntimeResultCard result={completionResult} onViewDetails={onViewDetails} />
          ) : null}

          {interaction ? (
            <div className="space-y-2">
              <ActionCard
                interaction={interaction}
                busy={busy}
                onSelectCandidate={onSelectCandidate}
                onApprove={onApprove}
                onCancel={onCancel}
                onSupplySceneCode={onSupplySceneCode}
                onSupplyInput={onSupplyInput}
                onConfirmUnknownState={onConfirmUnknownState}
                onViewAttempts={onViewAttempts}
              />
            </div>
          ) : null}

          {busy && !interaction ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              正在处理...
            </div>
          ) : null}
        </div>
      </ScrollArea>

      {/* 底部输入区 */}
      <div className="shrink-0 border-t bg-background">
        <div className="mx-auto max-w-3xl px-4 py-4">
          {!hasMessages ? (
            <div className="flex gap-2">
              <Textarea
                value={userGoal}
                onChange={(e) => onUserGoalChange(e.target.value)}
                placeholder="输入造数目标，例如：造一笔已支付订单"
                className="min-h-[60px] resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canStart && !busy) {
                    e.preventDefault();
                    onStart();
                  }
                }}
              />
              <Button onClick={onStart} disabled={!canStart || busy} className="self-end">
                {busy ? (
                  <Loader2Icon className="mr-1.5 size-4 animate-spin" />
                ) : (
                  <SendIcon className="mr-1.5 size-4" />
                )}
                发起
              </Button>
            </div>
          ) : (
            <div className="text-center text-xs text-muted-foreground">
              按 Cmd/Ctrl + Enter 快速发起新任务
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
