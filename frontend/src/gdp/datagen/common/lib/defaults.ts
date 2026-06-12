import type {
  BatchConfig,
  ConditionRule,
  HttpSourceConfig,
  HttpTimeoutConfig,
  InputFieldDefinition,
  SceneDefinition,
  SceneSuccessCriteria,
  SqlSourceConfig,
  StepDefinition,
  StepType,
  TaskDefinition,
} from "./types";

export const INPUT_FIELD_TYPES = [
  "string",
  "number",
  "boolean",
  "date",
  "enum",
  "object",
  "array",
] as const;

export const STEP_TYPES: StepType[] = ["HTTP", "SQL"];

export const HTTP_METHODS = ["GET", "POST"] as const;
export const SQL_OPERATIONS = ["SELECT", "INSERT", "UPDATE", "DELETE"] as const;
export const CONDITION_OPERATORS = [
  "EQ",
  "NE",
  "GT",
  "GTE",
  "LT",
  "LTE",
  "IN",
  "NOT_IN",
  "EXISTS",
  "NOT_EXISTS",
  "EMPTY",
  "NOT_EMPTY",
  "CONTAINS",
  "REGEX",
] as const;

export function createDefaultHttpTimeoutConfig(): HttpTimeoutConfig {
  return {
    connectTimeoutSeconds: 10,
    readTimeoutSeconds: 10,
    writeTimeoutSeconds: 10,
    poolTimeoutSeconds: 10,
  };
}

export function createEnvField(): InputFieldDefinition {
  return {
    name: "env",
    label: "环境",
    type: "string",
    required: true,
    defaultValue: null,
    optionsSource: null,
    validation: { minLength: 1, maxLength: 64, pattern: null },
    batchEnabled: false,
  };
}

export function createDefaultBatchConfig(): BatchConfig {
  return {
    enabled: false,
    failurePolicy: "STOP_ON_ERROR",
    maxConcurrency: 1,
  };
}

export function createDefaultScene(): SceneDefinition {
  return {
    sceneCode: "",
    sceneName: "",
    sceneRemark: "",
    sceneType: "",
    environmentField: "env",
    inputSchema: [createEnvField()],
    steps: [],
    resultSchema: [],
    resultMapping: {},
    successCriteria: null,
    errorPolicy: "STOP_ON_ERROR",
    batchConfig: createDefaultBatchConfig(),
    status: "DRAFT",
  };
}

export function createConditionRule(): ConditionRule {
  return {
    path: "${RES_BODY(success)}",
    op: "EQ",
    value: true,
  };
}

export function createDefaultSceneSuccessCriteria(
  firstOutputPath = "",
): SceneSuccessCriteria {
  return {
    enabled: true,
    businessSuccess: {
      allOf: firstOutputPath
        ? [{ path: firstOutputPath, op: "NOT_EMPTY" }]
        : [],
      anyOf: [],
    },
    businessFailure: {
      allOf: [],
      anyOf: [],
    },
  };
}

export function createDefaultStep(
  type: StepType,
  index: number,
): StepDefinition {
  const stepId = `${type.toLowerCase().replace("_", "")}${index + 1}`;
  const base = {
    stepId,
    stepName: stepLabel(type),
    executionOrder: index + 1,
    enabled: true,
    dependsOn: [],
    description: "",
    outputMapping: {},
    outputMeta: null,
  };

  if (type === "HTTP") {
    return {
      ...base,
      type: "HTTP",
      method: "POST",
      path: "",
      sysCode: "",
      timeoutConfig: createDefaultHttpTimeoutConfig(),
      requestMapping: { headers: {}, query: {}, body: {} },
      httpParamMapping: {},
      responseHandling: {
        expectedContentType: "JSON",
        statusCode: { success: [200] },
        businessSuccess: { allOf: [createConditionRule()] },
        businessFailure: { anyOf: [] },
      },
      errorMapping: {
        messageTemplate: "",
        fields: {},
        fallbackMessage: "",
        exposeRawResponse: false,
      },
      businessErrorMapping: {
        messageTemplate: "",
        fields: {},
        fallbackMessage: "",
        exposeRawResponse: false,
      },
      retryPolicy: {
        enabled: false,
        maxAttempts: 1,
        intervalMs: 1000,
        retryOn: [],
      },
    };
  }

  if (type === "SQL") {
    return {
      ...base,
      type: "SQL",
      sysCode: "",
      datasourceCode: "",
      operation: "UPDATE",
      sqlText: "",
      normalizedSql: "",
      tables: [],
      resultFields: [],
      conditionFields: [],
      parameters: [],
      safety: { requireWhere: true, maxAffectedRows: null },
      paramMapping: {},
    };
  }

  if (type === "ASSERT") {
    return {
      ...base,
      type: "ASSERT",
      assertions: [{ expression: "", message: "" }],
    };
  }

  return {
    ...base,
    type: "TRANSFORM",
    assignments: { "vars.value": "" },
  };
}

export function stepLabel(type: StepType): string {
  switch (type) {
    case "HTTP":
      return "HTTP 请求";
    case "SQL":
      return "SQL 操作";
    case "ASSERT":
      return "断言";
    case "TRANSFORM":
      return "转换";
  }
}

export function createDefaultHttpSource(): HttpSourceConfig {
  return {
    sourceCode: "",
    sourceName: "",
    sysCode: "",
    path: "",
    method: "POST",
    timeoutConfig: createDefaultHttpTimeoutConfig(),
    requestMapping: { headers: {}, query: {}, body: {} },
    bodySchema: null,
    responseSchema: null,
    responseHeadersSchema: null,
    responseCookiesSchema: null,
    responseHandling: {
      expectedContentType: "JSON",
      statusCode: { success: [200] },
      businessSuccess: { allOf: [createConditionRule()] },
      businessFailure: { anyOf: [] },
    },
    errorMapping: {
      messageTemplate: "",
      fields: {},
      fallbackMessage: "",
      exposeRawResponse: false,
    },
    businessErrorMapping: {
      messageTemplate: "",
      fields: {},
      fallbackMessage: "",
      exposeRawResponse: false,
    },
    outputMapping: {},
    outputMeta: null,
    retryPolicy: {
      enabled: false,
      maxAttempts: 1,
      intervalMs: 1000,
      retryOn: [],
    },
    status: "ENABLED",
  };
}

export function createDefaultSqlSource(): SqlSourceConfig {
  return {
    sourceCode: "",
    sourceName: "",
    sysCode: "",
    datasourceCode: "",
    operation: "SELECT",
    sqlText: "",
    normalizedSql: "",
    tables: [],
    resultFields: [],
    conditionFields: [],
    parameters: [],
    safety: { requireWhere: true, maxAffectedRows: null },
    status: "ENABLED",
  };
}

export function createDefaultTask(): TaskDefinition {
  return {
    taskCode: "",
    taskName: "",
    taskRemark: "",
    environmentField: "env",
    inputSchema: [createEnvField()],
    steps: [],
    resultMapping: {},
    status: "DRAFT",
  };
}
