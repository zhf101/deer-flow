import type {
  AssertStepDefinition,
  HttpStepDefinition,
  SceneDefinition,
  SqlStepDefinition,
  StepDefinition,
  TransformStepDefinition,
} from "./types";

function basePayload(step: StepDefinition) {
  return {
    stepId: step.stepId,
    stepName: step.stepName ?? null,
    type: step.type,
    enabled: step.enabled,
    dependsOn: step.dependsOn,
    description: step.description ?? null,
    position: step.position ?? null,
    templateRef: step.templateRef ?? null,
    outputMapping: step.outputMapping ?? {},
    outputMeta: step.outputMeta ?? null,
  };
}

export function toStrictStepPayload(step: StepDefinition): StepDefinition {
  const base = basePayload(step);

  if (step.type === "HTTP") {
    return {
      ...base,
      type: "HTTP",
      sourceName: step.sourceName ?? null,
      sysCode: step.sysCode || null,
      method: step.method,
      path: step.path || null,
      timeoutConfig: step.timeoutConfig,
      requestMapping: step.requestMapping,
      httpParamMapping: step.httpParamMapping,
      bodySchema: step.bodySchema ?? null,
      responseSchema: step.responseSchema ?? null,
      responseHeadersSchema: step.responseHeadersSchema ?? null,
      responseCookiesSchema: step.responseCookiesSchema ?? null,
      responseHandling: step.responseHandling ?? null,
      errorMapping: step.errorMapping ?? null,
      businessErrorMapping: step.businessErrorMapping ?? null,
      retryPolicy: step.retryPolicy ?? null,
    } satisfies HttpStepDefinition;
  }

  if (step.type === "SQL") {
    return {
      ...base,
      type: "SQL",
      sourceName: step.sourceName ?? null,
      sysCode: step.sysCode || null,
      datasourceCode: step.datasourceCode || null,
      operation: step.operation ?? null,
      sqlText: step.sqlText || null,
      normalizedSql: step.normalizedSql ?? null,
      tables: step.tables ?? [],
      resultFields: step.resultFields ?? [],
      conditionFields: step.conditionFields ?? [],
      parameters: step.parameters ?? [],
      safety: step.safety,
      paramMapping: step.paramMapping,
    } satisfies SqlStepDefinition;
  }

  if (step.type === "ASSERT") {
    return {
      ...base,
      type: "ASSERT",
      assertions: step.assertions,
    } satisfies AssertStepDefinition;
  }

  return {
    ...base,
    type: "TRANSFORM",
    assignments: step.assignments,
  } satisfies TransformStepDefinition;
}

export function toStrictScenePayload(scene: SceneDefinition): SceneDefinition {
  return {
    ...scene,
    steps: scene.steps.map(toStrictStepPayload),
  };
}
