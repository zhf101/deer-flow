"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

import {
  createAgentRuntimeTaskRun,
  getAgentRuntimeTaskRun,
  getAgentRuntimeTimeline,
  listScenes,
  startAgentRuntimeTaskRun,
} from "../common/lib/api";
import type {
  AgentRuntimeTaskRunResponse,
  AgentRuntimeTimelineResponse,
  SceneSummary,
} from "../common/lib/types";
import { generateHtmlReport } from "./report-generator";

/* ============================================================
   MVP3 多场景编排验收测试用例定义
   ============================================================ */

interface TestCase {
  id: string;
  name: string;
  description: string;
  category: "主流程" | "变量传递" | "边界 case" | "错误处理" | "回归";
  goal: string;
  scene_code?: string;
  inputs: Record<string, unknown>;
  expectedSteps: string[];
  expectedVariablePassing: { from: string; to: string; variable: string }[];
  approved?: boolean;
}

const MVP3_TEST_CASES: TestCase[] = [
  // ── 主流程 ──────────────────────────────────────────
  {
    id: "TC-001",
    name: "创建订单并支付（3步主流程）",
    description: "验证三步串联：创建订单 → 支付订单 → 查询订单状态，order_id 从 Step1 传递到 Step2/Step3",
    category: "主流程",
    goal: "创建订单并支付",
    scene_code: "mvp3_create_order_and_pay",
    inputs: {
      buyer_id: "U10001",
      product_id: "SKU10001",
      quantity: 1,
      amount: 299.0,
      payment_method: "ALIPAY",
      approved: true,
    },
    expectedSteps: ["mvp3_create_order", "mvp3_pay_order", "mvp3_query_order_status"],
    expectedVariablePassing: [
      { from: "Step1", to: "Step2", variable: "order_id" },
      { from: "Step1", to: "Step3", variable: "order_id" },
      { from: "Step2", to: "Step3", variable: "pay_status" },
    ],
  },
  {
    id: "TC-002",
    name: "完整交易流程（5步）",
    description: "验证五步串联：检查库存 → 创建订单 → 确认订单 → 支付订单 → 发送通知，多级变量传递",
    category: "主流程",
    goal: "完成一笔完整交易",
    scene_code: "mvp3_full_trade_flow",
    inputs: {
      buyer_id: "U10001",
      product_id: "SKU10001",
      quantity: 2,
      amount: 598.0,
      payment_method: "WECHAT",
      notify_channel: "SMS",
      approved: true,
    },
    expectedSteps: [
      "mvp3_check_inventory",
      "mvp3_create_order_v2",
      "mvp3_confirm_order",
      "mvp3_pay_order_v2",
      "mvp3_send_notification",
    ],
    expectedVariablePassing: [
      { from: "Step1", to: "Step2", variable: "available" },
      { from: "Step2", to: "Step3", variable: "order_id" },
      { from: "Step2", to: "Step4", variable: "order_id" },
      { from: "Step2", to: "Step5", variable: "order_id" },
      { from: "Step4", to: "Step5", variable: "payment_id" },
    ],
  },
  // ── 变量传递 ────────────────────────────────────────
  {
    id: "TC-003",
    name: "order_id 跨步骤传递验证",
    description: "验证 order_id 从创建订单步骤正确传递到支付和查询步骤",
    category: "变量传递",
    goal: "创建订单并支付",
    scene_code: "mvp3_create_order_and_pay",
    inputs: {
      buyer_id: "U10002",
      product_id: "SKU10002",
      quantity: 1,
      amount: 129.0,
      payment_method: "WECHAT",
      approved: true,
    },
    expectedSteps: ["mvp3_create_order", "mvp3_pay_order", "mvp3_query_order_status"],
    expectedVariablePassing: [
      { from: "Step1", to: "Step2", variable: "order_id" },
      { from: "Step1", to: "Step3", variable: "order_id" },
    ],
  },
  {
    id: "TC-004",
    name: "多级变量传递（order_id + amount + payment_id）",
    description: "验证 order_id、amount 从 Step1 传递到 Step2，payment_id 从 Step2 传递到 Step5",
    category: "变量传递",
    goal: "完成一笔完整交易",
    scene_code: "mvp3_full_trade_flow",
    inputs: {
      buyer_id: "U10003",
      product_id: "SKU10001",
      quantity: 3,
      amount: 897.0,
      payment_method: "ALIPAY",
      notify_channel: "EMAIL",
      approved: true,
    },
    expectedSteps: [
      "mvp3_check_inventory",
      "mvp3_create_order_v2",
      "mvp3_confirm_order",
      "mvp3_pay_order_v2",
      "mvp3_send_notification",
    ],
    expectedVariablePassing: [
      { from: "Step1", to: "Step2", variable: "available" },
      { from: "Step2", to: "Step3", variable: "order_id" },
      { from: "Step2", to: "Step4", variable: "order_id" },
      { from: "Step2", to: "Step4", variable: "amount" },
      { from: "Step2", to: "Step5", variable: "order_id" },
      { from: "Step4", to: "Step5", variable: "payment_id" },
    ],
  },
  // ── 边界 case ────────────────────────────────────────
  {
    id: "TC-005",
    name: "单步场景兼容（创建并确认订单）",
    description: "验证单 Step 场景仍能正常执行，不破坏第二阶段兼容性",
    category: "边界 case",
    goal: "创建并确认订单",
    scene_code: "mvp3_create_and_confirm",
    inputs: {
      buyer_id: "U10004",
      amount: 199.0,
      approved: true,
    },
    expectedSteps: ["mvp3_create_simple_order", "mvp3_confirm_simple_order"],
    expectedVariablePassing: [
      { from: "Step1", to: "Step2", variable: "order_id" },
    ],
  },
  {
    id: "TC-006",
    name: "纯查询场景（查询支付凭证）",
    description: "验证纯查询场景无副作用，自动执行",
    category: "边界 case",
    goal: "查询支付凭证",
    scene_code: "mvp3_query_payment_receipt",
    inputs: {
      payment_id: "PAY-TEST-001",
    },
    expectedSteps: ["mvp3_query_receipt"],
    expectedVariablePassing: [],
  },
  {
    id: "TC-007",
    name: "批量执行场景",
    description: "验证批量接口场景正常执行",
    category: "边界 case",
    goal: "批量创建订单",
    scene_code: "mvp3_batch_execute",
    inputs: {
      buyer_id: "U10005",
      amount: 99.0,
      payment_method: "ALIPAY",
    },
    expectedSteps: ["mvp3_batch_execute"],
    expectedVariablePassing: [],
  },
  // ── 错误处理 ────────────────────────────────────────
  {
    id: "TC-008",
    name: "健康检查（无副作用）",
    description: "验证健康检查场景无副作用，自动执行",
    category: "错误处理",
    goal: "检查系统健康状态",
    scene_code: "mvp3_health_check",
    inputs: {},
    expectedSteps: ["mvp3_health_check"],
    expectedVariablePassing: [],
  },
  {
    id: "TC-009",
    name: "取消订单场景",
    description: "验证取消订单场景正常执行",
    category: "错误处理",
    goal: "取消订单",
    scene_code: "mvp3_cancel_order",
    inputs: {
      order_id: "ORD-TEST-001",
      reason: "测试取消",
    },
    expectedSteps: ["mvp3_cancel_order"],
    expectedVariablePassing: [],
  },
];

/* ============================================================
   测试执行状态
   ============================================================ */

interface TestResult {
  testCase: TestCase;
  status: "pending" | "running" | "passed" | "failed";
  taskRunId?: string;
  error?: string;
  timeline?: AgentRuntimeTimelineResponse;
  variableCheck: { passed: boolean; details: string[] }[];
  stepCheck: { passed: boolean; details: string[] }[];
  durationMs?: number;
  startedAt?: string;
  finishedAt?: string;
}

/* ============================================================
   组件
   ============================================================ */

export function Mvp3TestRunnerPage() {
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [selectedTests, setSelectedTests] = useState<Set<string>>(new Set(MVP3_TEST_CASES.map((t) => t.id)));
  const [results, setResults] = useState<TestResult[]>([]);
  const [running, setRunning] = useState(false);
  const [reportHtml, setReportHtml] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("runner");
  const abortRef = useRef(false);

  // 加载场景列表
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listScenes({ status: "PUBLISHED", limit: 100 });
        if (!cancelled) setScenes(data);
      } catch (err) {
        if (!cancelled) toast.error("加载场景列表失败");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleTest = useCallback((id: string) => {
    setSelectedTests((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedTests(new Set(MVP3_TEST_CASES.map((t) => t.id)));
  }, []);

  const clearAll = useCallback(() => {
    setSelectedTests(new Set());
  }, []);

  /* ── 运行单个测试用例 ── */
  const runSingleTest = useCallback(
    async (testCase: TestCase): Promise<TestResult> => {
      const startedAt = new Date().toISOString();
      const startTime = Date.now();

      // 1. 创建 TaskRun
      let taskRun: AgentRuntimeTaskRunResponse;
      try {
        taskRun = await createAgentRuntimeTaskRun({
          user_goal: testCase.goal,
          env_code: "dev",
        });
      } catch (err) {
        return {
          testCase,
          status: "failed",
          error: `创建任务失败: ${err instanceof Error ? err.message : String(err)}`,
          variableCheck: [],
          stepCheck: [],
          startedAt,
          finishedAt: new Date().toISOString(),
          durationMs: Date.now() - startTime,
        };
      }

      // 2. 启动任务
      let taskRunAfterStart: AgentRuntimeTaskRunResponse;
      try {
        taskRunAfterStart = await startAgentRuntimeTaskRun(taskRun.task_run_id, {
          scene_code: testCase.scene_code || null,
          inputs: testCase.inputs,
        });
      } catch (err) {
        return {
          testCase,
          status: "failed",
          taskRunId: taskRun.task_run_id,
          error: `启动任务失败: ${err instanceof Error ? err.message : String(err)}`,
          variableCheck: [],
          stepCheck: [],
          startedAt,
          finishedAt: new Date().toISOString(),
          durationMs: Date.now() - startTime,
        };
      }

      // 3. 轮询等待完成
      const POLL_MS = 2000;
      const MAX_POLLS = 60; // 2 minutes max
      let timeline: AgentRuntimeTimelineResponse | null = null;
      let finalStatus = taskRunAfterStart.status;

      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((r) => setTimeout(r, POLL_MS));

        try {
          const current = await getAgentRuntimeTaskRun(taskRun.task_run_id);
          finalStatus = current.status;
          if (
            finalStatus === "COMPLETED" ||
            finalStatus === "FAILED" ||
            finalStatus === "CANCELLED" ||
            finalStatus === "WAITING_USER"
          ) {
            break;
          }
        } catch {
          // continue polling
        }
      }

      // 4. 获取 timeline
      try {
        timeline = await getAgentRuntimeTimeline(taskRun.task_run_id);
      } catch {
        // timeline fetch failed, use basic status
      }

      const finishedAt = new Date().toISOString();
      const durationMs = Date.now() - startTime;
      const isPassed = finalStatus === "COMPLETED";

      // 5. 验证步骤执行
      const stepCheck = verifySteps(testCase, timeline);
      const variableCheck = verifyVariablePassing(testCase, timeline);

      return {
        testCase,
        status: isPassed ? "passed" : "failed",
        taskRunId: taskRun.task_run_id,
        timeline: timeline ?? undefined,
        stepCheck,
        variableCheck,
        error: finalStatus === "WAITING_USER" ? "任务等待用户输入" : finalStatus === "FAILED" ? "任务执行失败" : undefined,
        startedAt,
        finishedAt,
        durationMs,
      };
    },
    [],
  );

  /* ── 验证步骤 ── */
  function verifySteps(testCase: TestCase, timeline: AgentRuntimeTimelineResponse | null) {
    const checks: { passed: boolean; details: string[] }[] = [];
    if (!timeline) {
      return testCase.expectedSteps.map((stepId) => ({
        passed: false,
        details: ["无法获取 timeline 数据"],
      }));
    }

    const stepMap = new Map(timeline.steps.map((s) => [s.step_id, s]));

    for (const expectedStepId of testCase.expectedSteps) {
      const step = stepMap.get(expectedStepId);
      if (!step) {
        checks.push({ passed: false, details: [`步骤 ${expectedStepId} 未找到`] });
        continue;
      }
      const details: string[] = [
        `步骤序号: ${step.step_no}`,
        `目标: ${step.goal}`,
        `状态: ${step.status}`,
        `依赖: ${step.depends_on.join(", ") || "无"}`,
      ];
      if (step.status === "DONE") {
        details.push("执行成功");
      } else if (step.status === "FAILED") {
        details.push("执行失败");
      } else {
        details.push(`未完成 (${step.status})`);
      }
      checks.push({ passed: step.status === "DONE", details });
    }

    return checks;
  }

  /* ── 验证变量传递 ── */
  function verifyVariablePassing(
    testCase: TestCase,
    timeline: AgentRuntimeTimelineResponse | null,
  ) {
    const checks: { passed: boolean; details: string[] }[] = [];
    if (!timeline || testCase.expectedVariablePassing.length === 0) {
      return testCase.expectedVariablePassing.map((vp) => ({
        passed: false,
        details: ["无法验证 — timeline 数据缺失"],
      }));
    }

    // Build variable map
    const varMap = new Map(timeline.variables.map((v) => [v.name, v]));
    // Build step map
    const stepMap = new Map(timeline.steps.map((s) => [s.step_id, s]));

    // Build edge map: from_step_id -> [to_step_id, variable_ids]
    const edgeMap = new Map<string, { toStepIds: Set<string>; varIds: Set<string> }>();
    for (const edge of timeline.step_edges) {
      const existing = edgeMap.get(edge.from_step_id) ?? { toStepIds: new Set(), varIds: new Set() };
      existing.toStepIds.add(edge.to_step_id);
      for (const vid of edge.variable_ids) existing.varIds.add(vid);
      edgeMap.set(edge.from_step_id, existing);
    }

    // Find step numbers from step_ids
    const stepIdToNo = new Map<string, number>();
    for (const step of timeline.steps) stepIdToNo.set(step.step_id, step.step_no);

    for (const vp of testCase.expectedVariablePassing) {
      // Find from step by step number
      const fromStepNo = parseInt(vp.from.replace("Step", ""), 10);
      const toStepNo = parseInt(vp.to.replace("Step", ""), 10);

      const fromStep = timeline.steps.find((s) => s.step_no === fromStepNo);
      const toStep = timeline.steps.find((s) => s.step_no === toStepNo);

      if (!fromStep || !toStep) {
        checks.push({
          passed: false,
          details: [`找不到步骤 (${vp.from} / ${vp.to})`],
        });
        continue;
      }

      // Check if the variable exists
      const variable = varMap.get(vp.variable);
      const varExists = !!variable;

      // Check if from step produces this variable
      const fromProduces = fromStep.produces.includes(variable?.variable_id ?? "");

      // Check if to step consumes this variable
      const toConsumes = toStep.consumes.includes(variable?.variable_id ?? "");

      // Check step edge
      const edge = edgeMap.get(fromStep.step_id);
      const hasEdge = edge?.toStepIds.has(toStep.step_id) ?? false;

      const allPassed = varExists && fromProduces && toConsumes;

      const details: string[] = [
        `变量: ${vp.variable}`,
        `存在: ${varExists ? "是" : "否"}${variable ? ` (preview: ${variable.value_preview})` : ""}`,
        `Step${fromStepNo} 产出: ${fromProduces ? "是" : "否"}`,
        `Step${toStepNo} 消费: ${toConsumes ? "是" : "否"}`,
        `步骤边: ${hasEdge ? "存在" : "不存在"}`,
      ];

      checks.push({ passed: allPassed, details });
    }

    return checks;
  }

  /* ── 运行所有选中测试 ── */
  const runAllTests = useCallback(async () => {
    if (selectedTests.size === 0) {
      toast.warning("请至少选择一个测试用例");
      return;
    }

    abortRef.current = false;
    setRunning(true);
    setResults([]);
    setReportHtml(null);

    const testCases = MVP3_TEST_CASES.filter((tc) => selectedTests.has(tc.id));

    const newResults: TestResult[] = [];
    for (const tc of testCases) {
      if (abortRef.current) break;

      // Update UI to show running
      setResults((prev) => [...prev, { testCase: tc, status: "running", variableCheck: [], stepCheck: [] }]);

      try {
        const result = await runSingleTest(tc);
        newResults.push(result);
        setResults((prev) => {
          const updated = [...prev];
          const idx = updated.findIndex((r) => r.testCase.id === tc.id);
          if (idx >= 0) updated[idx] = result;
          return updated;
        });

        if (result.status === "passed") {
          toast.success(`${tc.id}: ${tc.name} — 通过`);
        } else {
          toast.error(`${tc.id}: ${tc.name} — 失败: ${result.error || "验证未通过"}`);
        }
      } catch (err) {
        const failed: TestResult = {
          testCase: tc,
          status: "failed",
          error: err instanceof Error ? err.message : String(err),
          variableCheck: [],
          stepCheck: [],
        };
        newResults.push(failed);
        setResults((prev) => {
          const updated = [...prev];
          const idx = updated.findIndex((r) => r.testCase.id === tc.id);
          if (idx >= 0) updated[idx] = failed;
          return updated;
        });
        toast.error(`${tc.id}: ${tc.name} — 异常`);
      }
    }

    setRunning(false);

    // Generate HTML report
    if (newResults.length > 0) {
      const html = generateHtmlReport(newResults, scenes);
      setReportHtml(html);
      setActiveTab("report");
    }
  }, [selectedTests, runSingleTest, scenes]);

  const abortTests = useCallback(() => {
    abortRef.current = true;
    setRunning(false);
    toast.info("测试已中断");
  }, []);

  /* ── 统计 ── */
  const passedCount = results.filter((r) => r.status === "passed").length;
  const failedCount = results.filter((r) => r.status === "failed").length;
  const totalCount = results.length;

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* ── 头部 ── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-lg">MVP3 多场景编排验收测试台</span>
            <Badge variant="outline">浏览器端测试</Badge>
          </CardTitle>
          <CardDescription>
            从浏览器发起真实的 HTTP 请求，模拟用户操作完成 MVP3 多场景编排验收测试。测试涉及变量引用、多场景步骤变量传递、边界 case 等。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button onClick={selectAll} variant="outline" size="sm" disabled={running}>
              全选
            </Button>
            <Button onClick={clearAll} variant="outline" size="sm" disabled={running}>
              清空
            </Button>
            <Separator orientation="vertical" className="h-8" />
            <Button onClick={runAllTests} disabled={running || selectedTests.size === 0} size="sm">
              {running ? "运行中..." : `运行选中测试 (${selectedTests.size})`}
            </Button>
            {running && (
              <Button onClick={abortTests} variant="destructive" size="sm">
                中断
              </Button>
            )}
            <Separator orientation="vertical" className="h-8" />
            <span className="flex items-center gap-4 text-sm text-muted-foreground">
              <span>通过: <strong className="text-emerald-600">{passedCount}</strong></span>
              <span>失败: <strong className="text-red-600">{failedCount}</strong></span>
              <span>总计: <strong>{totalCount}</strong></span>
            </span>
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="runner">测试用例</TabsTrigger>
          <TabsTrigger value="results">执行结果 ({totalCount})</TabsTrigger>
          <TabsTrigger value="report" disabled={!reportHtml}>HTML 报告</TabsTrigger>
          <TabsTrigger value="scenes">已发布场景 ({scenes.length})</TabsTrigger>
        </TabsList>

        {/* ── 测试用例列表 ── */}
        <TabsContent value="runner" className="space-y-3">
          {["主流程", "变量传递", "边界 case", "错误处理", "回归"].map((category) => {
            const cases = MVP3_TEST_CASES.filter((tc) => tc.category === category);
            if (cases.length === 0) return null;
            return (
              <Card key={category}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">{category}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {cases.map((tc) => (
                    <div
                      key={tc.id}
                      className={`flex items-start gap-3 rounded-md border p-3 transition-colors ${
                        selectedTests.has(tc.id) ? "border-primary bg-primary/5" : "border-border"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedTests.has(tc.id)}
                        onChange={() => toggleTest(tc.id)}
                        disabled={running}
                        className="mt-1 h-4 w-4"
                      />
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-muted-foreground">{tc.id}</span>
                          <span className="font-medium text-sm">{tc.name}</span>
                          {tc.scene_code && (
                            <Badge variant="secondary" className="text-xs">
                              {tc.scene_code}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{tc.description}</p>
                        {tc.expectedVariablePassing.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-1">
                            {tc.expectedVariablePassing.map((vp, i) => (
                              <Badge key={i} variant="outline" className="text-xs">
                                {vp.from} → {vp.to}: {vp.variable}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        {/* ── 执行结果 ── */}
        <TabsContent value="results">
          {results.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                尚未执行任何测试，请选择测试用例并点击"运行选中测试"
              </CardContent>
            </Card>
          ) : (
            <ScrollArea className="h-[600px]">
              <div className="space-y-3">
                {results.map((result, idx) => (
                  <Card key={idx}>
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-muted-foreground">{result.testCase.id}</span>
                          <CardTitle className="text-sm">{result.testCase.name}</CardTitle>
                        </div>
                        <Badge
                          variant={
                            result.status === "passed"
                              ? "default"
                              : result.status === "running"
                                ? "secondary"
                                : "destructive"
                          }
                        >
                          {result.status === "passed"
                            ? "通过"
                            : result.status === "running"
                              ? "运行中"
                              : "失败"}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {/* 基本信息 */}
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-muted-foreground">场景编码: </span>
                          <code className="font-mono">{result.testCase.scene_code || "自动搜索"}</code>
                        </div>
                        <div>
                          <span className="text-muted-foreground">目标: </span>
                          <code className="font-mono">{result.testCase.goal}</code>
                        </div>
                        <div>
                          <span className="text-muted-foreground">TaskRun ID: </span>
                          <code className="font-mono">{result.taskRunId || "N/A"}</code>
                        </div>
                        <div>
                          <span className="text-muted-foreground">耗时: </span>
                          <span>{result.durationMs ?? "—"}ms</span>
                        </div>
                      </div>

                      {result.error && (
                        <div className="rounded-md bg-destructive/10 p-2 text-xs text-destructive">
                          {result.error}
                        </div>
                      )}

                      {/* 步骤验证 */}
                      <div>
                        <h4 className="mb-1 text-xs font-medium">步骤验证</h4>
                        <div className="space-y-1">
                          {result.stepCheck.map((sc, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs">
                              <span className={sc.passed ? "text-emerald-600" : "text-red-600"}>
                                {sc.passed ? "✓" : "✗"}
                              </span>
                              <span className="text-muted-foreground">
                                {result.testCase.expectedSteps[i] || `步骤 ${i + 1}`}: {sc.details.join("; ")}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* 变量传递验证 */}
                      {result.variableCheck.length > 0 && (
                        <div>
                          <h4 className="mb-1 text-xs font-medium">变量传递验证</h4>
                          <div className="space-y-1">
                            {result.variableCheck.map((vc, i) => (
                              <div key={i} className="flex items-start gap-2 text-xs">
                                <span className={vc.passed ? "text-emerald-600" : "text-red-600"}>
                                  {vc.passed ? "✓" : "✗"}
                                </span>
                                <span className="text-muted-foreground">
                                  {result.testCase.expectedVariablePassing[i]
                                    ? `${result.testCase.expectedVariablePassing[i].from} → ${result.testCase.expectedVariablePassing[i].to}: ${result.testCase.expectedVariablePassing[i].variable}`
                                    : `变量 ${i + 1}`}
                                  : {vc.details.join("; ")}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Timeline 变量快照 */}
                      {result.timeline?.variables && result.timeline.variables.length > 0 && (
                        <div>
                          <h4 className="mb-1 text-xs font-medium">产出变量</h4>
                          <div className="flex flex-wrap gap-1">
                            {result.timeline.variables.map((v) => (
                              <Badge key={v.variable_id} variant="outline" className="text-xs">
                                {v.name} = {v.value_preview}
                                {v.sensitive && <span className="ml-1 text-amber-600">[敏感]</span>}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </ScrollArea>
          )}
        </TabsContent>

        {/* ── HTML 报告 ── */}
        <TabsContent value="report">
          {!reportHtml ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                运行测试后将在此展示 HTML 报告
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">MVP3 多场景编排验收测试报告</CardTitle>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const blob = new Blob([reportHtml], { type: "text/html" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `mvp3-test-report-${new Date().toISOString().slice(0, 10)}.html`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    下载报告
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <iframe
                  srcDoc={reportHtml}
                  className="h-[700px] w-full rounded-md border"
                  title="MVP3 测试报告"
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── 已发布场景 ── */}
        <TabsContent value="scenes">
          <ScrollArea className="h-[600px]">
            <div className="space-y-2">
              {scenes.map((scene) => (
                <Card key={scene.id}>
                  <CardContent className="py-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-medium text-sm">{scene.sceneName}</span>
                        <code className="ml-2 text-xs text-muted-foreground">{scene.sceneCode}</code>
                      </div>
                      <Badge variant={scene.status === "PUBLISHED" ? "default" : "secondary"}>
                        {scene.status}
                      </Badge>
                    </div>
                    {scene.tags && scene.tags.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {scene.tags.map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default Mvp3TestRunnerPage;
