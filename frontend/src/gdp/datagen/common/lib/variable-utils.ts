import type {
  InputFieldDefinition,
  SceneDefinition,
} from "./types";

export interface VariableItem {
  label: string;
  value: string;
  group: string;
  sourceStepId?: string;
  outputName?: string;
}

/** 根据场景上下文构建完整的可选变量列表，供 VariableSelector 和标签解析共享。 */
export function buildVariableList(
  scene: SceneDefinition,
  currentStepId?: string | null,
  includeAllSteps?: boolean,
): VariableItem[] {
  const list: VariableItem[] = [];

  // 输入参数
  const addInput = (field: InputFieldDefinition, path = "input") => {
    const fullPath = `${path}.${field.name}`;
    list.push({
      label: field.label ?? field.name,
      value: `\${${fullPath}}`,
      group: "输入参数",
    });
    if (field.children) {
      field.children.forEach((child) => addInput(child, fullPath));
    }
  };
  scene.inputSchema.forEach((field) => addInput(field));

  // 依赖步骤输出
  const currentStep = scene.steps.find((s) => s.stepId === currentStepId);
  const dependentStepIds = currentStep?.dependsOn ?? [];
  const dependentSteps = includeAllSteps
    ? scene.steps
    : scene.steps.filter((s) => dependentStepIds.includes(s.stepId));

  dependentSteps.forEach((step) => {
    const meta = step.outputMeta ?? {};
    Object.keys(step.outputMapping ?? {}).forEach((outKey) => {
      const fieldLabel = meta[outKey]?.label ?? meta[outKey]?.remark ?? outKey;
      list.push({
        label: `${step.stepName ?? step.stepId} -> ${fieldLabel}`,
        value: `\${steps.${step.stepId}.outputs.${outKey}}`,
        group: "步骤输出",
        sourceStepId: step.stepId,
        outputName: outKey,
      });
    });
  });

  // 系统变量
  list.push({ label: "当前时间 (now)", value: "${system.now}", group: "系统变量" });
  list.push({ label: "时间戳 (timestamp)", value: "${system.timestamp}", group: "系统变量" });
  list.push({ label: "UUID", value: "${system.uuid}", group: "系统变量" });

  return list;
}

const VARIABLE_PATTERN = /^\$\{(.+)\}$/;

/** 将原始变量字符串（如 "${input.userId}"）解析为可读标签（如 "输入参数-用户ID"）。如果不是变量引用或无法解析，则返回原字符串。 */
export function resolveVariableLabel(
  raw: string,
  scene: SceneDefinition,
  currentStepId?: string | null,
): string {
  if (!raw) return raw;

  const match = VARIABLE_PATTERN.exec(raw.trim());
  if (!match) return raw; // 不是变量引用

  const variables = buildVariableList(scene, currentStepId);
  const found = variables.find((v) => v.value === raw.trim());
  if (found) {
    return `${found.group}-${found.label}`;
  }

  // 兜底处理：尝试解析内部路径以生成可读展示文本
  const inner = match[1];
  if (!inner) return raw;

  // ${input.xxx}
  if (inner.startsWith("input.")) {
    const fieldName = inner.slice("input.".length);
    const field = findFieldByName(scene.inputSchema, fieldName);
    const displayName = field?.label ?? fieldName;
    return `输入参数-${displayName}`;
  }

  // ${steps.xxx.outputs.yyy}
  const stepMatch = /^steps\.(\w+)\.outputs\.(.+)$/.exec(inner);
  if (stepMatch?.[1] && stepMatch[2]) {
    const stepId = stepMatch[1];
    const outKey = stepMatch[2];
    const step = scene.steps.find((s) => s.stepId === stepId);
    const stepLabel = step?.stepName ?? stepId;
    const meta = step?.outputMeta?.[outKey];
    const fieldLabel = meta?.label ?? meta?.remark ?? outKey;
    return `${stepLabel}-${fieldLabel}`;
  }

  // ${system.xxx}
  if (inner.startsWith("system.")) {
    return `系统变量-${inner.slice("system.".length)}`;
  }

  return raw;
}

function findFieldByName(
  fields: InputFieldDefinition[],
  name: string,
): InputFieldDefinition | undefined {
  for (const field of fields) {
    if (field.name === name) return field;
    if (field.children) {
      const found = findFieldByName(field.children, name);
      if (found) return found;
    }
  }
  return undefined;
}

/** 判断字符串是否为变量引用（${...}） */
export function isVariableRef(value: string): boolean {
  return VARIABLE_PATTERN.test(value.trim());
}
