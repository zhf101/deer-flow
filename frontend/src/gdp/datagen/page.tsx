"use client";

import {
  DatabaseIcon,
  FilePlus2Icon,
  GlobeIcon,
  LayoutListIcon,
  SettingsIcon,
  WorkflowIcon,
} from "lucide-react";
import { useCallback, useState } from "react";

import { cn } from "@/lib/utils";

import { ConfigManagement } from "./baseconfig";
import { HttpSourceManagement } from "./httpsource";
import { SceneDashboard } from "./scene/scene-dashboard";
import { SceneEditor } from "./scene/scene-editor";
import { SqlSourceManagement } from "./sqlsource";
import { TabBar, type Tab } from "./common/shell/module-tab-bar";
import { TaskDashboard } from "./task/task-dashboard";
import { TaskEditor } from "./task/task-editor";
import { TaskRunDialog } from "./task/task-run-dialog";

/* ── types ──────────────────────────────────────────────────────── */

type TabType =
  | "scene-list"
  | "task-list"
  | "config"
  | "httpsource"
  | "sqlsource"
  | "scene-edit"
  | "scene-view"
  | "scene-new"
  | "task-edit"
  | "task-view"
  | "task-new";

interface TabState {
  id: string;
  type: TabType;
  sceneCode?: string | null;
  taskCode?: string | null;
  label: string;
}

/* ── sidebar nav items ──────────────────────────────────────────── */

const NAV_ITEMS: {
  id: string;
  type: TabType;
  label: string;
  icon: typeof LayoutListIcon;
  group: string;
}[] = [
  { id: "scene-list", type: "scene-list", label: "造数场景", icon: LayoutListIcon, group: "编排" },
  { id: "task-list", type: "task-list", label: "造数任务", icon: WorkflowIcon, group: "编排" },
  { id: "httpsource", type: "httpsource", label: "HTTP 接口", icon: GlobeIcon, group: "配置" },
  { id: "sqlsource", type: "sqlsource", label: "SQL 配置", icon: DatabaseIcon, group: "配置" },
  { id: "config", type: "config", label: "基础配置", icon: SettingsIcon, group: "配置" },
];

/* ── main component ─────────────────────────────────────────────── */

export function DataFactoryPage() {
  const [tabs, setTabs] = useState<TabState[]>([
    { id: "scene-list", type: "scene-list", label: "造数场景" },
  ]);
  const [activeTabId, setActiveTabId] = useState("scene-list");
  const [runningTaskCode, setRunningTaskCode] = useState<string | null>(null);

  /* ── tab operations ────────────────────────────────────────────── */

  const ensureTab = useCallback(
    (newTab: TabState) => {
      setTabs((prev) => {
        const existing = prev.find((t) => t.id === newTab.id);
        if (existing) return prev;
        return [...prev, newTab];
      });
      setActiveTabId(newTab.id);
    },
    [],
  );

  const closeTab = useCallback(
    (id: string) => {
      setTabs((prev) => {
        const idx = prev.findIndex((t) => t.id === id);
        if (idx === -1) return prev;
        const next = prev.filter((t) => t.id !== id);
        if (id === activeTabId && next.length > 0) {
          const focusIdx = Math.min(idx, next.length - 1);
          setActiveTabId(next[focusIdx]!.id);
        }
        return next;
      });
    },
    [activeTabId],
  );

  const openConfig = useCallback(() => {
    ensureTab({ id: "config", type: "config", label: "基础配置" });
  }, [ensureTab]);

  const openHttpSource = useCallback(() => {
    ensureTab({ id: "httpsource", type: "httpsource", label: "HTTP 接口" });
  }, [ensureTab]);

  const openSqlSource = useCallback(() => {
    ensureTab({ id: "sqlsource", type: "sqlsource", label: "SQL 配置" });
  }, [ensureTab]);

  const openSceneEdit = useCallback(
    (code: string) => {
      ensureTab({
        id: `scene-edit-${code}`,
        type: "scene-edit",
        sceneCode: code,
        label: `编辑: ${code}`,
      });
    },
    [ensureTab],
  );

  const openSceneView = useCallback(
    (code: string) => {
      ensureTab({
        id: `scene-view-${code}`,
        type: "scene-view",
        sceneCode: code,
        label: `查看: ${code}`,
      });
    },
    [ensureTab],
  );

  const openNewScene = useCallback(() => {
    ensureTab({
      id: "scene-new",
      type: "scene-new",
      label: "新增场景",
    });
  }, [ensureTab]);

  const openTaskList = useCallback(() => {
    ensureTab({ id: "task-list", type: "task-list", label: "造数任务" });
  }, [ensureTab]);

  const openTaskEdit = useCallback(
    (code: string) => {
      ensureTab({
        id: `task-edit-${code}`,
        type: "task-edit",
        taskCode: code,
        label: `编辑: ${code}`,
      });
    },
    [ensureTab],
  );

  const openTaskView = useCallback(
    (code: string) => {
      ensureTab({
        id: `task-view-${code}`,
        type: "task-view",
        taskCode: code,
        label: `查看: ${code}`,
      });
    },
    [ensureTab],
  );

  const openNewTask = useCallback(() => {
    ensureTab({
      id: "task-new",
      type: "task-new",
      label: "新增任务",
    });
  }, [ensureTab]);

  const openTaskRun = useCallback(
    (code: string) => {
      setRunningTaskCode(code);
    },
    [],
  );

  /* ── build TabBar data ─────────────────────────────────────────── */

  const tabBarData: Tab[] = tabs.map((t) => ({
    id: t.id,
    label: t.label,
    closable: t.type !== "scene-list",
    icon:
      t.type === "scene-list" ? (
        <LayoutListIcon className="size-3" />
      ) : t.type === "task-list" ? (
        <WorkflowIcon className="size-3" />
      ) : t.type === "config" ? (
        <SettingsIcon className="size-3" />
      ) : t.type === "httpsource" ? (
        <GlobeIcon className="size-3" />
      ) : t.type === "sqlsource" ? (
        <DatabaseIcon className="size-3" />
      ) : t.type === "scene-new" || t.type === "task-new" ? (
        <FilePlus2Icon className="size-3" />
      ) : undefined,
  }));

  /* ── render active tab content ─────────────────────────────────── */

  const activeTab = tabs.find((t) => t.id === activeTabId);

  const renderContent = () => {
    if (!activeTab) return null;

    switch (activeTab.type) {
      case "scene-list":
        return (
          <SceneDashboard
            onEdit={openSceneEdit}
            onView={openSceneView}
            onCreate={openNewScene}
            onConfig={openConfig}
          />
        );
      case "task-list":
        return (
          <TaskDashboard
            onEdit={openTaskEdit}
            onView={openTaskView}
            onRun={openTaskRun}
            onCreate={openNewTask}
          />
        );
      case "config":
        return <ConfigManagement />;
      case "httpsource":
        return <HttpSourceManagement />;
      case "sqlsource":
        return <SqlSourceManagement />;
      case "scene-edit":
        return (
          <SceneEditor
            sceneCode={activeTab.sceneCode}
            readOnly={false}
            onBack={() => closeTab(activeTab.id)}
          />
        );
      case "scene-view":
        return (
          <SceneEditor
            sceneCode={activeTab.sceneCode}
            readOnly={true}
            onBack={() => closeTab(activeTab.id)}
          />
        );
      case "scene-new":
        return (
          <SceneEditor
            sceneCode={null}
            readOnly={false}
            onBack={() => closeTab(activeTab.id)}
          />
        );
      case "task-edit":
        return (
          <TaskEditor
            taskCode={activeTab.taskCode}
            readOnly={false}
            onBack={() => closeTab(activeTab.id)}
            onRun={openTaskRun}
          />
        );
      case "task-view":
        return (
          <TaskEditor
            taskCode={activeTab.taskCode}
            readOnly={true}
            onBack={() => closeTab(activeTab.id)}
          />
        );
      case "task-new":
        return (
          <TaskEditor
            taskCode={null}
            readOnly={false}
            onBack={() => closeTab(activeTab.id)}
          />
        );
      default:
        return null;
    }
  };

  /* ── determine active sidebar item ────────────────────────────── */

  const activeNavId = (() => {
    if (!activeTab) return "scene-list";
    // Map editor/view/new tabs back to their parent nav item
    if (activeTab.type.startsWith("scene")) return "scene-list";
    if (activeTab.type.startsWith("task")) return "task-list";
    return activeTab.type;
  })();

  /* ── group nav items ──────────────────────────────────────────── */

  const groups = NAV_ITEMS.reduce<Record<string, typeof NAV_ITEMS>>(
    (acc, item) => {
      (acc[item.group] ??= []).push(item);
      return acc;
    },
    {},
  );

  return (
    <main className="flex h-screen bg-background overflow-hidden">
      {/* ── Left Sidebar Navigation ── */}
      <aside className="flex w-[180px] flex-col border-r bg-muted/20 shrink-0">
        <div className="px-4 py-3 border-b">
          <h2 className="text-sm font-bold tracking-tight">造数工厂</h2>
          <p className="text-[10px] text-muted-foreground mt-0.5">数据工厂管理平台</p>
        </div>
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-4">
          {Object.entries(groups).map(([group, items]) => (
            <div key={group}>
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-1">
                {group}
              </p>
              <div className="space-y-0.5">
                {items.map((item) => {
                  const Icon = item.icon;
                  const isActive = activeNavId === item.id;
                  return (
                    <button
                      key={item.id}
                      onClick={() =>
                        ensureTab({
                          id: item.id,
                          type: item.type,
                          label: item.label,
                        })
                      }
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <Icon className="size-4 shrink-0" />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      {/* ── Main Content ── */}
      <div className="flex flex-1 flex-col min-w-0">
        <TabBar
          tabs={tabBarData}
          activeTabId={activeTabId}
          onSelect={setActiveTabId}
          onClose={closeTab}
        />
        <div className="flex-1 min-h-0 overflow-hidden">
          {renderContent()}
        </div>
      </div>

      {/* Task run dialog (shared across tabs) */}
      {runningTaskCode && (
        <TaskRunDialog
          taskCode={runningTaskCode}
          open={!!runningTaskCode}
          onOpenChange={(open) => {
            if (!open) setRunningTaskCode(null);
          }}
        />
      )}
    </main>
  );
}
