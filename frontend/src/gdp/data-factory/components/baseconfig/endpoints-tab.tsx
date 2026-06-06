"use client";

import {
  EditIcon,
  PlusIcon,
  RefreshCwIcon,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  createServiceEndpoint,
  deleteServiceEndpoint,
  listEnvironments,
  listServiceEndpoints,
  updateServiceEndpoint,
} from "../../lib/api";
import type {
  ConfigStatus,
  EnvironmentResponse,
  ServiceEndpointConfig,
  ServiceEndpointResponse,
} from "../../lib/types";
import { FieldRow, StatusBadge } from "./config-helpers";

export function ServiceEndpointsTab() {
  const [items, setItems] = useState<ServiceEndpointResponse[]>([]);
  const [envs, setEnvs] = useState<EnvironmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceEndpointResponse | null>(null);
  const [form, setForm] = useState<ServiceEndpointConfig>({
    envCode: "",
    serviceCode: "",
    serviceName: "",
    baseUrl: "",
    status: "ENABLED",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [endpoints, environments] = await Promise.all([
        listServiceEndpoints(),
        listEnvironments(),
      ]);
      setItems(endpoints);
      setEnvs(environments);
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
      envCode: envs[0]?.envCode ?? "",
      serviceCode: "",
      serviceName: "",
      baseUrl: "",
      status: "ENABLED",
    });
    setDialogOpen(true);
  };

  const openEdit = (item: ServiceEndpointResponse) => {
    setEditing(item);
    setForm({
      envCode: item.envCode,
      serviceCode: item.serviceCode,
      serviceName: item.serviceName,
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

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确认删除服务端点 "${name}"？`)) return;
    try {
      await deleteServiceEndpoint(id);
      toast.success("服务端点已删除");
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="mt-4 space-y-4">
      <div className="flex items-center gap-2">
        <Button onClick={openCreate} className="gap-1.5" size="sm">
          <PlusIcon className="size-4" />
          新增服务端点
        </Button>
        <Button variant="outline" size="icon" onClick={load} disabled={loading}>
          <RefreshCwIcon
            className={`size-4 ${loading ? "animate-spin" : ""}`}
          />
        </Button>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">环境</th>
              <th className="px-3 py-2 text-left font-medium">服务编码</th>
              <th className="px-3 py-2 text-left font-medium">服务名称</th>
              <th className="px-3 py-2 text-left font-medium">Base URL</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
              <th className="px-3 py-2 w-24 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="text-muted-foreground px-3 py-8 text-center"
                >
                  暂无服务端点配置
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-b-0">
                <td className="px-3 py-2 font-mono text-xs">{item.envCode}</td>
                <td className="px-3 py-2 font-mono text-xs">
                  {item.serviceCode}
                </td>
                <td className="px-3 py-2">{item.serviceName}</td>
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
                    onClick={() => handleDelete(item.id, item.serviceName)}
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
              <Select
                value={form.envCode}
                onValueChange={(v) => setForm({ ...form, envCode: v })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择环境" />
                </SelectTrigger>
                <SelectContent>
                  {envs.map((env) => (
                    <SelectItem key={env.envCode} value={env.envCode}>
                      {env.envName} ({env.envCode})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FieldRow>
            <FieldRow label="服务编码">
              <Input
                value={form.serviceCode}
                onChange={(e) =>
                  setForm({ ...form, serviceCode: e.target.value })
                }
                placeholder="如 user-service"
                disabled={!!editing}
              />
            </FieldRow>
            <FieldRow label="服务名称">
              <Input
                value={form.serviceName}
                onChange={(e) =>
                  setForm({ ...form, serviceName: e.target.value })
                }
                placeholder="如 用户服务"
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
              <Select
                value={form.status}
                onValueChange={(v) =>
                  setForm({ ...form, status: v as ConfigStatus })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ENABLED">启用</SelectItem>
                  <SelectItem value="DISABLED">停用</SelectItem>
                </SelectContent>
              </Select>
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
