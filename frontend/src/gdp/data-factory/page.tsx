"use client";

import { useState } from "react";

import { ConfigManagement } from "./components/config-management";
import { SceneDashboard } from "./components/scene-dashboard";
import { SceneEditor } from "./components/scene-editor";

type ViewMode = "list" | "edit" | "view" | "config";

export function DataFactoryPage() {
  const [view, setView] = useState<ViewMode>("list");
  const [selectedSceneCode, setSelectedSceneCode] = useState<string | null>(null);

  if (view === "config") {
    return (
      <main className="bg-background h-screen min-h-0 w-full overflow-hidden">
        <ConfigManagement onBack={() => setView("list")} />
      </main>
    );
  }

  if (view === "list") {
    return (
      <main className="bg-background h-screen min-h-0 w-full overflow-hidden">
        <SceneDashboard
          onEdit={(code) => {
            setSelectedSceneCode(code);
            setView("edit");
          }}
          onView={(code) => {
            setSelectedSceneCode(code);
            setView("view");
          }}
          onCreate={() => {
            setSelectedSceneCode(null);
            setView("edit");
          }}
          onConfig={() => setView("config")}
        />
      </main>
    );
  }

  return (
    <main className="bg-background h-screen min-h-0 w-full overflow-hidden">
      <SceneEditor
        sceneCode={selectedSceneCode}
        readOnly={view === "view"}
        onBack={() => setView("list")}
      />
    </main>
  );
}
