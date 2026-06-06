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

import { createScene, copyScene, deleteScene, listScenes } from "../../lib/api";
import type { SceneStatus, SceneSummary } from "../../lib/types";

interface SceneDashboardProps {
  onEdit: (sceneCode: string) => void;
  onView: (sceneCode: string) => void;
  onCreate: () => void;
  onConfig: () => void;
}

export function SceneDashboard({ onEdit, onView, onCreate, onConfig }: SceneDashboardProps) {
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
          const timestamp = Date.now();
          const demoSceneCode = `demo_scene_${timestamp}`;
          await createScene({
            sceneCode: demoSceneCode,
            sceneName: "电商下单核心链路 (演示)",
            sceneType: "ecommerce",
            sceneRemark: "演示场景：HTTP 用户登录获取 Token → SQL 查询库存 → HTTP 创建订单 → SQL 记录订单日志，展示请求映射、响应提取与参数传递。",
            environmentField: "env",
            status: "DRAFT",
            inputSchema: [
                { name: "env", label: "环境标识", remark: "用于切换测试/预发/生产环境", type: "string", required: true, batchEnabled: false },
                { name: "userId", label: "用户ID", remark: "下单买家唯一标识", type: "string", required: true, batchEnabled: true, defaultValue: "U8899" },
                { name: "productId", label: "商品编号", remark: "待购买商品SKU编号", type: "string", required: true, batchEnabled: true, defaultValue: "P1024" },
                { name: "buyCount", label: "购买数量", remark: "单次购买件数", type: "number", required: false, batchEnabled: true, defaultValue: 2 }
            ],
            steps: [
                {
                    stepId: "user_login",
                    stepName: "1. 用户登录获取Token",
                    type: "HTTP",
                    enabled: true,
                    dependsOn: [],
                    description: "调用认证服务登录接口，获取访问令牌供后续步骤使用",
                    method: "POST",
                    url: "${env.services.auth.baseUrl}/api/v1/login",
                    requestMapping: {
                        headers: { "Content-Type": "application/json" },
                        body: { "userId": "${input.userId}", "grantType": "password" }
                    },
                    bodySchema: [
                        { name: "userId", label: "用户ID", remark: "登录账号标识", type: "string", required: true, batchEnabled: false },
                        { name: "grantType", label: "授权类型", remark: "OAuth2授权模式", type: "string", required: false, batchEnabled: false }
                    ],
                    bodyMapping: {
                        "userId": "${input.userId}",
                        "grantType": "password"
                    },
                    responseSchema: [
                        { name: "code", label: "响应码", remark: "业务状态码，200为成功", type: "string", required: false, batchEnabled: false, defaultValue: "200" },
                        { name: "message", label: "响应消息", remark: "服务端返回的描述信息", type: "string", required: false, batchEnabled: false, defaultValue: "success" },
                        { name: "data", label: "响应数据", remark: "业务数据载体", type: "object", required: false, batchEnabled: false, children: [
                            { name: "accessToken", label: "访问令牌", remark: "JWT格式Token，有效期2小时", type: "string", required: false, batchEnabled: false, defaultValue: "eyJhbGciOiJIUzI1NiJ9..." },
                            { name: "expiresIn", label: "过期时间", remark: "Token有效时长(秒)", type: "number", required: false, batchEnabled: false, defaultValue: 7200 }
                        ]}
                    ],
                    responseHandling: {
                        expectedContentType: "JSON",
                        statusCode: { success: [200] },
                        businessSuccess: { allOf: [{ path: "$.body.code", op: "EQ", value: "200" }] },
                        businessFailure: { anyOf: [] }
                    },
                    outputMapping: {
                        "accessToken": "$.body.data.accessToken",
                        "expiresIn": "$.body.data.expiresIn"
                    },
                    outputMeta: {
                        "accessToken": { label: "访问令牌", remark: "JWT格式，后续请求携带此Token鉴权" },
                        "expiresIn": { label: "过期时间", remark: "单位秒，默认7200" }
                    },
                    paramMapping: {},
                    httpParamMapping: {},
                    sqlParamMapping: {},
                    assertions: [],
                    assignments: {}
                },
                {
                    stepId: "check_inventory",
                    stepName: "2. 查询商品库存",
                    type: "SQL",
                    enabled: true,
                    dependsOn: ["user_login"],
                    description: "查询商品库存表，确认商品可用且库存充足",
                    operation: "SELECT",
                    datasource: "${env.datasources.tradeDb}",
                    sqlTemplateCode: "",
                    paramMapping: {
                        "productId": "${input.productId}"
                    },
                    outputMapping: {
                        "stock_num": "stock_num",
                        "product_status": "status"
                    },
                    outputMeta: {
                        "stock_num": { label: "库存数量", remark: "当前可售库存数" },
                        "product_status": { label: "商品状态", remark: "ON_SALE=在售, OFF_SHELF=已下架" }
                    },
                    requestMapping: {},
                    httpParamMapping: {},
                    sqlParamMapping: {},
                    assertions: [],
                    assignments: {}
                },
                {
                    stepId: "create_order",
                    stepName: "3. 创建交易订单",
                    type: "HTTP",
                    enabled: true,
                    dependsOn: ["user_login", "check_inventory"],
                    description: "携带登录Token调用交易中台创建订单",
                    method: "POST",
                    url: "${env.services.trade.baseUrl}/api/v2/orders/create",
                    requestMapping: {
                        headers: {
                            "Content-Type": "application/json",
                            "Authorization": "Bearer ${steps.user_login.outputs.accessToken}"
                        },
                        body: {
                            "requestNo": "${system.uuid}",
                            "timestamp": "${system.now}",
                            "buyer": { "id": "${input.userId}" },
                            "items": [ { "productId": "${input.productId}", "quantity": "${input.buyCount}" } ]
                        }
                    },
                    bodySchema: [
                        { name: "requestNo", label: "请求流水号", remark: "幂等键，防重复提交", type: "string", required: true, batchEnabled: false },
                        { name: "timestamp", label: "请求时间", remark: "下单时间戳", type: "string", required: true, batchEnabled: false },
                        { name: "buyer", label: "买家信息", remark: "购买者相关字段", type: "object", required: true, batchEnabled: false, children: [
                            { name: "id", label: "买家ID", remark: "买家用户编号", type: "string", required: true, batchEnabled: false }
                        ]},
                        { name: "items", label: "商品明细", remark: "下单商品列表", type: "array", required: true, batchEnabled: false, children: [
                            { name: "productId", label: "商品编号", remark: "SKU编号", type: "string", required: true, batchEnabled: false },
                            { name: "quantity", label: "购买数量", remark: "购买件数", type: "number", required: true, batchEnabled: false }
                        ]}
                    ],
                    bodyMapping: {
                        "requestNo": "${system.uuid}",
                        "timestamp": "${system.now}",
                        "buyer.id": "${input.userId}",
                        "items.productId": "${input.productId}",
                        "items.quantity": "${input.buyCount}"
                    },
                    responseSchema: [
                        { name: "success", label: "是否成功", remark: "业务处理结果标识", type: "boolean", required: false, batchEnabled: false, defaultValue: true },
                        { name: "errorCode", label: "错误码", remark: "失败时返回的错误编码", type: "string", required: false, batchEnabled: false },
                        { name: "errorMsg", label: "错误信息", remark: "失败时的错误描述", type: "string", required: false, batchEnabled: false },
                        { name: "data", label: "订单数据", remark: "成功时返回的订单详情", type: "object", required: false, batchEnabled: false, children: [
                            { name: "orderNo", label: "全局订单号", remark: "订单唯一标识，格式TD+日期+序号", type: "string", required: false, batchEnabled: false, defaultValue: "TD20260604889901" },
                            { name: "payAmount", label: "应付金额", remark: "订单实付金额(元)", type: "number", required: false, batchEnabled: false, defaultValue: 199.5 },
                            { name: "orderStatus", label: "订单状态", remark: "PENDING=待付款, PAID=已付款", type: "string", required: false, batchEnabled: false, defaultValue: "PENDING" }
                        ]}
                    ],
                    responseHandling: {
                        expectedContentType: "JSON",
                        statusCode: { success: [200] },
                        businessSuccess: { allOf: [{ path: "$.body.success", op: "EQ", value: "true" }] },
                        businessFailure: { anyOf: [{ path: "$.body.errorCode", op: "EXISTS", value: "" }] }
                    },
                    outputMapping: {
                        "orderNo": "$.body.data.orderNo",
                        "payAmount": "$.body.data.payAmount",
                        "orderStatus": "$.body.data.orderStatus"
                    },
                    outputMeta: {
                        "orderNo": { label: "全局订单号", remark: "订单唯一标识，用于后续查询和对账" },
                        "payAmount": { label: "应付金额", remark: "单位元，精确到分" },
                        "orderStatus": { label: "订单状态", remark: "PENDING=待付款" }
                    },
                    paramMapping: {},
                    httpParamMapping: {},
                    sqlParamMapping: {},
                    assertions: [],
                    assignments: {}
                },
                {
                    stepId: "record_order_log",
                    stepName: "4. 记录订单日志",
                    type: "SQL",
                    enabled: true,
                    dependsOn: ["create_order"],
                    description: "将订单创建结果写入日志表，便于后续审计追溯",
                    operation: "INSERT",
                    datasource: "${env.datasources.tradeDb}",
                    sqlTemplateCode: "",
                    paramMapping: {
                        "orderNo": "${steps.create_order.outputs.orderNo}",
                        "userId": "${input.userId}",
                        "productId": "${input.productId}",
                        "payAmount": "${steps.create_order.outputs.payAmount}"
                    },
                    outputMapping: {
                        "insert_id": "insert_id"
                    },
                    outputMeta: {
                        "insert_id": { label: "日志主键", remark: "自增ID，用于确认日志写入成功" }
                    },
                    requestMapping: {},
                    httpParamMapping: {},
                    sqlParamMapping: {},
                    assertions: [],
                    assignments: {}
                }
            ],
            resultSchema: [
                { name: "orderNo", label: "订单号", remark: "全局唯一订单号", type: "string", required: false, batchEnabled: false },
                { name: "payAmount", label: "应付金额", remark: "订单实付金额(元)", type: "number", required: false, batchEnabled: false },
                { name: "userId", label: "用户ID", remark: "下单用户标识", type: "string", required: false, batchEnabled: false },
                { name: "productId", label: "商品编号", remark: "购买商品SKU", type: "string", required: false, batchEnabled: false },
            ],
            resultMapping: {
                "$.orderNo": "${steps.create_order.outputs.orderNo}",
                "$.payAmount": "${steps.create_order.outputs.payAmount}",
                "$.userId": "${input.userId}",
                "$.productId": "${input.productId}",
            },
            errorPolicy: "STOP_ON_ERROR",
            batchConfig: {
                enabled: true,
                maxConcurrency: 5,
                failurePolicy: "CONTINUE_ON_ERROR"
            }
          });
          toast.success("演示场景生成成功！");
          void loadScenes();
      } catch (error) {
          toast.error("演示场景生成失败");
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
                  <td className="p-4">{scene.sceneType || "-"}</td>
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

      {/* Copy Dialog */}
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

      {/* Delete Dialog */}
      <Dialog open={!!deletingScene} onOpenChange={(open) => !open && setDeletingScene(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-destructive">确认删除</DialogTitle>
            <DialogDescription>
              您确定要删除场景 "{deletingScene?.sceneName}" 吗？此操作不可撤销，且会删除所有相关版本。
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
