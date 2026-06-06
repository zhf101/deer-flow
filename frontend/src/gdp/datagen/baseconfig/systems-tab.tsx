"use client";

import { EditIcon, Trash2Icon } from "lucide-react";
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

import { deleteSystem, listSystems, saveSystem } from "../common/lib/api";
import type { SysConfig, SysResponse } from "../common/lib/types";

import {
  ConfigToolbar,
  FieldRow,
  StatusBadge,
  StatusSelect,
} from "./config-helpers";

const EMPTY_SYSTEM: SysConfig = {
  sysCode: "",
  sysName: "",
  status: "ENABLED",
  remark: "",
};

export function SystemsTab() {
  const [items, setItems] = useState<SysResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<SysResponse | null>(null);
  const [form, setForm] = useState<SysConfig>(EMPTY_SYSTEM);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listSystems());
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
    setForm(EMPTY_SYSTEM);
    setDialogOpen(true);
  };

  const openEdit = (item: SysResponse) => {
    setEditing(item);
    setForm({
      sysCode: item.sysCode,
      sysName: item.sysName,
      status: item.status,
      remark: item.remark,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      await saveSystem(form);
      toast.success(editing ? "系统已更新" : "系统已创建");
      setDialogOpen(false);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleDelete = async (sysCode: string) => {
    if (!confirm(`确认删除系统 "${sysCode}"？`)) return;
    try {
      await deleteSystem(sysCode);
      toast.success("系统已删除");
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="mt-4 space-y-4">
      <ConfigToolbar
        createLabel="新增系统"
        loading={loading}
        onCreate={openCreate}
        onRefresh={load}
      />

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">系统编码</th>
              <th className="px-3 py-2 text-left font-medium">系统名称</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
              <th className="px-3 py-2 text-left font-medium">备注</th>
              <th className="w-24 px-3 py-2 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  暂无系统配置
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-b-0">
                <td className="px-3 py-2 font-mono text-xs">
                  {item.sysCode}
                </td>
                <td className="px-3 py-2">{item.sysName}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={item.status} />
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
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
                    onClick={() => handleDelete(item.sysCode)}
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
            <DialogTitle>{editing ? "编辑系统" : "新增系统"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <FieldRow label="系统编码">
              <Input
                value={form.sysCode}
                onChange={(e) =>
                  setForm({ ...form, sysCode: e.target.value })
                }
                placeholder="如 trade, risk, user"
                disabled={!!editing}
              />
            </FieldRow>
            <FieldRow label="系统名称">
              <Input
                value={form.sysName}
                onChange={(e) =>
                  setForm({ ...form, sysName: e.target.value })
                }
                placeholder="如 交易系统"
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
