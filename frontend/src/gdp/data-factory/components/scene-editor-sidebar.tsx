import {
    CheckCircle2Icon,
    ChevronLeftIcon,
    ChevronRightIcon,
    EyeIcon,
    Loader2Icon,
    PlayIcon,
    RocketIcon,
    SaveIcon,
  } from "lucide-react";

  import { Badge } from "@/components/ui/badge";
  import { Button } from "@/components/ui/button";
  import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
  } from "@/components/ui/tooltip";
  import { cn } from "@/lib/utils";

  import type { SceneStatus } from "../lib/types";

  function StatusBadge({ status }: { status: SceneStatus }) {
    const label =
      status === "PUBLISHED" ? "已发布" : status === "DISABLED" ? "已停用" : "草稿";
    const variant =
      status === "PUBLISHED" ? "default" : status === "DISABLED" ? "destructive" : "secondary";

    return (
      <Badge variant={variant} className="rounded-md">
        {label}
      </Badge>
    );
  }

  interface SceneEditorSidebarProps {
    isSidebarExpanded: boolean;
    setIsSidebarExpanded: (expanded: boolean) => void;
    onBack: () => void;
    sceneName: string | null;
    sceneCode: string | null;
    status: SceneStatus;
    steps: Array<{ title: string; description: string; icon: any }>;
    currentStep: number;
    navigateToStep: (idx: number) => void;
    saving: boolean;
    publishing: boolean;
    save: () => void;
    runPublish: () => void;
    onRun?: () => void;
    readOnly?: boolean;
  }

  export function SceneEditorSidebar({
    isSidebarExpanded,
    setIsSidebarExpanded,
    onBack,
    sceneName,
    sceneCode,
    status,
    steps,
    currentStep,
    navigateToStep,
    saving,
    publishing,
    save,
    runPublish,
    onRun,
    readOnly,
  }: SceneEditorSidebarProps) {
    return (
      <aside
        className={cn(
            "border-r bg-card flex flex-col shrink-0 transition-all duration-300 ease-in-out z-30",
            isSidebarExpanded ? "w-64" : "w-16"
        )}
      >
        <div className="p-4 border-b flex items-center overflow-hidden h-14 shrink-0">
            <Button variant="ghost" size="icon-sm" onClick={onBack} className="shrink-0">
                <ChevronLeftIcon className="size-4" />
            </Button>
            {isSidebarExpanded ? (
                <>
                    <span className="ml-2 text-xs font-bold truncate animate-in fade-in slide-in-from-left-1 flex-1">返回仪表盘</span>
                    <Button variant="ghost" size="icon-sm" onClick={() => setIsSidebarExpanded(false)} className="shrink-0">
                        <ChevronLeftIcon className="size-4" />
                    </Button>
                </>
            ) : (
                <Button variant="ghost" size="icon-sm" onClick={() => setIsSidebarExpanded(true)} className="shrink-0 ml-auto">
                    <ChevronRightIcon className="size-4" />
                </Button>
            )}
        </div>

        {isSidebarExpanded && (
            <div className="px-5 pt-4 pb-2">
                <h2 className="text-sm font-bold truncate" title={sceneName || ""}>{sceneName || "未命名场景"}</h2>
                <div className="flex items-center gap-2 mt-1">
                    <StatusBadge status={status} />
                    <span className="text-[10px] font-mono text-muted-foreground uppercase">{sceneCode || "DRAFT"}</span>
                </div>
            </div>
        )}

        <nav className="flex-1 p-2 space-y-2 mt-2 overflow-hidden">
            {steps.map((step, idx) => {
                const isActive = currentStep === idx;
                const isCompleted = idx < currentStep;
                const Icon = step.icon;
                return (
                    <Tooltip key={idx}>
                        <TooltipTrigger asChild>
                            <button
                                onClick={() => navigateToStep(idx)}
                                className={cn(
                                    "w-full flex items-center gap-3 rounded-lg transition-all text-left relative",
                                    isActive ? "bg-background shadow-sm border border-border" : "hover:bg-muted/50 border border-transparent text-muted-foreground",
                                    isSidebarExpanded ? "p-3" : "p-2 justify-center"
                                )}
                            >
                                {isActive && <div className="absolute left-0 top-2 bottom-2 w-1 bg-primary rounded-full" />}
                                <div className={cn(
                                    "size-8 rounded-full flex items-center justify-center shrink-0 transition-colors",
                                    isActive ? "bg-primary text-primary-foreground" : isCompleted ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                                )}>
                                    {isCompleted ? <CheckCircle2Icon className="size-4" /> : <Icon className="size-4" />}
                                </div>
                                {isSidebarExpanded && (
                                    <div className="min-w-0 animate-in fade-in slide-in-from-left-2 duration-300">
                                        <div className={cn("text-xs font-bold leading-tight", isActive ? "text-primary" : "text-foreground/80")}>
                                            {step.title}
                                        </div>
                                        <div className="text-[10px] opacity-70 mt-0.5 truncate leading-tight">
                                            {step.description}
                                        </div>
                                    </div>
                                )}
                            </button>
                        </TooltipTrigger>
                        {!isSidebarExpanded && (
                            <TooltipContent side="right" className="flex flex-col gap-0.5">
                                <p className="text-xs font-bold">{step.title}</p>
                                <p className="text-[10px] opacity-70">{step.description}</p>
                            </TooltipContent>
                        )}
                    </Tooltip>
                );
            })}
        </nav>

        {!readOnly ? (
            <div className={cn("p-4 border-t space-y-2", !isSidebarExpanded && "p-2 items-center")}>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            variant="outline"
                            size={isSidebarExpanded ? "sm" : "icon-sm"}
                            className={cn("w-full h-8 gap-2", !isSidebarExpanded && "justify-center p-0")}
                            onClick={save}
                            disabled={saving}
                        >
                            {saving ? <Loader2Icon className="size-3 animate-spin" /> : <SaveIcon className="size-3" />}
                            {isSidebarExpanded && <span className="text-xs">保存</span>}
                        </Button>
                    </TooltipTrigger>
                    {!isSidebarExpanded && <TooltipContent side="right">立即保存草稿</TooltipContent>}
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                        <Button
                            size={isSidebarExpanded ? "sm" : "icon-sm"}
                            className={cn("w-full h-8 gap-2", !isSidebarExpanded && "justify-center p-0")}
                            onClick={runPublish}
                            disabled={publishing || saving}
                        >
                            {publishing ? <Loader2Icon className="size-3 animate-spin" /> : <RocketIcon className="size-3" />}
                            {isSidebarExpanded && <span className="text-xs">发布</span>}
                        </Button>
                    </TooltipTrigger>
                    {!isSidebarExpanded && <TooltipContent side="right">发布上线</TooltipContent>}
                </Tooltip>

                {status === "PUBLISHED" && onRun && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size={isSidebarExpanded ? "sm" : "icon-sm"}
                        className={cn(
                          "w-full h-8 gap-2 border-green-200 text-green-700 hover:bg-green-50",
                          !isSidebarExpanded && "justify-center p-0"
                        )}
                        onClick={onRun}
                      >
                        <PlayIcon className="size-3" />
                        {isSidebarExpanded && <span className="text-xs">执行</span>}
                      </Button>
                    </TooltipTrigger>
                    {!isSidebarExpanded && <TooltipContent side="right">执行场景</TooltipContent>}
                  </Tooltip>
                )}
            </div>
        ) : (
            <div className={cn("p-4 border-t", !isSidebarExpanded && "p-2 flex justify-center")}>
                {isSidebarExpanded ? (
                    <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2">
                        <EyeIcon className="size-3.5 text-muted-foreground shrink-0" />
                        <span className="text-[11px] text-muted-foreground font-medium">只读查看模式</span>
                    </div>
                ) : (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <div className="p-2 rounded-md bg-muted/50 cursor-default">
                                <EyeIcon className="size-3.5 text-muted-foreground" />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent side="right">只读查看模式</TooltipContent>
                    </Tooltip>
                )}
            </div>
        )}
      </aside>
    );
  }