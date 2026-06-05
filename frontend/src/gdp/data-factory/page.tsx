"use client";

import {
  FilePlus2Icon,
  LayoutListIcon,
  SettingsIcon,
} from "lucide-react";
import { useCallback, useState } from "react";

import { ConfigManagement } from "./components/config";
import { SceneDashboard } from "./components/orchestration/scene-dashboard";
import { SceneEditor } from "./components/orchestration/scene-editor";
import { TabBar, type Tab } from "./components/tab-bar";

/* ── types ──────────────────────────────────────────────────────── */

interface TabState {
  id: string;
  type: "scene-list" | "config" | "scene-edit" | "scene-view" | "scene-new";
  sceneCode?: string | null;
  label: string;
}

/* ── main component ─────────────────────────────────────────────── */

export function DataFactoryPage() {
  const [tabs, setTabs] = useState<TabState[]>([
    { id: "scene-list", type: "scene-list", label: "造数场景" },
  ]);
  const [activeTabId, setActiveTabId] = useState("scene-list");

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
        // If closing active tab, focus adjacent
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
    ensureTab({ id: "config", type: "config", label: "配置管理" });
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

  /* ── build TabBar data ─────────────────────────────────────────── */

  const tabBarData: Tab[] = tabs.map((t) => ({
    id: t.id,
    label: t.label,
    closable: t.type !== "scene-list",
    icon:
      t.type === "scene-list" ? (
        <LayoutListIcon className="size-3" />
      ) : t.type === "config" ? (
        <SettingsIcon className="size-3" />
      ) : t.type === "scene-new" ? (
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
      case "config":
        return <ConfigManagement />;
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
      default:
        return null;
    }
  };

  return (
    <main className="flex h-screen flex-col bg-background overflow-hidden">
      <TabBar
        tabs={tabBarData}
        activeTabId={activeTabId}
        onSelect={setActiveTabId}
        onClose={closeTab}
      />
      <div className="flex-1 min-h-0 overflow-hidden">
        {renderContent()}
      </div>
    </main>
  );
}
