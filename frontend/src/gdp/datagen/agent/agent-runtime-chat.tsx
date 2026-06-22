import { BotIcon, GitBranchIcon, Loader2Icon, SendIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import type { AgentRuntimeSceneCandidate, SceneSummary } from "../common/lib/types";
import { ActionCard } from "./agent-runtime-action-cards";
import { AgentRuntimeMessage } from "./agent-runtime-message";
import type { AgentRuntimePresetId, AgentRuntimeStartPreset } from "./agent-runtime-presets";
import { AgentRuntimeResultCard } from "./agent-runtime-result-card";
import type { ChatMessage, CompletionResult, WaitingInteraction } from "./agent-runtime-view-model";

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
  presets,
  selectedPresetId,
  onApplyPreset,
  scenes,
  selectedSceneCode,
  selectedSceneName,
  inputsText,
  onSceneCodeChange,
  onInputsTextChange,
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
  presets: AgentRuntimeStartPreset[];
  selectedPresetId: AgentRuntimePresetId | null;
  onApplyPreset: (presetId: AgentRuntimePresetId) => void;
  scenes: SceneSummary[];
  selectedSceneCode: string | null;
  selectedSceneName: string | null;
  inputsText: string;
  onSceneCodeChange: (sceneCode: string | null) => void;
  onInputsTextChange: (value: string) => void;
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
            <div className="space-y-4 py-12">
              <div className="flex flex-col items-center justify-center text-center">
                <BotIcon className="size-12 text-muted-foreground/50" />
                <h3 className="mt-4 text-lg font-medium">GDP Agent 运行台</h3>
                <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                  选择验收入口后发起任务；MVP3 入口由 Planner 串联多个已发布 Scene。
                </p>
              </div>
              <div className="rounded-md border bg-card p-3">
                <div className="mb-2 flex items-center gap-2 text-xs">
                  <GitBranchIcon className="size-3.5 text-muted-foreground" />
                  <span className="font-medium">验收入口</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {presets.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => onApplyPreset(preset.id)}
                      className={cn(
                        "flex min-h-[72px] flex-col items-start justify-between gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors",
                        selectedPresetId === preset.id
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border hover:bg-muted/60",
                      )}
                    >
                      <span className="flex w-full items-center justify-between gap-2">
                        <span className="font-medium">{preset.label}</span>
                        <Badge variant="outline" className="shrink-0 text-[10px]">
                          {preset.badge}
                        </Badge>
                      </span>
                      <span className="line-clamp-2 text-muted-foreground">{preset.description}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="rounded-md border bg-card p-3">
                <div className="mb-2 flex items-center gap-2 text-xs">
                  <span className="font-medium">场景</span>
                  {selectedSceneCode ? (
                    <Badge variant="outline" className="text-[10px]">
                      {selectedSceneCode}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-[10px]">
                      Planner 多 Scene
                    </Badge>
                  )}
                  {selectedSceneName ? (
                    <span className="min-w-0 truncate text-muted-foreground">{selectedSceneName}</span>
                  ) : null}
                </div>
                <div className="max-h-40 overflow-auto rounded-md border bg-muted/20 p-1">
                  {scenes.map((scene) => (
                    <button
                      key={scene.sceneCode}
                      type="button"
                      onClick={() => onSceneCodeChange(scene.sceneCode)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left text-xs transition-colors",
                        selectedSceneCode === scene.sceneCode
                          ? "bg-primary/10 text-foreground"
                          : "hover:bg-muted/60",
                      )}
                    >
                      <span className="min-w-0 truncate">{scene.sceneName}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">{scene.sceneCode}</span>
                    </button>
                  ))}
                </div>
              </div>
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
            <div className="space-y-2">
              <Textarea
                value={inputsText}
                onChange={(e) => onInputsTextChange(e.target.value)}
                placeholder="输入场景参数 JSON"
                className="min-h-[110px] resize-none font-mono text-xs"
              />
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
