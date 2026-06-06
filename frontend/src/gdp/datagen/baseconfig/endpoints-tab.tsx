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

import {
  createServiceEndpoint,
  deleteServiceEndpoint,
  listEnvironments,
  listServiceEndpoints,
  listSystems,
  updateServiceEndpoint,
} from "../common/lib/api";
import type {
  EnvironmentResponse,
  ServiceEndpointConfig,
  ServiceEndpointResponse,
  SysResponse,
} from "../common/lib/types";

import {
  ConfigToolbar,
  EnvironmentSelect,
  FieldRow,
  StatusBadge,
  StatusSelect,
  SystemSelect,
  systemNameByCode,
} from "./config-helpers";

const EMPTY_ENDPOINT: ServiceEndpointConfig = {
  envCode: "",
  sysCode: "",
  baseUrl: "",
  status: "ENABLED",
};

export function ServiceEndpointsTab() {
  const [items, setItems] = useState<ServiceEndpointResponse[]>([]);
  const [envs, setEnvs] = useState<EnvironmentResponse[]>([]);
  const [systems, setSystems] = useState<SysResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceEndpointResponse | null>(null);
  const [form, setForm] = useState<ServiceEndpointConfig>(EMPTY_ENDPOINT);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [endpoints, environments, systemItems] = await Promise.all([
        listServiceEndpoints(),
        listEnvironments(),
        listSystems(),
      ]);
      setItems(endpoints);
      setEnvs(environments);
      setSystems(systemItems);
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
    setForm({
      ...EMPTY_ENDPOINT,
      envCode: envs[0]?.envCode ?? "",
      sysCode: systems[0]?.sysCode ?? "",
    });
    setDialogOpen(true);
  };

  const openEdit = (item: ServiceEndpointResponse) => {
    setEditing(item);
    setForm({
      envCode: item.envCode,
      sysCode: item.sysCode,
      baseUrl: item.baseUrl,
      status: item.status,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      if (editing) {
        await updateServiceEndpoint(editing.id, form);
      } else {
        await createServiceEndpoint(form);
      }
      toast.success(editing ? "服务端点已更新" : "服务端点已创建");
      setDialogOpen(false);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleDelete = async (item: ServiceEndpointResponse) => {
    if (!confirm(`确认删除服务端点 "${item.envCode}/${item.sysCode}"？`)) {
      return;
    }
    try {
      await deleteServiceEndpoint(item.id);
      toast.success("服务端点已删除");
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="mt-4 space-y-4">
      <ConfigToolbar
        createLabel="新增服务端点"
        loading={loading}
        onCreate={openCreate}
        onRefresh={load}
      />

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">环境</th>
              <th className="px-3 py-2 text-left font-medium">所属系统</th>
              <th className="px-3 py-2 text-left font-medium">Base URL</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
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
                  暂无服务端点配置
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-b-0">
                <td className="px-3 py-2 font-mono text-xs">
                  {item.envCode}
                </td>
                <td className="px-3 py-2">
                  {systemNameByCode(systems, item.sysCode)}
                  <span className="ml-1 font-mono text-xs text-muted-foreground">
                    ({item.sysCode})
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {item.baseUrl}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={item.status} />
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
                    onClick={() => handleDelete(item)}
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
            <DialogTitle>
              {editing ? "编辑服务端点" : "新增服务端点"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <FieldRow label="环境">
              <EnvironmentSelect
                value={form.envCode}
                envs={envs}
                onChange={(envCode) => setForm({ ...form, envCode })}
              />
            </FieldRow>
            <FieldRow label="所属系统">
              <SystemSelect
                value={form.sysCode}
                systems={systems}
                onChange={(sysCode) => setForm({ ...form, sysCode })}
              />
            </FieldRow>
            <FieldRow label="Base URL">
              <Input
                value={form.baseUrl}
                onChange={(e) =>
                  setForm({ ...form, baseUrl: e.target.value })
                }
                placeholder="如 https://api-dev.example.com"
              />
            </FieldRow>
            <FieldRow label="状态">
              <StatusSelect
                value={form.status}
                onChange={(status) => setForm({ ...form, status })}
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
