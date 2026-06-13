/**
 * ============================================================================
 * 步骤级校验和配置完成度计算
 * ============================================================================
 *
 * 独立的步骤校验逻辑，镜像后端 validate_scene_publish 的规则。
 * 供编辑器和步骤列表复用。
 */

import type {
  ConditionOperator,
  ConditionRule,
  InputFieldDefinition,
  SceneDefinition,
  StepDefinition,
  ValidationIssue,
} from "./types";
import { isAssertStep, isHttpStep, isSqlStep, isTransformStep } from "./types";

// ── 变量引用提取 ────────────────────────────────────────────────────────

const STEP_OUTPUT_REF_RE =
  /\$\{steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)(?:[.\[].*?)?\}/g;
const VALUELESS_OPERATORS = new Set<ConditionOperator>([
  "EXISTS",
  "NOT_EXISTS",
  "EMPTY",
  "NOT_EMPTY",
]);

function extractStepOutputRefs(value: unknown): [string, string][] {
  const refs: [string, string][] = [];
  if (typeof value === "string") {
    let match: RegExpExecArray | null;
    const re = new RegExp(STEP_OUTPUT_REF_RE.source, "g");
    while ((match = re.exec(value)) !== null) {
      refs.push([match[1]!, match[2]!]);
    }
  } else if (Array.isArray(value)) {
    for (const item of value) {
      refs.push(...extractStepOutputRefs(item));
    }
  } else if (value && typeof value === "object") {
    for (const v of Object.values(value as Record<string, unknown>)) {
      refs.push(...extractStepOutputRefs(v));
    }
  }
  return refs;
}

// ── 依赖闭包 ────────────────────────────────────────────────────────────

function dependencyClosure(
  step: StepDefinition,
  stepsById: Map<string, StepDefinition>,
): Set<string> {
  const allowed = new Set<string>();
  const stack = [...step.dependsOn];
  while (stack.length) {
    const dep = stack.pop()!;
    if (allowed.has(dep)) continue;
    allowed.add(dep);
    const depStep = stepsById.get(dep);
    if (depStep) stack.push(...depStep.dependsOn);
  }
  return allowed;
}

// ── 单步骤校验 ──────────────────────────────────────────────────────────

export function validateStepForPublish(
  step: StepDefinition,
  scene: SceneDefinition,
): ValidationIssue[] {
  if (!step.enabled) return [];

  const issues: ValidationIssue[] = [];
  const field = `step:${step.stepId}`;
  const stepsById = new Map(scene.steps.map((s) => [s.stepId, s]));

  // HTTP 步骤校验
  if (isHttpStep(step)) {
    if (!step.sysCode) {
      issues.push({
        field: `${field}.sysCode`,
        message: "HTTP 步骤必须配置系统编码。",
        level: "ERROR",
      });
    }
    if (!step.method) {
      issues.push({
        field: `${field}.method`,
        message: "HTTP 步骤必须配置请求方法。",
        level: "ERROR",
      });
    }
    if (!step.path) {
      issues.push({
        field: `${field}.path`,
        message: "HTTP 步骤必须配置请求路径。",
        level: "ERROR",
      });
    }
  }

  // SQL 步骤校验
  if (isSqlStep(step)) {
    if (!step.sysCode) {
      issues.push({
        field: `${field}.sysCode`,
        message: "SQL 步骤必须配置系统编码。",
        level: "ERROR",
      });
    }
    if (!step.datasourceCode) {
      issues.push({
        field: `${field}.datasourceCode`,
        message: "SQL 步骤必须配置数据源编码。",
        level: "ERROR",
      });
    }
    if (!step.operation) {
      issues.push({
        field: `${field}.operation`,
        message: "SQL 步骤必须配置操作类型。",
        level: "ERROR",
      });
    }
    if (!step.sqlText) {
      issues.push({
        field: `${field}.sqlText`,
        message: "SQL 步骤必须配置 SQL 文本。",
        level: "ERROR",
      });
    }
    if (!step.normalizedSql) {
      issues.push({
        field: `${field}.normalizedSql`,
        message: "SQL 步骤发布前必须先解析生成标准 SQL。",
        level: "ERROR",
      });
    }

    // SQL 安全检查：UPDATE/DELETE + requireWhere 必须有顶层 WHERE
    if (
      step.normalizedSql &&
      (step.operation === "UPDATE" || step.operation === "DELETE") &&
      step.safety?.requireWhere !== false
    ) {
      if (!hasTopLevelWhere(step.normalizedSql)) {
        issues.push({
          field: `${field}.normalizedSql`,
          message:
            "UPDATE/DELETE 步骤启用 requireWhere 时必须包含 WHERE 条件。",
          level: "ERROR",
        });
      }
    }

    // 必填参数映射检查
    if (step.normalizedSql && step.parameters) {
      const mapping = step.paramMapping || {};
      for (const param of step.parameters) {
        if (!param.required) continue;
        if (!param.name) continue;
        const hasDefault = param.defaultValue != null;
        if (!(param.name in mapping) && !hasDefault) {
          issues.push({
            field: `${field}.paramMapping.${param.name}`,
            message: `SQL 必填参数未映射：${param.name}。`,
            level: "ERROR",
          });
        }
      }
    }
  }

  if (isAssertStep(step)) {
    if (step.assertions.length === 0) {
      issues.push({
        field: `${field}.assertions`,
        message: "断言步骤必须至少配置一条断言。",
        level: "ERROR",
      });
    }
    step.assertions.forEach((assertion, index) => {
      if (!assertion.expression.trim()) {
        issues.push({
          field: `${field}.assertions[${index}].expression`,
          message: "断言表达式不能为空。",
          level: "ERROR",
        });
      }
    });
  }

  if (isTransformStep(step) && Object.keys(step.assignments).length === 0) {
    issues.push({
      field: `${field}.assignments`,
      message: "转换步骤必须至少配置一个变量赋值。",
      level: "ERROR",
    });
  }

  // 变量引用校验
  const allowed = dependencyClosure(step, stepsById);
  const allValues: unknown[] = [step.outputMapping];
  if (isHttpStep(step)) {
    allValues.push(step.requestMapping, step.httpParamMapping);
  } else if (isSqlStep(step)) {
    allValues.push(step.paramMapping);
  } else if (isAssertStep(step)) {
    allValues.push(step.assertions);
  } else if (isTransformStep(step)) {
    allValues.push(step.assignments);
  }

  for (const [refStepId, outputName] of allValues.flatMap(
    extractStepOutputRefs,
  )) {
    const refStep = stepsById.get(refStepId);
    if (!refStep) {
      issues.push({
        field,
        message: `变量引用的步骤不存在：${refStepId}。`,
        level: "ERROR",
      });
      continue;
    }
    if (!allowed.has(refStepId)) {
      issues.push({
        field,
        message: `变量引用必须来自当前步骤依赖链：${refStepId}。`,
        level: "ERROR",
      });
    }
    if (!refStep.enabled) {
      issues.push({
        field,
        message: `变量不能引用禁用步骤的输出：${refStepId}。`,
        level: "ERROR",
      });
      continue;
    }
    if (!(outputName in refStep.outputMapping)) {
      issues.push({
        field,
        message: `变量引用的步骤输出不存在：${refStepId}.${outputName}。`,
        level: "ERROR",
      });
    }
  }

  return issues;
}

function hasTopLevelWhere(sqlText: string): boolean {
  let depth = 0;
  let quote: string | null = null;

  for (let index = 0; index < sqlText.length; index += 1) {
    const char = sqlText[index]!;
    if (quote) {
      if (char === quote) {
        if (sqlText[index + 1] === quote) {
          index += 1;
        } else {
          quote = null;
        }
      } else if (char === "\\" && (quote === "'" || quote === '"')) {
        index += 1;
      }
      continue;
    }

    if (char === "'" || char === '"' || char === "`") {
      quote = char;
      continue;
    }
    if (sqlText.slice(index, index + 2) === "--") {
      const newlineIndex = sqlText.indexOf("\n", index + 2);
      index = newlineIndex === -1 ? sqlText.length : newlineIndex;
      continue;
    }
    if (sqlText.slice(index, index + 2) === "/*") {
      const commentEnd = sqlText.indexOf("*/", index + 2);
      index = commentEnd === -1 ? sqlText.length : commentEnd + 1;
      continue;
    }
    if (char === "(") {
      depth += 1;
      continue;
    }
    if (char === ")") {
      depth = Math.max(depth - 1, 0);
      continue;
    }
    if (
      depth === 0 &&
      sqlText.slice(index, index + 5).toLowerCase() === "where" &&
      isWordBoundary(sqlText, index - 1) &&
      isWordBoundary(sqlText, index + 5)
    ) {
      return true;
    }
  }

  return false;
}

function isWordBoundary(sqlText: string, index: number): boolean {
  if (index < 0 || index >= sqlText.length) return true;
  return !/[A-Za-z0-9_]/.test(sqlText[index]!);
}

// ── 步骤配置完成度 ──────────────────────────────────────────────────────

export interface StepConfigStatus {
  complete: boolean;
  errorCount: number;
  warningCount: number;
  outputCount: number;
  usedVariableCount: number;
}

export function computeStepConfigStatus(
  step: StepDefinition,
  scene: SceneDefinition,
): StepConfigStatus {
  const issues = validateStepForPublish(step, scene);
  const errorCount = issues.filter((i) => i.level === "ERROR").length;
  const warningCount = issues.filter((i) => i.level === "WARNING").length;
  const outputCount = Object.keys(step.outputMapping ?? {}).length;

  // 统计此步骤引用的变量数
  const allValues: unknown[] = [
    isHttpStep(step) ? step.requestMapping : null,
    isHttpStep(step) ? step.httpParamMapping : null,
    isSqlStep(step) ? step.paramMapping : null,
    isTransformStep(step) ? step.assignments : null,
  ];
  const usedVars = new Set<string>();
  for (const [refStepId, outputName] of allValues.flatMap(
    extractStepOutputRefs,
  )) {
    usedVars.add(`${refStepId}.${outputName}`);
  }

  return {
    complete: errorCount === 0,
    errorCount,
    warningCount,
    outputCount,
    usedVariableCount: usedVars.size,
  };
}

// ── 场景级发布校验（增强版）─────────────────────────────────────────────

export function validateSceneForPublish(
  scene: SceneDefinition,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // 基础草稿校验
  if (!scene.sceneCode?.trim()) {
    issues.push({
      field: "sceneCode",
      message: "场景编码不能为空。",
      level: "ERROR",
    });
  }
  if (!scene.sceneName?.trim()) {
    issues.push({
      field: "sceneName",
      message: "场景名称不能为空。",
      level: "ERROR",
    });
  }

  // 步骤 ID 唯一性
  const stepIds = new Set<string>();
  for (const [index, step] of scene.steps.entries()) {
    if (!step.stepId) {
      issues.push({
        field: `steps[${index}].stepId`,
        message: "步骤 ID 不能为空。",
        level: "ERROR",
      });
      continue;
    }
    if (stepIds.has(step.stepId)) {
      issues.push({
        field: `steps[${index}].stepId`,
        message: `步骤 ID 重复：${step.stepId}。`,
        level: "ERROR",
      });
    }
    stepIds.add(step.stepId);
  }

  // 依赖关系校验
  const graph = new Map<string, string[]>();
  const indegree = new Map<string, number>();
  for (const step of scene.steps) {
    graph.set(step.stepId, []);
    indegree.set(step.stepId, 0);
  }
  for (const [index, step] of scene.steps.entries()) {
    for (const dep of step.dependsOn) {
      if (dep === step.stepId) {
        issues.push({
          field: `steps[${index}].dependsOn`,
          message: `步骤不能依赖自身：${step.stepId}。`,
          level: "ERROR",
        });
        continue;
      }
      if (!stepIds.has(dep)) {
        issues.push({
          field: `steps[${index}].dependsOn`,
          message: `依赖步骤不存在：${dep}。`,
          level: "ERROR",
        });
        continue;
      }
      graph.get(dep)!.push(step.stepId);
      indegree.set(step.stepId, (indegree.get(step.stepId) ?? 0) + 1);
    }
  }
  // 环检测
  const queue = [...indegree.entries()]
    .filter(([, d]) => d === 0)
    .map(([id]) => id);
  let visited = 0;
  while (queue.length) {
    const current = queue.shift()!;
    visited++;
    for (const next of graph.get(current) ?? []) {
      const d = (indegree.get(next) ?? 1) - 1;
      indegree.set(next, d);
      if (d === 0) queue.push(next);
    }
  }
  if (visited !== stepIds.size) {
    issues.push({
      field: "steps",
      message: "步骤依赖存在环。",
      level: "ERROR",
    });
  }

  // 逐步骤校验
  for (const step of scene.steps) {
    issues.push(...validateStepForPublish(step, scene));
  }

  // 结果映射校验
  const stepsById = new Map(scene.steps.map((s) => [s.stepId, s]));
  for (const [refStepId, outputName] of extractStepOutputRefs(
    scene.resultMapping,
  )) {
    const refStep = stepsById.get(refStepId);
    if (!refStep) {
      issues.push({
        field: "resultMapping",
        message: `变量引用的步骤不存在：${refStepId}。`,
        level: "ERROR",
      });
      continue;
    }
    if (!refStep.enabled) {
      issues.push({
        field: "resultMapping",
        message: `变量不能引用禁用步骤的输出：${refStepId}。`,
        level: "ERROR",
      });
      continue;
    }
    if (!(outputName in refStep.outputMapping)) {
      issues.push({
        field: "resultMapping",
        message: `变量引用的步骤输出不存在：${refStepId}.${outputName}。`,
        level: "ERROR",
      });
    }
  }

  validateSceneSuccessCriteria(scene, stepsById, issues);

  addSemanticQualityWarnings(scene, issues);

  return issues;
}

function validateSceneSuccessCriteria(
  scene: SceneDefinition,
  stepsById: Map<string, StepDefinition>,
  issues: ValidationIssue[],
): void {
  const criteria = scene.successCriteria;
  if (!criteria?.enabled) return;

  const successRules = criteria.businessSuccess?.allOf ?? [];
  const failureRules = criteria.businessFailure?.anyOf ?? [];
  if (successRules.length === 0 && failureRules.length === 0) {
    issues.push({
      field: "successCriteria",
      message: "启用场景业务判定后，必须至少配置一条成功或失败规则。",
      level: "ERROR",
    });
  }

  validateConditionRuleGroup(
    "successCriteria.businessFailure.anyOf",
    failureRules,
    issues,
  );
  validateConditionRuleGroup(
    "successCriteria.businessSuccess.allOf",
    successRules,
    issues,
  );

  for (const [refStepId, outputName] of extractStepOutputRefs(criteria)) {
    const refStep = stepsById.get(refStepId);
    if (!refStep) {
      issues.push({
        field: "successCriteria",
        message: `业务判定引用的步骤不存在：${refStepId}。`,
        level: "ERROR",
      });
      continue;
    }
    if (!refStep.enabled) {
      issues.push({
        field: "successCriteria",
        message: `业务判定不能引用禁用步骤的输出：${refStepId}。`,
        level: "ERROR",
      });
      continue;
    }
    if (!(outputName in refStep.outputMapping)) {
      issues.push({
        field: "successCriteria",
        message: `业务判定引用的步骤输出不存在：${refStepId}.${outputName}。`,
        level: "ERROR",
      });
    }
  }
}

function validateConditionRuleGroup(
  field: string,
  rules: ConditionRule[],
  issues: ValidationIssue[],
): void {
  rules.forEach((rule, index) => {
    const ruleField = `${field}[${index}]`;
    const rulePath = typeof rule.path === "string" ? rule.path : "";
    if (!rulePath.trim()) {
      issues.push({
        field: `${ruleField}.path`,
        message: "业务判定规则字段路径不能为空。",
        level: "ERROR",
      });
    }
    if (!rule.op) {
      issues.push({
        field: `${ruleField}.op`,
        message: "业务判定规则操作符不能为空。",
        level: "ERROR",
      });
    }
    if (
      !VALUELESS_OPERATORS.has(rule.op) &&
      (rule.value === undefined ||
        rule.value === null ||
        (typeof rule.value === "string" && !rule.value.trim()))
    ) {
      issues.push({
        field: `${ruleField}.value`,
        message: "业务判定规则目标值不能为空。",
        level: "ERROR",
      });
    }
  });
}

function addSemanticQualityWarnings(
  scene: SceneDefinition,
  issues: ValidationIssue[],
): void {
  const remark = scene.sceneRemark?.trim() ?? "";
  if (!remark) {
    issues.push({
      field: "sceneRemark",
      message: "建议填写场景备注，说明场景能做什么、产出什么以及适用范围。",
      level: "WARNING",
    });
  } else if (remark.length < 20) {
    issues.push({
      field: "sceneRemark",
      message: "场景备注过短，建议说明场景用途、主要产出和执行副作用。",
      level: "WARNING",
    });
  }

  addSchemaSemanticWarnings(scene.inputSchema, "inputSchema", issues, {
    skipNames: new Set([scene.environmentField]),
  });
  addSchemaSemanticWarnings(scene.resultSchema ?? [], "resultSchema", issues, {
    resultMapping: scene.resultMapping ?? {},
  });

  scene.steps.forEach((step, index) => {
    if (!step.enabled) return;
    const outputMeta = step.outputMeta ?? {};
    Object.keys(step.outputMapping ?? {}).forEach((outputName) => {
      const meta = outputMeta[outputName] ?? {};
      if (!meta.label?.trim()) {
        issues.push({
          field: `steps[${index}].outputMeta.${outputName}.label`,
          message: `建议为步骤输出 ${step.stepId}.${outputName} 填写中文名，方便后续场景接龙。`,
          level: "WARNING",
        });
      }
      if (!meta.remark?.trim()) {
        issues.push({
          field: `steps[${index}].outputMeta.${outputName}.remark`,
          message: `建议为步骤输出 ${step.stepId}.${outputName} 填写备注，说明输出业务含义。`,
          level: "WARNING",
        });
      }
    });
  });
}

function addSchemaSemanticWarnings(
  fields: InputFieldDefinition[],
  prefix: string,
  issues: ValidationIssue[],
  options: {
    skipNames?: Set<string>;
    resultMapping?: Record<string, string>;
    pathPrefix?: string;
  } = {},
): void {
  const pathPrefix = options.pathPrefix ?? "$";
  fields.forEach((field, index) => {
    if (options.skipNames?.has(field.name)) return;
    const fieldPrefix = `${prefix}[${index}]`;
    const isContainer = field.type === "object" || field.type === "array";
    const currentPath =
      field.type === "array"
        ? `${pathPrefix}.${field.name}[*]`
        : `${pathPrefix}.${field.name}`;

    if (!isContainer) {
      if (!field.label?.trim()) {
        issues.push({
          field: `${fieldPrefix}.label`,
          message: `建议为字段 ${field.name} 填写中文名，方便 AI 理解字段含义。`,
          level: "WARNING",
        });
      }
      if (!field.remark?.trim()) {
        issues.push({
          field: `${fieldPrefix}.remark`,
          message: `建议为字段 ${field.name} 填写备注，说明业务含义、来源或填写约束。`,
          level: "WARNING",
        });
      }
      if (options.resultMapping && !(currentPath in options.resultMapping)) {
        issues.push({
          field: `${fieldPrefix}.mapping`,
          message: `结果字段 ${currentPath} 尚未配置输出映射，AI 会误判该场景产出。`,
          level: "WARNING",
        });
      }
    }

    if (field.children?.length) {
      addSchemaSemanticWarnings(
        field.children,
        `${fieldPrefix}.children`,
        issues,
        {
          resultMapping: options.resultMapping,
          pathPrefix: currentPath,
        },
      );
    }
  });
}
