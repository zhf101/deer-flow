/**
 * ============================================================================
 * 模板工具：HTTP Source / SQL Source → 步骤映射、hash 计算、偏离检测
 * ============================================================================
 *
 * 用于将已配置好的 HTTP 接口模板（HttpSource）或 SQL 模板（SqlSource）
 * 导入为场景编排中的步骤（HttpStepDefinition / SqlStepDefinition）。
 *
 * 导入后会生成 StepTemplateRef 快照，记录来源信息和 hash，
 * 用于后续的偏离检测和重新同步。
 */

import { createDefaultHttpTimeoutConfig } from "./defaults";
import type {
  HttpSourceResponse,
  HttpStepDefinition,
  SqlSourceResponse,
  SqlStepDefinition,
  StepDefinition,
} from "./types";

// ── 稳定 hash 工具 ─────────────────────────────────────────────────────────

/** 简单的字符串 hash（FNV-1a 32-bit），用于偏离检测，非加密用途 */
function fnv1aHash(str: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = (hash * 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

/** 递归排序对象所有层级的 key，确保 JSON.stringify 输出稳定 */
function deepSortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(deepSortKeys);
  if (value !== null && typeof value === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      sorted[key] = deepSortKeys((value as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return value;
}

/** 将对象序列化后计算 hash，排除不稳定的审计字段 */
function stableHash(obj: Record<string, unknown>, excludeKeys: string[]): string {
  const filtered: Record<string, unknown> = {};
  for (const key of Object.keys(obj).sort()) {
    if (excludeKeys.includes(key)) continue;
    filtered[key] = deepSortKeys(obj[key]);
  }
  return fnv1aHash(JSON.stringify(filtered));
}

// ── 审计字段排除列表 ──────────────────────────────────────────────────────

/** Source 响应中不参与业务 hash 的字段 */
const SOURCE_AUDIT_KEYS = [
  "id", "createdAt", "updatedAt", "createdBy", "updatedBy", "status",
];

/** Step 配置中不参与 configHash 的字段 */
const STEP_NON_CONFIG_KEYS = [
  "stepId", "stepName", "executionOrder", "enabled", "dependsOn",
  "description", "position", "templateRef", "type",
  "sourceName", // 仅用于展示，不参与配置对比
];

// ── HTTP Source → Step 映射 ──────────────────────────────────────────────

/** 从 HTTP Source 计算业务配置 hash（用于 sourceHashSnapshot） */
export function computeHttpSourceHash(source: HttpSourceResponse): string {
  return stableHash(source as unknown as Record<string, unknown>, SOURCE_AUDIT_KEYS);
}

/** 从 HTTP Step 计算配置 hash（用于 configHash） */
export function computeHttpStepConfigHash(step: HttpStepDefinition): string {
  return stableHash(step as unknown as Record<string, unknown>, STEP_NON_CONFIG_KEYS);
}

/** 生成不重复的 stepId，基于 sourceCode 加序号 */
function uniqueStepId(baseCode: string, existingSteps: StepDefinition[]): string {
  const existingIds = new Set(existingSteps.map((s) => s.stepId));
  if (!existingIds.has(baseCode)) return baseCode;
  let suffix = 2;
  while (existingIds.has(`${baseCode}_${suffix}`)) suffix++;
  return `${baseCode}_${suffix}`;
}

/** 将 HTTP Source 模板导入为 HTTP Step */
export function httpSourceToStep(
  source: HttpSourceResponse,
  existingSteps: StepDefinition[],
): HttpStepDefinition {
  const stepId = uniqueStepId(source.sourceCode, existingSteps);
  const sourceHash = computeHttpSourceHash(source);
  const now = new Date().toISOString();

  const step: HttpStepDefinition = {
    stepId,
    stepName: source.sourceName,
    type: "HTTP",
    enabled: true,
    dependsOn: [],
    description: `从模板 ${source.sourceName} 导入`,
    executionOrder: existingSteps.length + 1,
    position: null,
    outputMapping: source.outputMapping ?? {},
    outputMeta: source.outputMeta ?? null,

    // 从模板复制的业务配置字段
    sourceName: source.sourceName,
    sysCode: source.sysCode,
    method: source.method,
    path: source.path,
    timeoutConfig: source.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
    requestMapping: source.requestMapping ?? {},
    httpParamMapping: {},
    bodySchema: source.bodySchema ?? null,
    responseSchema: source.responseSchema ?? null,
    responseHeadersSchema: source.responseHeadersSchema ?? null,
    responseCookiesSchema: source.responseCookiesSchema ?? null,
    responseHandling: source.responseHandling ?? null,
    errorMapping: source.errorMapping ?? null,
    businessErrorMapping: source.businessErrorMapping ?? null,
    retryPolicy: source.retryPolicy ?? null,

    // 模板引用快照
    templateRef: {
      type: "HTTP_SOURCE",
      sourceCode: source.sourceCode,
      sourceNameAtSnapshot: source.sourceName,
      sourceUpdatedAtSnapshot: source.updatedAt,
      sourceHashSnapshot: sourceHash,
      configHash: "", // 创建后再计算
      snapshotAt: now,
      drifted: false,
    },
  };

  // 计算并回填 configHash
  step.templateRef!.configHash = computeHttpStepConfigHash(step);

  return step;
}

// ── SQL Source → Step 映射 ───────────────────────────────────────────────

/** 从 SQL Source 计算业务配置 hash（用于 sourceHashSnapshot） */
export function computeSqlSourceHash(source: SqlSourceResponse): string {
  return stableHash(source as unknown as Record<string, unknown>, SOURCE_AUDIT_KEYS);
}

/** 从 SQL Step 计算配置 hash（用于 configHash） */
export function computeSqlStepConfigHash(step: SqlStepDefinition): string {
  return stableHash(step as unknown as Record<string, unknown>, STEP_NON_CONFIG_KEYS);
}

/** 将 SQL Source 模板导入为 SQL Step */
export function sqlSourceToStep(
  source: SqlSourceResponse,
  existingSteps: StepDefinition[],
): SqlStepDefinition {
  const stepId = uniqueStepId(source.sourceCode, existingSteps);
  const sourceHash = computeSqlSourceHash(source);
  const now = new Date().toISOString();

  const step: SqlStepDefinition = {
    stepId,
    stepName: source.sourceName,
    type: "SQL",
    enabled: true,
    dependsOn: [],
    description: `从模板 ${source.sourceName} 导入`,
    executionOrder: existingSteps.length + 1,
    position: null,
    outputMapping: {},
    outputMeta: null,

    // 从模板复制的业务配置字段
    sourceName: source.sourceName,
    sysCode: source.sysCode,
    datasourceCode: source.datasourceCode,
    operation: source.operation,
    sqlText: source.sqlText,
    normalizedSql: source.normalizedSql,
    tables: source.tables ?? [],
    resultFields: source.resultFields ?? [],
    conditionFields: source.conditionFields ?? [],
    parameters: source.parameters ?? [],
    safety: source.safety ?? { requireWhere: true, maxAffectedRows: null },
    paramMapping: {},

    // 模板引用快照
    templateRef: {
      type: "SQL_SOURCE",
      sourceCode: source.sourceCode,
      sourceNameAtSnapshot: source.sourceName,
      sourceUpdatedAtSnapshot: source.updatedAt,
      sourceHashSnapshot: sourceHash,
      configHash: "", // 创建后再计算
      snapshotAt: now,
      drifted: false,
    },
  };

  // 计算并回填 configHash
  step.templateRef!.configHash = computeSqlStepConfigHash(step);

  return step;
}

// ── 偏离检测 ──────────────────────────────────────────────────────────────

/** 检查步骤是否偏离了来源模板的最新版本 */
export function checkDrift(
  step: StepDefinition,
  currentSource: HttpSourceResponse | SqlSourceResponse | null,
): boolean {
  if (!step.templateRef || !currentSource) return false;

  const currentHash =
    step.type === "HTTP"
      ? computeHttpSourceHash(currentSource as HttpSourceResponse)
      : computeSqlSourceHash(currentSource as SqlSourceResponse);

  return currentHash !== step.templateRef.sourceHashSnapshot;
}

/** 根据当前模板源重新同步步骤配置（重新导入），保留步骤自身的 stepId/dependsOn/executionOrder */
export function resyncStepFromSource(
  step: StepDefinition,
  currentSource: HttpSourceResponse | SqlSourceResponse,
): StepDefinition {
  const now = new Date().toISOString();

  if (step.type === "HTTP" && currentSource) {
    const src = currentSource as HttpSourceResponse;
    const sourceHash = computeHttpSourceHash(src);
    const resynced: HttpStepDefinition = {
      ...(step),
      sourceName: src.sourceName,
      sysCode: src.sysCode,
      method: src.method,
      path: src.path,
      timeoutConfig: src.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
      requestMapping: src.requestMapping ?? {},
      bodySchema: src.bodySchema ?? null,
      responseSchema: src.responseSchema ?? null,
      responseHeadersSchema: src.responseHeadersSchema ?? null,
      responseCookiesSchema: src.responseCookiesSchema ?? null,
      responseHandling: src.responseHandling ?? null,
      errorMapping: src.errorMapping ?? null,
      businessErrorMapping: src.businessErrorMapping ?? null,
      retryPolicy: src.retryPolicy ?? null,
      outputMapping: src.outputMapping ?? {},
      outputMeta: src.outputMeta ?? null,
      templateRef: {
        type: "HTTP_SOURCE",
        sourceCode: src.sourceCode,
        sourceNameAtSnapshot: src.sourceName,
        sourceUpdatedAtSnapshot: src.updatedAt,
        sourceHashSnapshot: sourceHash,
        configHash: "",
        snapshotAt: now,
        drifted: false,
      },
    };
    resynced.templateRef!.configHash = computeHttpStepConfigHash(resynced);
    return resynced;
  }

  if (step.type === "SQL" && currentSource) {
    const src = currentSource as SqlSourceResponse;
    const sourceHash = computeSqlSourceHash(src);
    const resynced: SqlStepDefinition = {
      ...(step),
      sourceName: src.sourceName,
      sysCode: src.sysCode,
      datasourceCode: src.datasourceCode,
      operation: src.operation,
      sqlText: src.sqlText,
      normalizedSql: src.normalizedSql,
      tables: src.tables ?? [],
      resultFields: src.resultFields ?? [],
      conditionFields: src.conditionFields ?? [],
      parameters: src.parameters ?? [],
      safety: src.safety ?? { requireWhere: true, maxAffectedRows: null },
      templateRef: {
        type: "SQL_SOURCE",
        sourceCode: src.sourceCode,
        sourceNameAtSnapshot: src.sourceName,
        sourceUpdatedAtSnapshot: src.updatedAt,
        sourceHashSnapshot: sourceHash,
        configHash: "",
        snapshotAt: now,
        drifted: false,
      },
    };
    resynced.templateRef!.configHash = computeSqlStepConfigHash(resynced);
    return resynced;
  }

  return step;
}

/** 断开步骤与模板的关联，保留当前配置不变 */
export function detachTemplateRef(step: StepDefinition): StepDefinition {
  return { ...step, templateRef: null };
}
