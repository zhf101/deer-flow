"use client";

import { XIcon } from "lucide-react";
import { useCallback, useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/* ── types ──────────────────────────────────────────────────────── */

export interface Tab {
  id: string;
  label: string;
  icon?: ReactNode;
  closable: boolean;
  dirty?: boolean;
}

interface TabBarProps {
  tabs: Tab[];
  activeTabId: string;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
}

/* ── component ──────────────────────────────────────────────────── */

export function TabBar({ tabs, activeTabId, onSelect, onClose }: TabBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleClose = useCallback(
    (e: React.MouseEvent, tabId: string) => {
      e.stopPropagation();
      onClose(tabId);
    },
    [onClose],
  );

  return (
    <div
      ref={scrollRef}
      className="flex items-center bg-muted/30 border-b overflow-x-auto scrollbar-thin select-none shrink-0"
      style={{ scrollbarWidth: "thin" }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTabId;
        return (
          <div
            key={tab.id}
            onClick={() => onSelect(tab.id)}
            className={cn(
              "group relative flex items-center gap-1.5 px-3 h-9 text-xs cursor-pointer border-r border-border/30 shrink-0 transition-colors",
              "max-w-[180px] min-w-[80px]",
              isActive
                ? "bg-background text-foreground"
                : "bg-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
          >
            {/* Active indicator - top accent bar */}
            {isActive && (
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-primary rounded-b" />
            )}

            {/* Icon */}
            {tab.icon && (
              <span className="shrink-0 size-3.5">{tab.icon}</span>
            )}

            {/* Label */}
            <span className="truncate text-[11px] font-medium leading-none">
              {tab.label}
            </span>

            {/* Dirty indicator */}
            {tab.dirty && (
              <span className="shrink-0 size-1.5 rounded-full bg-primary/60" />
            )}

            {/* Close button */}
            {tab.closable && (
              <button
                type="button"
                onClick={(e) => handleClose(e, tab.id)}
                className={cn(
                  "shrink-0 ml-auto rounded-sm p-0.5 transition-all",
                  isActive
                    ? "opacity-60 hover:opacity-100 hover:bg-muted"
                    : "opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:bg-muted",
                )}
              >
                <XIcon className="size-3" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
