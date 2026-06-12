import { BotIcon, UserIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import type { ChatMessage } from "./agent-runtime-view-model";

function formatTime(timestamp: string) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function AgentRuntimeMessage({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isError = message.content.includes("失败") || message.content.includes("未知");

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        {isUser ? <UserIcon className="size-4" /> : <BotIcon className="size-4" />}
      </div>
      <div className={cn("min-w-0 max-w-[75%] space-y-1", isUser ? "items-end" : "items-start")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground"
              : isError
                ? "bg-destructive/10 text-destructive"
                : "bg-muted",
          )}
        >
          {message.content}
        </div>
        <div className={cn("px-1 text-[11px] text-muted-foreground", isUser ? "text-right" : "text-left")}>
          {formatTime(message.timestamp)}
        </div>
      </div>
    </div>
  );
}
