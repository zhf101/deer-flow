"use client";

import {
  EditIcon,
  Trash2Icon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import {
  deleteEnvironment,
  listEnvironments,
  saveEnvironment,
} from "../common/lib/api";
import type {
  EnvironmentConfig,
  EnvironmentResponse,
} from "../common/lib/types";

import {
  ConfigToolbar,
  FieldRow,
  StatusBadge,
  StatusSelect,
} from "./config-helpers";

export function EnvironmentsTab() {
  const [items, setItems] = useState<EnvironmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<EnvironmentResponse | null>(null);
  const [form, setForm] = useState<EnvironmentConfig>({
    envCode: "",
    envName: "",
    status: "ENABLED",
    remark: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listEnvironments());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm({ envCode: "", envName: "", status: "ENABLED", remark: "" });
    setDialogOpen(true);
  };

  const openEdit = (item: EnvironmentResponse) => {
    setEditing(item);
    setForm({
      envCode: item.envCode,
      envName: item.envName,
      status: item.status,
      remark: item.remark,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      await saveEnvironment(form);
      toast.success(editing ? "环境已更新" : "环境已创建");
      setDialogOpen(false);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleDelete = async (envCode: string) => {
    if (!confirm(`确认删除环境 "${envCode}"？`)) return;
    try {
      await deleteEnvironment(envCode);
      toast.success("环境已删除");
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="mt-4 space-y-4">
      <ConfigToolbar
        createLabel="新增环境"
        loading={loading}
        onCreate={openCreate}
        onRefresh={load}
      />

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">环境编码</th>
              <th className="px-3 py-2 text-left font-medium">环境名称</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
              <th className="px-3 py-2 text-left font-medium">备注</th>
              <th className="px-3 py-2 w-24 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="text-muted-foreground px-3 py-8 text-center"
                >
                  暂无环境配置
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-b-0">
                <td className="px-3 py-2 font-mono text-xs">{item.envCode}</td>
                <td className="px-3 py-2">{item.envName}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={item.status} />
                </td>
                <td className="text-muted-foreground px-3 py-2 text-xs">
                  {item.remark ?? "-"}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    onClick={() => openEdit(item)}
                  >
                    <EditIcon className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-7 text-red-500"
                    onClick={() => handleDelete(item.envCode)}
                  >
                    <Trash2Icon className="size-3.5" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? "编辑环境" : "新增环境"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <FieldRow label="环境编码">
              <Input
                value={form.envCode}
                onChange={(e) =>
                  setForm({ ...form, envCode: e.target.value })
                }
                placeholder="如 dev, staging, prod"
                disabled={!!editing}
              />
            </FieldRow>
            <FieldRow label="环境名称">
              <Input
                value={form.envName}
                onChange={(e) =>
                  setForm({ ...form, envName: e.target.value })
                }
                placeholder="如 开发环境"
              />
            </FieldRow>
            <FieldRow label="状态">
              <StatusSelect
                value={form.status}
                onChange={(status) => setForm({ ...form, status })}
              />
            </FieldRow>
            <FieldRow label="备注">
              <Input
                value={form.remark ?? ""}
                onChange={(e) => setForm({ ...form, remark: e.target.value })}
                placeholder="可选"
              />
            </FieldRow>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleSave}>保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
