"use client";

import {
  ArrowLeftIcon,
  InfoIcon,
  PlusIcon,
  RefreshCwIcon,
  Trash2Icon,
  EditIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import {
  createDatasource,
  createServiceEndpoint,
  deleteDatasource,
  deleteEnvironment,
  deleteServiceEndpoint,
  listDatasources,
  listEnvironments,
  listServiceEndpoints,
  saveEnvironment,
  updateDatasource,
  updateServiceEndpoint,
} from "../lib/api";
import type {
  ConfigStatus,
  DatasourceConfig,
  DatasourceResponse,
  EnvironmentConfig,
  EnvironmentResponse,
  ServiceEndpointConfig,
  ServiceEndpointResponse,
} from "../lib/types";

interface ConfigManagementProps {
  onBack: () => void;
}

export function ConfigManagement({ onBack }: ConfigManagementProps) {
  return (
    <TooltipProvider delayDuration={300}>
    <div className="flex h-full flex-col p-6">
      <div className="mb-6 flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeftIcon className="size-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">配置管理</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            管理环境、服务端点和数据源配置
          </p>
        </div>
      </div>

      <Tabs defaultValue="environments" className="flex-1">
        <TabsList>
          <TabsTrigger value="environments">环境</TabsTrigger>
          <TabsTrigger value="endpoints">服务端点</TabsTrigger>
          <TabsTrigger value="datasources">数据源</TabsTrigger>
        </TabsList>

        <TabsContent value="environments">
          <EnvironmentsTab />
        </TabsContent>
        <TabsContent value="endpoints">
          <ServiceEndpointsTab />
        </TabsContent>
        <TabsContent value="datasources">
          <DatasourcesTab />
        </TabsContent>
      </Tabs>
    </div>
    </TooltipProvider>
  );
}

/* ─── Environments Tab ──────────────────────────────────────────── */

function EnvironmentsTab() {
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
      <div className="flex items-center gap-2">
        <Button onClick={openCreate} className="gap-1.5" size="sm">
          <PlusIcon className="size-4" />
          新增环境
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

/* ─── Service Endpoints Tab ─────────────────────────────────────── */

function ServiceEndpointsTab() {
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

/* ─── Datasources Tab ───────────────────────────────────────────── */

function DatasourcesTab() {
  const [items, setItems] = useState<DatasourceResponse[]>([]);
  const [envs, setEnvs] = useState<EnvironmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<DatasourceResponse | null>(null);
  const [form, setForm] = useState<DatasourceConfig>({
    envCode: "",
    datasourceCode: "",
    datasourceName: "",
    dbType: "MySQL",
    host: "",
    port: 3306,
    databaseName: "",
    username: "",
    password: "",
    status: "ENABLED",
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [datasources, environments] = await Promise.all([
        listDatasources(),
        listEnvironments(),
      ]);
      setItems(datasources);
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
      datasourceCode: "",
      datasourceName: "",
      dbType: "MySQL",
      host: "",
      port: 3306,
      databaseName: "",
      username: "",
      password: "",
      status: "ENABLED",
    });
    setDialogOpen(true);
  };

  const openEdit = (item: DatasourceResponse) => {
    setEditing(item);
    setForm({
      envCode: item.envCode,
      datasourceCode: item.datasourceCode,
      datasourceName: item.datasourceName,
      dbType: item.dbType,
      host: item.host,
      port: item.port,
      databaseName: item.databaseName,
      username: item.username ?? "",
      password: item.password ?? "",
      status: item.status,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    try {
      if (editing) {
        await updateDatasource(editing.id, form);
      } else {
        await createDatasource(form);
      }
      toast.success(editing ? "数据源已更新" : "数据源已创建");
      setDialogOpen(false);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确认删除数据源 "${name}"？`)) return;
    try {
      await deleteDatasource(id);
      toast.success("数据源已删除");
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
          新增数据源
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
              <th className="px-3 py-2 text-left font-medium">数据源编码</th>
              <th className="px-3 py-2 text-left font-medium">名称</th>
              <th className="px-3 py-2 text-left font-medium">类型</th>
              <th className="px-3 py-2 text-left font-medium">地址</th>
              <th className="px-3 py-2 text-left font-medium">状态</th>
              <th className="px-3 py-2 w-24 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="text-muted-foreground px-3 py-8 text-center"
                >
                  暂无数据源配置
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b last:border-b-0">
                <td className="px-3 py-2 font-mono text-xs">{item.envCode}</td>
                <td className="px-3 py-2 font-mono text-xs">
                  {item.datasourceCode}
                </td>
                <td className="px-3 py-2">{item.datasourceName}</td>
                <td className="px-3 py-2">
                  <Badge variant="outline">{item.dbType}</Badge>
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {item.host}:{item.port}/{item.databaseName}
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
                    onClick={() =>
                      handleDelete(item.id, item.datasourceName)
                    }
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
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editing ? "编辑数据源" : "新增数据源"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
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
            <FieldRow label="数据库类型">
              <Select
                value={form.dbType}
                onValueChange={(v) => setForm({ ...form, dbType: v })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MySQL">MySQL</SelectItem>
                  <SelectItem value="PostgreSQL">PostgreSQL</SelectItem>
                  <SelectItem value="SQLServer">SQL Server</SelectItem>
                  <SelectItem value="Oracle">Oracle</SelectItem>
                  <SelectItem value="SQLite">SQLite</SelectItem>
                </SelectContent>
              </Select>
            </FieldRow>
            <FieldRow label="数据源编码" tooltip="数据源的唯一标识符，在同一环境内不可重复。SQL 编排节点通过此编码选择要使用的数据源。例如：tradeDb、orderDb。">
              <Input
                value={form.datasourceCode}
                onChange={(e) =>
                  setForm({ ...form, datasourceCode: e.target.value })
                }
                placeholder="如 tradeDb"
                disabled={!!editing}
              />
            </FieldRow>
            <FieldRow label="数据源名称">
              <Input
                value={form.datasourceName}
                onChange={(e) =>
                  setForm({ ...form, datasourceName: e.target.value })
                }
                placeholder="如 交易数据库"
              />
            </FieldRow>
            <FieldRow label="主机地址">
              <Input
                value={form.host}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="如 127.0.0.1"
              />
            </FieldRow>
            <FieldRow label="端口">
              <Input
                type="number"
                value={form.port}
                onChange={(e) =>
                  setForm({ ...form, port: Number(e.target.value) })
                }
                placeholder="3306"
              />
            </FieldRow>
            <FieldRow label="数据库名" className="col-span-2">
              <Input
                value={form.databaseName}
                onChange={(e) =>
                  setForm({ ...form, databaseName: e.target.value })
                }
                placeholder="如 trade_db"
              />
            </FieldRow>
            <FieldRow label="用户名">
              <Input
                value={form.username ?? ""}
                onChange={(e) =>
                  setForm({ ...form, username: e.target.value })
                }
                placeholder="数据库用户名"
              />
            </FieldRow>
            <FieldRow label="密码">
              <Input
                type="password"
                value={form.password ?? ""}
                onChange={(e) =>
                  setForm({ ...form, password: e.target.value })
                }
                placeholder="数据库密码"
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

/* ─── Shared helpers ────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={status === "ENABLED" ? "default" : "secondary"}>
      {status === "ENABLED" ? "启用" : "停用"}
    </Badge>
  );
}

function FieldRow({
  label,
  children,
  className,
  tooltip,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  tooltip?: string;
}) {
  return (
    <div className={className}>
      <label className="mb-1 flex items-center gap-1 text-xs font-medium">
        {label}
        {tooltip && (
          <Tooltip>
            <TooltipTrigger asChild>
              <InfoIcon className="size-3 text-muted-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs text-xs">
              {tooltip}
            </TooltipContent>
          </Tooltip>
        )}
      </label>
      {children}
    </div>
  );
}
