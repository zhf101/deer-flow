export type SceneStatus = "DRAFT" | "PUBLISHED" | "DISABLED";
export type VersionStatus = "DRAFT" | "PUBLISHED";
export type ConfigStatus = "ENABLED" | "DISABLED";
export type StepType = "HTTP" | "AUTH_HTTP" | "SQL" | "ASSERT" | "TRANSFORM";
export type InputFieldType =
  | "string"
  | "number"
  | "boolean"
  | "date"
  | "enum"
  | "object"
  | "array";
export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type SqlOperation = "SELECT" | "INSERT" | "UPDATE" | "DELETE";
export type ConditionOperator =
  | "EQ"
  | "NE"
  | "GT"
  | "GTE"
  | "LT"
  | "LTE"
  | "IN"
  | "NOT_IN"
  | "EXISTS"
  | "NOT_EXISTS"
  | "EMPTY"
  | "NOT_EMPTY"
  | "CONTAINS"
  | "REGEX";
export type RetryErrorType =
  | "NETWORK_TIMEOUT"
  | "CONNECTION_RESET"
  | "HTTP_5XX"
  | "RATE_LIMIT";

export interface InputFieldValidation {
  minLength?: number | null;
  maxLength?: number | null;
  pattern?: string | null;
  minimum?: number | null;
  maximum?: number | null;
}

export interface InputFieldDefinition {
  name: string;
  label?: string | null;
  remark?: string | null;
  type: InputFieldType;
  required: boolean;
  defaultValue?: unknown;
  optionsSource?: string | null;
  validation?: InputFieldValidation | null;
  batchEnabled: boolean;
  children?: InputFieldDefinition[] | null;
}

export interface Position {
  x: number;
  y: number;
}

export interface ConditionRule {
  path: string;
  op: ConditionOperator;
  value?: unknown;
}

export interface ResponseHandling {
  expectedContentType: "JSON" | "TEXT" | "XML" | "ANY";
  statusCode: {
    success: number[];
  };
  businessSuccess: {
    allOf: ConditionRule[];
  };
  businessFailure: {
    anyOf: ConditionRule[];
  };
}

export interface ErrorMapping {
  messageTemplate?: string | null;
  fields: Record<string, string>;
  fallbackMessage?: string | null;
  exposeRawResponse: boolean;
}

export interface RetryPolicy {
  enabled: boolean;
  maxAttempts: number;
  intervalMs: number;
  retryOn: RetryErrorType[];
}

export interface AuthMapping {
  token?: string | null;
  tokenType?: string | null;
  fields: Record<string, string>;
}

export interface AssertionDefinition {
  expression: string;
  message?: string | null;
}

export interface StepDefinition {
  stepId: string;
  stepName?: string | null;
  type: StepType;
  enabled: boolean;
  dependsOn: string[];
  description?: string | null;
  position?: Position | null;
  method?: HttpMethod | null;
  url?: string | null;
  serviceCode?: string | null;
  requestMapping: Record<string, unknown>;
  bodySchema?: InputFieldDefinition[] | null;
  bodyMapping?: Record<string, unknown> | null;
  responseSchema?: InputFieldDefinition[] | null;
  responseHandling?: ResponseHandling | null;
  errorMapping?: ErrorMapping | null;
  outputMapping: Record<string, string>;
  outputMeta?: Record<string, { label?: string; remark?: string }> | null;
  retryPolicy?: RetryPolicy | null;
  authMapping?: AuthMapping | null;
  datasource?: string | null;
  sqlTemplateCode?: string | null;
  operation?: SqlOperation | null;
  paramMapping: Record<string, unknown>;
  assertions: AssertionDefinition[];
  assignments: Record<string, string>;
}

export interface BatchConfig {
  enabled: boolean;
  failurePolicy: "STOP_ON_ERROR" | "CONTINUE_ON_ERROR";
  maxConcurrency: number;
}

export interface SceneDefinition {
  sceneCode: string;
  sceneName: string;
  sceneRemark?: string | null;
  sceneType?: string | null;
  environmentField: "env";
  inputSchema: InputFieldDefinition[];
  steps: StepDefinition[];
  resultSchema?: InputFieldDefinition[] | null;
  resultMapping: Record<string, string>;
  errorPolicy?: "STOP_ON_ERROR" | "CONTINUE_ON_ERROR";
  batchConfig: BatchConfig;
  status: SceneStatus;
}

export interface SceneSummary {
  id: string;
  sceneCode: string;
  sceneName: string;
  sceneRemark?: string | null;
  sceneType?: string | null;
  status: SceneStatus;
  currentVersionNo?: number | null;
  createdBy?: string | null;
  updatedBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SceneVersion {
  id: string;
  sceneCode: string;
  versionNo: number;
  versionStatus: VersionStatus;
  definition: SceneDefinition;
  validationResult?: Record<string, unknown> | null;
  createdBy?: string | null;
  createdAt: string;
  publishedBy?: string | null;
  publishedAt?: string | null;
}

export interface ValidationIssue {
  field: string;
  message: string;
  level: "ERROR" | "WARNING";
}

export interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

export interface EnvironmentConfig {
  envCode: string;
  envName: string;
  status: ConfigStatus;
  remark?: string | null;
}

export interface EnvironmentResponse extends EnvironmentConfig {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface ServiceEndpointConfig {
  envCode: string;
  serviceCode: string;
  serviceName: string;
  baseUrl: string;
  status: ConfigStatus;
}

export interface ServiceEndpointResponse extends ServiceEndpointConfig {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface DatasourceConfig {
  envCode: string;
  datasourceCode: string;
  datasourceName: string;
  dbType: string;
  host: string;
  port: number;
  databaseName: string;
  username?: string | null;
  password?: string | null;
  status: ConfigStatus;
}

export interface DatasourceResponse extends DatasourceConfig {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface SqlTemplateParameter {
  name: string;
  type: InputFieldType | string;
  required: boolean;
  defaultValue?: unknown;
}

export interface SqlTemplateSafety {
  requireWhere: boolean;
  maxAffectedRows?: number | null;
}

export interface SqlTemplateConfig {
  templateCode: string;
  templateName: string;
  operation: SqlOperation;
  datasourceType: string;
  sqlText: string;
  parameters: SqlTemplateParameter[];
  safety: SqlTemplateSafety;
  status: ConfigStatus;
}

export interface SqlTemplateResponse extends SqlTemplateConfig {
  id: string;
  createdBy?: string | null;
  updatedBy?: string | null;
  createdAt: string;
  updatedAt: string;
}
