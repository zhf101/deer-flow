import type {
  InputFieldDefinition,
  SceneDefinition,
} from "./types";

export interface VariableItem {
  label: string;
  value: string;
  group: string;
}

/**
 * Build the full list of selectable variables from scene context.
 * Shared between VariableSelector and label resolution.
 */
export function buildVariableList(
  scene: SceneDefinition,
  currentStepId?: string | null,
  includeAllSteps?: boolean,
): VariableItem[] {
  const list: VariableItem[] = [];

  // Input parameters
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

  // Dependent step outputs
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
      });
    });
  });

  // System variables
  list.push({ label: "当前时间 (now)", value: "${system.now}", group: "系统变量" });
  list.push({ label: "时间戳 (timestamp)", value: "${system.timestamp}", group: "系统变量" });
  list.push({ label: "UUID", value: "${system.uuid}", group: "系统变量" });

  return list;
}

const VARIABLE_PATTERN = /^\$\{(.+)\}$/;

/**
 * Resolve a raw variable string (e.g. "${input.userId}") into a
 * human-readable label (e.g. "输入参数-用户ID").
 *
 * Returns the original string unchanged if it is not a variable reference
 * or cannot be resolved.
 */
export function resolveVariableLabel(
  raw: string,
  scene: SceneDefinition,
  currentStepId?: string | null,
): string {
  if (!raw) return raw;

  const match = VARIABLE_PATTERN.exec(raw.trim());
  if (!match) return raw; // not a variable reference

  const variables = buildVariableList(scene, currentStepId);
  const found = variables.find((v) => v.value === raw.trim());
  if (found) {
    return `${found.group}-${found.label}`;
  }

  // Fallback: try to parse the inner path for a reasonable display
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

/** Check if a string is a variable reference (${...}) */
export function isVariableRef(value: string): boolean {
  return VARIABLE_PATTERN.test(value.trim());
}
