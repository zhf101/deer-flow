import type {
  HttpStepDefinition,
  HttpTimeoutConfig,
  SqlStepDefinition,
  StepDefinition,
} from "./types";

export function patchHttpStep(
  step: HttpStepDefinition,
  updates: Partial<Omit<HttpStepDefinition, "type">>,
): HttpStepDefinition {
  return { ...step, ...updates, type: "HTTP" };
}

export function patchSqlStep(
  step: SqlStepDefinition,
  updates: Partial<Omit<SqlStepDefinition, "type">>,
): SqlStepDefinition {
  return { ...step, ...updates, type: "SQL" };
}

export function patchHttpTimeoutConfig(
  step: HttpStepDefinition,
  updates: Partial<HttpTimeoutConfig>,
): HttpStepDefinition {
  return {
    ...step,
    timeoutConfig: {
      ...step.timeoutConfig,
      ...updates,
    },
  };
}

export function patchSqlParamMapping(
  step: SqlStepDefinition,
  key: string,
  value: unknown,
): SqlStepDefinition {
  return {
    ...step,
    paramMapping: {
      ...step.paramMapping,
      [key]: value,
    },
  };
}

export function replaceStepInList(
  steps: StepDefinition[],
  nextStep: StepDefinition,
): StepDefinition[] {
  return steps.map((step) => (step.stepId === nextStep.stepId ? nextStep : step));
}
