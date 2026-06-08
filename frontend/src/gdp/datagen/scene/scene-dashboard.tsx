"use client";

import {
  CopyIcon,
  EditIcon,
  EyeIcon,
  FilePlus2Icon,
  MoreVerticalIcon,
  RefreshCwIcon,
  SearchIcon,
  Trash2Icon,
  SparklesIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { createScene, copyScene, deleteScene, listScenes } from "../common/lib/api";
import type { SceneStatus, SceneSummary } from "../common/lib/types";

import { buildDemoSceneDefinition } from "./demo-scene-fixture";

interface SceneDashboardProps {
  onEdit: (sceneCode: string) => void;
  onView: (sceneCode: string) => void;
  onCreate: () => void;
  onConfig: () => void;
}

export function SceneDashboard({ onEdit, onView, onCreate }: SceneDashboardProps) {
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<SceneStatus | "">("");
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [copyingScene, setCopyingScene] = useState<SceneSummary | null>(null);
  const [newSceneCode, setNewSceneCode] = useState("");
  const [deletingScene, setDeletingScene] = useState<SceneSummary | null>(null);
  const [generatingDemo, setGeneratingDemo] = useState(false);

  const loadScenes = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listScenes({
        keyword,
        status,
        limit,
        offset: page * limit,
      });
      setScenes(result);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [keyword, status, page, limit]);

  useEffect(() => {
    void loadScenes();
  }, [loadScenes]);

  const handleGenerateDemo = async () => {
    setGeneratingDemo(true);
    try {
      await createScene(buildDemoSceneDefinition());
      toast.success("演示场景生成成功！");
      void loadScenes();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "演示场景生成失败");
    } finally {
      setGeneratingDemo(false);
    }
  };

  const handleCopy = async () => {
    if (!copyingScene || !newSceneCode) return;
    try {
      await copyScene(copyingScene.sceneCode, newSceneCode);
      toast.success("场景已复制");
      setCopyingScene(null);
      setNewSceneCode("");
      void loadScenes();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "复制失败");
    }
  };

  const handleDelete = async () => {
    if (!deletingScene) return;
    try {
      await deleteScene(deletingScene.sceneCode);
      toast.success("场景已删除");
      setDeletingScene(null);
      void loadScenes();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    }
  };

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">造数编排</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            管理和编排您的业务造数场景
          </p>
        </div>
        <div className="flex items-center gap-3">
            <Button variant="outline" onClick={handleGenerateDemo} disabled={generatingDemo} className="gap-2 border-primary/20 text-primary hover:bg-primary/5">
                <SparklesIcon className="size-4" />
                生成演示配置 (Demo)
            </Button>
            <Button onClick={onCreate} className="gap-2">
            <FilePlus2Icon className="size-4" />
            新增场景
            </Button>
        </div>
      </div>

      <div className="mb-6 flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <SearchIcon className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
          <Input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(0);
            }}
            placeholder="搜索场景名称或编码"
            className="pl-9"
          />
        </div>
        <Select
          value={status || "ALL"}
          onValueChange={(val) => {
            setStatus(val === "ALL" ? "" : (val as SceneStatus));
            setPage(0);
          }}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="所有状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">所有状态</SelectItem>
            <SelectItem value="DRAFT">草稿</SelectItem>
            <SelectItem value="PUBLISHED">已发布</SelectItem>
            <SelectItem value="DISABLED">已停用</SelectItem>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="icon"
          onClick={loadScenes}
          disabled={loading}
        >
          <RefreshCwIcon className={cn("size-4", loading && "animate-spin")} />
        </Button>
      </div>

      <div className="flex-1 overflow-auto rounded-md border bg-card shadow-sm">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-muted/50 sticky top-0 z-10 border-b">
            <tr>
              <th className="p-4 font-medium">场景名称</th>
              <th className="p-4 font-medium">业务分类</th>
              <th className="p-4 font-medium">状态</th>
              <th className="p-4 font-medium">当前版本</th>
              <th className="p-4 font-medium">最后更新</th>
              <th className="p-4 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && scenes.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : scenes.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-muted-foreground">
                  未找到匹配的场景
                </td>
              </tr>
            ) : (
              scenes.map((scene) => (
                <tr
                  key={scene.id}
                  className="border-b hover:bg-muted/30 transition-colors cursor-pointer"
                  onClick={() => onView(scene.sceneCode)}
                >
                  <td className="p-4">
                    <div className="font-medium">{scene.sceneName}</div>
                    <div className="text-muted-foreground font-mono text-xs">
                      {scene.sceneCode}
                    </div>
                  </td>
                  <td className="p-4">{scene.sceneType ?? "-"}</td>
                  <td className="p-4">
                    <StatusBadge status={scene.status} />
                  </td>
                  <td className="p-4">
                    {scene.currentVersionNo ? `v${scene.currentVersionNo}` : "-"}
                  </td>
                  <td className="p-4 text-muted-foreground">
                    {new Date(scene.updatedAt).toLocaleString()}
                  </td>
                  <td className="p-4 text-right">
                    <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={(e) => { e.stopPropagation(); onView(scene.sceneCode); }}
                        title="查看详情"
                      >
                        <EyeIcon className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={(e) => { e.stopPropagation(); onEdit(scene.sceneCode); }}
                        title="编辑"
                      >
                        <EditIcon className="size-4" />
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" onClick={(e) => e.stopPropagation()}>
                            <MoreVerticalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onSelect={() => {
                              setCopyingScene(scene);
                              setNewSceneCode(`${scene.sceneCode}_copy`);
                            }}
                          >
                            <CopyIcon className="mr-2 size-4" />
                            复制场景
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onSelect={() => setDeletingScene(scene)}
                          >
                            <Trash2Icon className="mr-2 size-4" />
                            删除场景
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between">
        <p className="text-muted-foreground text-xs">
          第 {page + 1} 页
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0 || loading}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={scenes.length < limit || loading}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </Button>
        </div>
      </div>

      {/* 复制对话框 */}
      <Dialog open={!!copyingScene} onOpenChange={(open) => !open && setCopyingScene(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>复制场景</DialogTitle>
            <DialogDescription>
              请输入新场景的唯一编码。
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <label className="text-sm font-medium">新场景编码</label>
            <Input
              value={newSceneCode}
              onChange={(e) => setNewSceneCode(e.target.value)}
              placeholder="e.g. create_order_v2"
              className="mt-2"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCopyingScene(null)}>
              取消
            </Button>
            <Button onClick={handleCopy} disabled={!newSceneCode}>
              确定复制
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除对话框 */}
      <Dialog open={!!deletingScene} onOpenChange={(open) => !open && setDeletingScene(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-destructive">确认删除</DialogTitle>
            <DialogDescription>
              您确定要删除场景 &quot;{deletingScene?.sceneName}&quot;
              吗？此操作不可撤销，且会删除所有相关版本。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingScene(null)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

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
