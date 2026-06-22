/** MVP3 多场景编排验收测试 HTML 报告生成器 */

export interface TestResult {
  testCase: {
    id: string;
    name: string;
    description: string;
    category: string;
    goal: string;
    scene_code?: string;
    inputs: Record<string, unknown>;
    expectedSteps: string[];
    expectedVariablePassing: { from: string; to: string; variable: string }[];
  };
  status: "pending" | "running" | "passed" | "failed";
  taskRunId?: string;
  error?: string;
  timeline?: {
    variables: { name: string; value_preview: string; sensitive: boolean }[];
  };
  variableCheck: { passed: boolean; details: string[] }[];
  stepCheck: { passed: boolean; details: string[] }[];
  durationMs?: number;
  startedAt?: string;
  finishedAt?: string;
}

export interface SceneInfo {
  sceneCode: string;
  sceneName: string;
  tags?: string[];
  status: string;
  stepCount?: number;
}

export function generateHtmlReport(
  results: TestResult[],
  scenes: SceneInfo[],
): string {
  const passedCount = results.filter((r) => r.status === "passed").length;
  const failedCount = results.filter((r) => r.status === "failed").length;
  const totalCount = results.length;
  const passRate = totalCount > 0 ? ((passedCount / totalCount) * 100).toFixed(1) : "0.0";

  const now = new Date().toISOString();

  // Group results by category
  const categories = ["主流程", "变量传递", "边界 case", "错误处理", "回归"];
  const groupedResults: Record<string, TestResult[]> = {};
  for (const cat of categories) {
    groupedResults[cat] = results.filter((r) => r.testCase.category === cat);
  }

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MVP3 多场景编排验收测试报告</title>
<style>
  :root {
    --pass: #16a34a;
    --pass-bg: #f0fdf4;
    --fail: #dc2626;
    --fail-bg: #fef2f2;
    --warn: #f59e0b;
    --warn-bg: #fffbeb;
    --info: #3b82f6;
    --info-bg: #eff6ff;
    --border: #e5e7eb;
    --text: #1f2937;
    --text-muted: #6b7280;
    --bg: #f9fafb;
    --card-bg: #ffffff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 20px;
  }
  .container { max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 24px; margin-bottom: 4px; }
  h2 { font-size: 18px; margin-bottom: 12px; border-bottom: 2px solid var(--border); padding-bottom: 8px; }
  h3 { font-size: 15px; margin-bottom: 8px; }
  .subtitle { color: var(--text-muted); font-size: 14px; margin-bottom: 20px; }

  /* 概览卡片 */
  .overview { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .stat-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
  }
  .stat-value { font-size: 32px; font-weight: 700; }
  .stat-label { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
  .stat-pass .stat-value { color: var(--pass); }
  .stat-fail .stat-value { color: var(--fail); }
  .stat-total .stat-value { color: var(--info); }
  .stat-rate .stat-value { color: var(--warn); }

  /* 进度条 */
  .progress-bar {
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
    margin-top: 8px;
  }
  .progress-fill {
    height: 100%;
    background: var(--pass);
    border-radius: 4px;
    transition: width 0.3s;
  }

  /* 测试用例卡片 */
  .test-case {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 12px;
    overflow: hidden;
  }
  .test-case-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
  }
  .test-case-header.passed { background: var(--pass-bg); }
  .test-case-header.failed { background: var(--fail-bg); }
  .test-case-id { font-family: monospace; font-size: 13px; color: var(--text-muted); }
  .test-case-name { font-weight: 600; font-size: 14px; }
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
  }
  .badge-pass { background: var(--pass-bg); color: var(--pass); }
  .badge-fail { background: var(--fail-bg); color: var(--fail); }
  .badge-scene { background: var(--info-bg); color: var(--info); }
  .badge-category { background: #f3f4f6; color: var(--text-muted); }

  .test-case-body { padding: 12px 16px; }
  .test-case-description { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }

  /* 步骤链可视化 */
  .step-chain {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 12px;
  }
  .step-node {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
    font-family: monospace;
    border: 1px solid var(--border);
    background: #f9fafb;
  }
  .step-node.step-done { background: var(--pass-bg); border-color: var(--pass); color: var(--pass); }
  .step-node.step-failed { background: var(--fail-bg); border-color: var(--fail); color: var(--fail); }
  .step-arrow { color: var(--text-muted); font-size: 16px; }

  /* 变量传递可视化 */
  .var-flow {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
    padding: 8px;
    background: #f8fafc;
    border-radius: 4px;
    border: 1px dashed var(--border);
  }
  .var-flow-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
  }
  .var-name {
    font-family: monospace;
    font-weight: 600;
    color: var(--info);
  }
  .var-arrow { color: var(--text-muted); }

  /* 验证结果表格 */
  .verify-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin-top: 8px;
  }
  .verify-table th,
  .verify-table td {
    padding: 6px 10px;
    border: 1px solid var(--border);
    text-align: left;
  }
  .verify-table th {
    background: #f9fafb;
    font-weight: 600;
    font-size: 12px;
  }
  .verify-pass { color: var(--pass); font-weight: 600; }
  .verify-fail { color: var(--fail); font-weight: 600; }

  /* 输入参数 */
  .inputs-block {
    background: #f9fafb;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 8px 12px;
    font-family: monospace;
    font-size: 12px;
    margin-bottom: 12px;
    white-space: pre-wrap;
    word-break: break-all;
  }

  /* 错误信息 */
  .error-block {
    background: var(--fail-bg);
    border: 1px solid #fecaca;
    border-radius: 4px;
    padding: 8px 12px;
    color: var(--fail);
    font-size: 13px;
    margin-top: 8px;
  }

  /* 场景列表 */
  .scene-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 8px;
    margin-top: 12px;
  }
  .scene-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
  }
  .scene-card-header { display: flex; justify-content: space-between; align-items: center; }
  .scene-card-name { font-weight: 600; font-size: 13px; }
  .scene-card-code { font-family: monospace; font-size: 11px; color: var(--text-muted); }
  .scene-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
  .scene-tag {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 3px;
    background: #e5e7eb;
    color: var(--text-muted);
  }

  /* 变量列表 */
  .var-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
  }
  .var-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-family: monospace;
    background: var(--info-bg);
    border: 1px solid #bfdbfe;
    color: var(--info);
  }
  .var-chip.sensitive {
    background: var(--warn-bg);
    border-color: #fcd34d;
    color: #92400e;
  }
  .var-preview { color: var(--text-muted); font-size: 11px; }

  /* 添加数据的说明 */
  .added-data {
    background: var(--info-bg);
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 24px;
  }
  .added-data h3 { color: var(--info); margin-bottom: 8px; }
  .added-data ul { padding-left: 20px; font-size: 13px; }
  .added-data li { margin-bottom: 4px; }

  /* 底部 */
  .footer {
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    text-align: center;
    font-size: 12px;
    color: var(--text-muted);
  }

  /* 打印样式 */
  @media print {
    body { padding: 0; }
    .test-case { break-inside: avoid; }
    .no-print { display: none; }
  }
</style>
</head>
<body>
<div class="container">
  <h1>MVP3 多场景编排验收测试报告</h1>
  <p class="subtitle">
    生成时间: ${now} |
    测试总数: ${totalCount} |
    通过率: ${passRate}%
  </p>

  <!-- 概览 -->
  <div class="overview">
    <div class="stat-card stat-total">
      <div class="stat-value">${totalCount}</div>
      <div class="stat-label">测试总数</div>
    </div>
    <div class="stat-card stat-pass">
      <div class="stat-value">${passedCount}</div>
      <div class="stat-label">通过</div>
    </div>
    <div class="stat-card stat-fail">
      <div class="stat-value">${failedCount}</div>
      <div class="stat-label">失败</div>
    </div>
    <div class="stat-card stat-rate">
      <div class="stat-value">${passRate}%</div>
      <div class="stat-label">通过率</div>
    </div>
  </div>
  <div class="progress-bar">
    <div class="progress-fill" style="width: ${passRate}%"></div>
  </div>

  <!-- 本次添加的测试数据说明 -->
  <div class="added-data">
    <h3>📦 本次添加的 MVP3 测试数据</h3>
    <ul>
      <li><strong>HTTP Mock 接口 (10个):</strong> /api/v1/orders/create, /api/v1/payments/pay, /api/v1/orders/{id}/status, /api/v1/inventory/check, /api/v1/orders/{id}/confirm, /api/v1/payments/{id}/receipt, /api/v1/notifications/send, /api/v1/orders/{id}/cancel, /api/v1/health/detailed, /api/v1/batch/execute</li>
      <li><strong>HTTP Source 配置 (10个):</strong> httpMvp3CreateOrder, httpMvp3PayOrder, httpMvp3QueryOrderStatus, httpMvp3CheckInventory, httpMvp3ConfirmOrder, httpMvp3SendNotification, httpMvp3BatchExecute, httpMvp3CancelOrder, httpMvp3HealthCheck, httpMvp3GetPaymentReceipt</li>
      <li><strong>MVP3 测试场景 (7个):</strong> mvp3_create_order_and_pay (3步), mvp3_full_trade_flow (5步), mvp3_create_and_confirm (2步), mvp3_query_payment_receipt (1步), mvp3_batch_execute (1步), mvp3_cancel_order (1步), mvp3_health_check (1步)</li>
      <li><strong>测试覆盖:</strong> 变量传递 (order_id, amount, payment_id)、多步骤依赖、边界 case、错误处理</li>
    </ul>
  </div>

  <!-- 测试结果按分类展示 -->
  ${categories
    .map(
      (cat) => `
  <h2>${cat} (${groupedResults[cat]?.length ?? 0})</h2>
  ${(groupedResults[cat] ?? [])
    .map(
      (result, idx) => `
  <div class="test-case">
    <div class="test-case-header ${result.status}">
      <div>
        <span class="test-case-id">${result.testCase.id}</span>
        <span class="test-case-name">${result.testCase.name}</span>
      </div>
      <span class="badge ${result.status === "passed" ? "badge-pass" : "badge-fail"}">
        ${result.status === "passed" ? "✓ 通过" : result.status === "running" ? "⟳ 运行中" : "✗ 失败"}
      </span>
    </div>
    <div class="test-case-body">
      <p class="test-case-description">${result.testCase.description}</p>

      <!-- 场景编码 -->
      ${result.testCase.scene_code ? `
      <div style="margin-bottom: 8px;">
        <span class="badge badge-scene">场景: ${result.testCase.scene_code}</span>
        <span class="badge badge-category">${result.testCase.category}</span>
      </div>` : ""}

      <!-- 输入参数 -->
      <h3>输入参数</h3>
      <div class="inputs-block">${formatJson(result.testCase.inputs)}</div>

      <!-- 步骤链可视化 -->
      <h3>步骤执行链</h3>
      <div class="step-chain">
        ${result.testCase.expectedSteps
          .map(
            (stepId, i) => {
              const stepResult = result.stepCheck[i];
              const stepClass = stepResult?.passed ? "step-done" : "step-failed";
              return `<span class="step-node ${stepClass}">Step${i + 1}: ${stepId}</span>${
                i < result.testCase.expectedSteps.length - 1 ? '<span class="step-arrow">→</span>' : ""
              }`;
            },
          )
          .join("")}
      </div>

      <!-- 步骤验证结果 -->
      <h3>步骤验证</h3>
      <table class="verify-table">
        <thead><tr><th>步骤</th><th>ID</th><th>结果</th><th>详情</th></tr></thead>
        <tbody>
          ${result.stepCheck
            .map(
              (sc, i) => `
          <tr>
            <td>Step ${i + 1}</td>
            <td><code>${result.testCase.expectedSteps[i] || "N/A"}</code></td>
            <td class="${sc.passed ? "verify-pass" : "verify-fail"}">${sc.passed ? "✓ PASS" : "✗ FAIL"}</td>
            <td>${sc.details.join("; ")}</td>
          </tr>`,
            )
            .join("")}
        </tbody>
      </table>

      <!-- 变量传递验证 -->
      ${result.testCase.expectedVariablePassing.length > 0 ? `
      <h3 style="margin-top: 12px;">变量传递验证</h3>
      <div class="var-flow">
        ${result.testCase.expectedVariablePassing
          .map(
            (vp) => `
        <div class="var-flow-item">
          <span>${vp.from}</span>
          <span class="var-arrow">→</span>
          <span>${vp.to}</span>
          <span class="var-arrow">:</span>
          <span class="var-name">${vp.variable}</span>
        </div>`,
          )
          .join("")}
      </div>
      <table class="verify-table">
        <thead><tr><th>来源</th><th>目标</th><th>变量</th><th>结果</th><th>详情</th></tr></thead>
        <tbody>
          ${result.variableCheck
            .map(
              (vc, i) => {
                const vp = result.testCase.expectedVariablePassing[i];
                return `
            <tr>
              <td>${vp?.from ?? "?"}</td>
              <td>${vp?.to ?? "?"}</td>
              <td><span class="var-name">${vp?.variable ?? "?"}</span></td>
              <td class="${vc.passed ? "verify-pass" : "verify-fail"}">${vc.passed ? "✓ PASS" : "✗ FAIL"}</td>
              <td>${vc.details.join("; ")}</td>
            </tr>`;
              },
            )
            .join("")}
        </tbody>
      </table>` : ""}

      <!-- 产出变量 -->
      ${result.timeline?.variables && result.timeline.variables.length > 0 ? `
      <h3 style="margin-top: 12px;">产出变量 (${result.timeline.variables.length})</h3>
      <div class="var-list">
        ${result.timeline.variables
          .map(
            (v) => `
        <span class="var-chip ${v.sensitive ? "sensitive" : ""}">
          ${v.name} = ${v.value_preview}
          ${v.sensitive ? "🔒" : ""}
        </span>`,
          )
          .join("")}
      </div>` : ""}

      <!-- 错误信息 -->
      ${result.error ? `<div class="error-block">⚠ ${result.error}</div>` : ""}

      <!-- 执行信息 -->
      <div style="margin-top: 8px; font-size: 12px; color: var(--text-muted);">
        TaskRun: ${result.taskRunId || "N/A"} |
        耗时: ${result.durationMs ?? "—"}ms |
        开始: ${result.startedAt || "—"} |
        结束: ${result.finishedAt || "—"}
      </div>
    </div>
  </div>`,
    )
    .join("")}
  `,
    )
    .join("")}
  ${categories
    .filter((cat) => (groupedResults[cat] ?? []).length === 0)
    .map((cat) => `<h2>${cat} (0)</h2><p style="color: var(--text-muted); font-size: 13px;">暂无测试结果</p>`)
    .join("")}

  <!-- 已发布场景列表 -->
  <h2>已发布场景 (${scenes.length})</h2>
  <div class="scene-list">
    ${scenes
      .map(
        (scene) => `
    <div class="scene-card">
      <div class="scene-card-header">
        <span class="scene-card-name">${scene.sceneName}</span>
        <span class="badge ${scene.status === "PUBLISHED" ? "badge-pass" : "badge-fail"}">${scene.status}</span>
      </div>
      <div class="scene-card-code">${scene.sceneCode}</div>
      <div class="scene-card-tags">
        ${(scene.tags ?? []).map((tag) => `<span class="scene-tag">${tag}</span>`).join("")}
        <span class="scene-tag">${scene.stepCount ?? 0} 步</span>
      </div>
    </div>`,
      )
      .join("")}
  </div>

  <div class="footer">
    MVP3 多场景编排验收测试报告 | 生成于 ${now} | DeerFlow GDP Agent Runtime
  </div>
</div>
</body>
</html>`;
}

function formatJson(obj: Record<string, unknown>): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}
