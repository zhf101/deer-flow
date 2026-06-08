/**
 * ============================================================================
 * 任务编排 - 任务列表（仪表盘）
 * ============================================================================
 *
 * 任务编排模块的列表页面，展示所有任务并支持搜索、筛选、新建、删除等操作。
 *
 * UI 内容：
 *   - 搜索框（按任务名称搜索）
 *   - 新建任务按钮
 *   - 任务卡片/表格列表：
 *     - 任务名称、描述、创建时间、状态
 *     - 操作按钮：编辑、运行、删除
 *   - 分页组件
 *   - 删除确认对话框
 *
 * 被引用位置：
 *   - page.tsx 中作为 TabType="task-list" 的内容组件
 *
 * 新增/复用判断：新增页面，任务编排模块列表页
 */
"use client";

import {
  EditIcon,
  EyeIcon,
  FilePlus2Icon,
  MoreVerticalIcon,
  PlayIcon,
  RefreshCwIcon,
  SearchIcon,
  Trash2Icon,
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

import { deleteTask, listTasks } from "../common/lib/api";
import type { SceneStatus, TaskSummary } from "../common/lib/types";

interface TaskDashboardProps {
  onEdit: (taskCode: string) => void;
  onView: (taskCode: string) => void;
  onRun: (taskCode: string) => void;
  onCreate: () => void;
}

export function TaskDashboard({ onEdit, onView, onRun, onCreate }: TaskDashboardProps) {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<SceneStatus | "">("");
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [deletingTask, setDeletingTask] = useState<TaskSummary | null>(null);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listTasks({
        keyword,
        status,
        limit,
        offset: page * limit,
      });
      setTasks(result);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [keyword, status, page, limit]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  const handleDelete = async () => {
    if (!deletingTask) return;
    try {
      await deleteTask(deletingTask.taskCode);
      toast.success("任务已删除");
      setDeletingTask(null);
      void loadTasks();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    }
  };

  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">造数任务</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            编排多个造数场景，组成复杂的造数任务
          </p>
        </div>
        <Button onClick={onCreate} className="gap-2">
          <FilePlus2Icon className="size-4" />
          新增任务
        </Button>
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
            placeholder="搜索任务名称或编码"
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
          onClick={loadTasks}
          disabled={loading}
        >
          <RefreshCwIcon className={cn("size-4", loading && "animate-spin")} />
        </Button>
      </div>

      <div className="flex-1 overflow-auto rounded-md border bg-card shadow-sm">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-muted/50 sticky top-0 z-10 border-b">
            <tr>
              <th className="p-4 font-medium">任务名称</th>
              <th className="p-4 font-medium">状态</th>
              <th className="p-4 font-medium">当前版本</th>
              <th className="p-4 font-medium">最后更新</th>
              <th className="p-4 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && tasks.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-muted-foreground">
                  加载中...
                </td>
              </tr>
            ) : tasks.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-muted-foreground">
                  未找到匹配的任务
                </td>
              </tr>
            ) : (
              tasks.map((task) => (
                <tr
                  key={task.id}
                  className="border-b hover:bg-muted/30 transition-colors cursor-pointer"
                  onClick={() => onView(task.taskCode)}
                >
                  <td className="p-4">
                    <div className="font-medium">{task.taskName}</div>
                    <div className="text-muted-foreground font-mono text-xs">
                      {task.taskCode}
                    </div>
                    {task.taskRemark && (
                      <div className="text-muted-foreground mt-0.5 text-xs truncate max-w-xs">
                        {task.taskRemark}
                      </div>
                    )}
                  </td>
                  <td className="p-4">
                    <StatusBadge status={task.status} />
                  </td>
                  <td className="p-4">
                    {task.currentVersionNo ? `v${task.currentVersionNo}` : "-"}
                  </td>
                  <td className="p-4 text-muted-foreground">
                    {new Date(task.updatedAt).toLocaleString()}
                  </td>
                  <td className="p-4 text-right">
                    <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={(e) => { e.stopPropagation(); onView(task.taskCode); }}
                        title="查看详情"
                      >
                        <EyeIcon className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={(e) => { e.stopPropagation(); onEdit(task.taskCode); }}
                        title="编辑"
                      >
                        <EditIcon className="size-4" />
                      </Button>
                      {task.status === "PUBLISHED" && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={(e) => { e.stopPropagation(); onRun(task.taskCode); }}
                          title="执行"
                        >
                          <PlayIcon className="size-4 text-green-600" />
                        </Button>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" onClick={(e) => e.stopPropagation()}>
                            <MoreVerticalIcon className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onSelect={() => setDeletingTask(task)}
                          >
                            <Trash2Icon className="mr-2 size-4" />
                            删除任务
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
            disabled={tasks.length < limit || loading}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </Button>
        </div>
      </div>

      {/* 删除对话框 */}
      <Dialog open={!!deletingTask} onOpenChange={(open) => !open && setDeletingTask(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-destructive">确认删除</DialogTitle>
            <DialogDescription>
              您确定要删除任务 "{deletingTask?.taskName}" 吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingTask(null)}>
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
