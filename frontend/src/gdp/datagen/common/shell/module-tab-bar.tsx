"use client";

import { XIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/* ── 类型 ── */

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

interface ContextMenuState {
  x: number;
  y: number;
  tabId: string;
}

/* ── 组件 ── */

export function TabBar({ tabs, activeTabId, onSelect, onClose }: TabBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [ctxMenu, setCtxMenu] = useState<ContextMenuState | null>(null);
  const ctxMenuRef = useRef<HTMLDivElement>(null);

  const handleClose = useCallback(
    (e: React.MouseEvent, tabId: string) => {
      e.stopPropagation();
      onClose(tabId);
    },
    [onClose],
  );

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, tabId: string) => {
      e.preventDefault();
      e.stopPropagation();
      setCtxMenu({ x: e.clientX, y: e.clientY, tabId });
    },
    [],
  );

  // 点击外部、滚动或按下 Escape 时关闭上下文菜单
  useEffect(() => {
    if (!ctxMenu) return;

    const dismiss = () => setCtxMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };

    document.addEventListener("click", dismiss);
    document.addEventListener("scroll", dismiss, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", dismiss);
      document.removeEventListener("scroll", dismiss, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [ctxMenu]);

  /* ── 上下文菜单操作 ── */

  const doAction = useCallback(
    (action: "close-all" | "close-others" | "close-left" | "close-right") => {
      if (!ctxMenu) return;
      const idx = tabs.findIndex((t) => t.id === ctxMenu.tabId);
      if (idx === -1) return;

      let targets: Tab[];
      switch (action) {
        case "close-all":
          targets = tabs.filter((t) => t.closable);
          break;
        case "close-others":
          targets = tabs.filter((t) => t.closable && t.id !== ctxMenu.tabId);
          break;
        case "close-left":
          targets = tabs.slice(0, idx).filter((t) => t.closable);
          break;
        case "close-right":
          targets = tabs.slice(idx + 1).filter((t) => t.closable);
          break;
      }

      // 按反向顺序关闭，避免索引偏移问题
      for (let i = targets.length - 1; i >= 0; i--) {
        const target = targets[i];
        if (target) onClose(target.id);
      }
      setCtxMenu(null);
    },
    [ctxMenu, tabs, onClose],
  );

  /* ── 计算可用操作 ── */

  const ctxActions = (() => {
    if (!ctxMenu) return { canCloseLeft: false, canCloseRight: false, canCloseOthers: false, canCloseAll: false };
    const idx = tabs.findIndex((t) => t.id === ctxMenu.tabId);
    const closableTabs = tabs.filter((t) => t.closable);
    return {
      canCloseAll: closableTabs.length > 0,
      canCloseOthers: closableTabs.some((t) => t.id !== ctxMenu.tabId),
      canCloseLeft: idx > 0 && tabs.slice(0, idx).some((t) => t.closable),
      canCloseRight: idx >= 0 && idx < tabs.length - 1 && tabs.slice(idx + 1).some((t) => t.closable),
    };
  })();

  return (
    <>
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
              onContextMenu={(e) => handleContextMenu(e, tab.id)}
              className={cn(
                "group relative flex items-center gap-1.5 px-3 h-9 text-xs cursor-pointer border-r border-border/30 shrink-0 transition-colors",
                "max-w-[180px] min-w-[80px]",
                isActive
                  ? "bg-background text-foreground"
                  : "bg-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
            >
              {/* 激活状态顶部强调条 */}
              {isActive && (
                <div className="absolute top-0 left-0 right-0 h-[2px] bg-primary rounded-b" />
              )}

              {/* 图标 */}
              {tab.icon && (
                <span className="shrink-0 size-3.5">{tab.icon}</span>
              )}

              {/* 标签 */}
              <span className="truncate text-[11px] font-medium leading-none">
                {tab.label}
              </span>

              {/* 未保存状态标记 */}
              {tab.dirty && (
                <span className="shrink-0 size-1.5 rounded-full bg-primary/60" />
              )}

              {/* 关闭按钮 */}
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

      {/* ── 上下文菜单 ── */}
      {ctxMenu && (
        <div
          ref={ctxMenuRef}
          className="fixed z-[9999] min-w-[140px] rounded-md border bg-popover py-1 shadow-md text-popover-foreground animate-in fade-in-0 zoom-in-95"
          style={{ left: ctxMenu.x, top: ctxMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <CtxMenuItem
            label="关闭全部"
            disabled={!ctxActions.canCloseAll}
            onClick={() => doAction("close-all")}
          />
          <CtxMenuItem
            label="关闭其他"
            disabled={!ctxActions.canCloseOthers}
            onClick={() => doAction("close-others")}
          />
          <div className="my-1 border-t" />
          <CtxMenuItem
            label="关闭左侧"
            disabled={!ctxActions.canCloseLeft}
            onClick={() => doAction("close-left")}
          />
          <CtxMenuItem
            label="关闭右侧"
            disabled={!ctxActions.canCloseRight}
            onClick={() => doAction("close-right")}
          />
        </div>
      )}
    </>
  );
}

/* ── 上下文菜单项 ── */

function CtxMenuItem({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center px-3 py-1.5 text-[12px] transition-colors",
        disabled
          ? "text-muted-foreground/40 cursor-not-allowed"
          : "cursor-pointer hover:bg-accent hover:text-accent-foreground",
      )}
    >
      {label}
    </button>
  );
}
