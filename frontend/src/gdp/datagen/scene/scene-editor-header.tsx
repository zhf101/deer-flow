import { Loader2Icon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

interface SceneEditorHeaderProps {
  sceneName: string | null;
  stepTitle: string;
  currentStepIndex: number;
  saving: boolean;
  isPublished: boolean;
}

export function SceneEditorHeader({
  sceneName,
  stepTitle,
  currentStepIndex: _currentStepIndex,
  saving,
  isPublished,
}: SceneEditorHeaderProps) {
  return (
    <header className="h-12 border-b flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-bold truncate max-w-[200px]">{sceneName ?? "未命名场景"}</h2>
        <div className="w-px h-4 bg-border mx-1" />
        <h3 className="text-sm font-medium text-muted-foreground">
          {stepTitle}
        </h3>
      </div>
      <div className="flex items-center gap-4">
        {saving && (
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground animate-pulse">
            <Loader2Icon className="size-2.5 animate-spin" />
            自动保存中...
          </div>
        )}
        <Badge variant="outline" className="text-[10px] opacity-60 font-normal">
          {isPublished ? "已落库" : "新草稿"}
        </Badge>
      </div>
    </header>
  );
}
