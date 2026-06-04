import type { SceneDefinition, ValidationIssue } from "./types";

const CODE_RE = /^[A-Za-z][A-Za-z0-9_:-]{1,127}$/;
const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function validateSceneDraft(scene: SceneDefinition): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!CODE_RE.test(scene.sceneCode)) {
    issues.push({
      field: "sceneCode",
      message: "场景编码需以字母开头，可包含字母、数字、_、:、-",
      level: "ERROR",
    });
  }
  if (!scene.sceneName.trim()) {
    issues.push({
      field: "sceneName",
      message: "场景名称不能为空",
      level: "ERROR",
    });
  }
  const inputNames = new Set<string>();
  for (const [index, field] of scene.inputSchema.entries()) {
    if (!IDENTIFIER_RE.test(field.name)) {
      issues.push({
        field: `inputSchema[${index}].name`,
        message: "入参字段名需为合法标识符",
        level: "ERROR",
      });
    }
    if (inputNames.has(field.name)) {
      issues.push({
        field: `inputSchema[${index}].name`,
        message: `重复入参字段：${field.name}`,
        level: "ERROR",
      });
    }
    inputNames.add(field.name);
  }
  const stepIds = new Set<string>();
  for (const [index, step] of scene.steps.entries()) {
    if (!IDENTIFIER_RE.test(step.stepId)) {
      issues.push({
        field: `steps[${index}].stepId`,
        message: "步骤 ID 需为合法标识符",
        level: "ERROR",
      });
    }
    if (stepIds.has(step.stepId)) {
      issues.push({
        field: `steps[${index}].stepId`,
        message: `重复步骤 ID：${step.stepId}`,
        level: "ERROR",
      });
    }
    stepIds.add(step.stepId);
  }
  if (!scene.inputSchema.some((field) => field.name === "env" && field.required)) {
    issues.push({
      field: "inputSchema.env",
      message: "env 入参必须存在且必填",
      level: "WARNING",
    });
  }
  return issues;
}

export function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

export function parseJsonObject(text: string): Record<string, unknown> {
  if (!text.trim()) return {};
  const parsed = JSON.parse(text) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("JSON 必须是对象");
  }
  return parsed as Record<string, unknown>;
}

export function parseStringMap(text: string): Record<string, string> {
  const parsed = parseJsonObject(text);
  return Object.fromEntries(
    Object.entries(parsed).map(([key, value]) => [
      key,
      stringifyConfigValue(value),
    ]),
  );
}

export function stringifyConfigValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return value.toString();
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}
