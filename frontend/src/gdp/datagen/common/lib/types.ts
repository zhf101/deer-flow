export type SceneStatus = "DRAFT" | "PUBLISHED" | "DISABLED";
export type VersionStatus = "DRAFT" | "PUBLISHED";
export type ConfigStatus = "ENABLED" | "DISABLED";
export type StepType = "HTTP" | "SQL" | "ASSERT" | "TRANSFORM";
export type InputFieldType =
  | "string"
  | "number"
  | "boolean"
  | "date"
  | "enum"
  | "object"
  | "array";
export type HttpMethod = "GET" | "POST";
export type SqlOperation = "SELECT" | "INSERT" | "UPDATE" | "DELETE";
export type ConditionOperator =
  | "EQ"
  | "NE"
  | "NEQ"
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

export interface HttpTimeoutConfig {
  connectTimeoutSeconds: number;
  readTimeoutSeconds: number;
  writeTimeoutSeconds: number;
  poolTimeoutSeconds: number;
}

export interface AssertionDefinition {
  expression: string;
  message?: string | null;
}

export interface StepTemplateRef {
  type: "HTTP_SOURCE" | "SQL_SOURCE";
  sourceCode: string;
  sourceNameAtSnapshot?: string | null;
  sourceUpdatedAtSnapshot?: string | null;
  sourceHashSnapshot?: string | null;
  configHash?: string | null;
  snapshotAt?: string | null;
  drifted: boolean;
}

export interface BaseStepDefinition {
  stepId: string;
  stepName?: string | null;
  type: StepType;
  executionOrder?: number | null;
  enabled: boolean;
  dependsOn: string[];
  description?: string | null;
  position?: Position | null;
  templateRef?: StepTemplateRef | null;
  outputMapping: Record<string, string>;
  outputMeta?: Record<string, { label?: string; remark?: string }> | null;
}

export interface HttpStepDefinition extends BaseStepDefinition {
  type: "HTTP";
  sourceName?: string | null;
  sysCode?: string | null;
  method: HttpMethod;
  path?: string | null;
  timeoutConfig: HttpTimeoutConfig;
  requestMapping: Record<string, unknown>;
  httpParamMapping: Record<string, unknown>;
  bodySchema?: InputFieldDefinition[] | null;
  responseSchema?: InputFieldDefinition[] | null;
  responseHeadersSchema?: InputFieldDefinition[] | null;
  responseCookiesSchema?: InputFieldDefinition[] | null;
  responseHandling?: ResponseHandling | null;
  errorMapping?: ErrorMapping | null;
  businessErrorMapping?: ErrorMapping | null;
  retryPolicy?: RetryPolicy | null;
}

export interface SqlStepDefinition extends BaseStepDefinition {
  type: "SQL";
  sourceName?: string | null;
  sysCode?: string | null;
  datasourceCode?: string | null;
  operation?: SqlOperation | null;
  sqlText?: string | null;
  normalizedSql?: string | null;
  tables?: SqlSourceTableMeta[];
  resultFields?: SqlSourceFieldMeta[];
  conditionFields?: SqlSourceConditionMeta[];
  parameters?: SqlSourceParameter[];
  safety?: SqlTemplateSafety;
  paramMapping: Record<string, unknown>;
}

export interface AssertStepDefinition extends BaseStepDefinition {
  type: "ASSERT";
  assertions: AssertionDefinition[];
}

export interface TransformStepDefinition extends BaseStepDefinition {
  type: "TRANSFORM";
  assignments: Record<string, string>;
}

export type StepDefinition =
  | HttpStepDefinition
  | SqlStepDefinition
  | AssertStepDefinition
  | TransformStepDefinition;

export function isHttpStep(step: StepDefinition): step is HttpStepDefinition {
  return step.type === "HTTP";
}

export function isSqlStep(step: StepDefinition): step is SqlStepDefinition {
  return step.type === "SQL";
}

export function isAssertStep(step: StepDefinition): step is AssertStepDefinition {
  return step.type === "ASSERT";
}

export function isTransformStep(step: StepDefinition): step is TransformStepDefinition {
  return step.type === "TRANSFORM";
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
  publishedVersionNo?: number | null;
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

export interface SysConfig {
  sysCode: string;
  sysName: string;
  status: ConfigStatus;
  remark?: string | null;
}

export interface SysResponse extends SysConfig {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export interface ServiceEndpointConfig {
  envCode: string;
  sysCode: string;
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
  sysCode: string;
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

export type IdentifierReferenceType =
  | "TIME"
  | "MATCHER"
  | "TPN"
  | "LOGIN"
  | "BASE64";

export interface IdentifierReferenceParameter {
  name: string;
  description: string;
  required: boolean;
  defaultValue?: unknown;
}

export interface IdentifierReferenceExample {
  expression: string;
  description: string;
}

export interface IdentifierReferenceConfig {
  refCode: string;
  refName: string;
  refType: IdentifierReferenceType;
  syntax: string;
  description: string;
  usageScope: string[];
  parameters: IdentifierReferenceParameter[];
  examples: IdentifierReferenceExample[];
  status: ConfigStatus;
  remark?: string | null;
}

export interface IdentifierReferenceResponse
  extends IdentifierReferenceConfig {
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

// ── HTTP 接口配置（httpsource）──────────────────────────────────────────

export interface HttpSourceConfig {
  sourceCode: string;
  sourceName: string;
  sysCode: string;
  path: string;
  method: HttpMethod;
  timeoutConfig: HttpTimeoutConfig;
  requestMapping: Record<string, unknown>;
  bodySchema?: InputFieldDefinition[] | null;
  responseSchema?: InputFieldDefinition[] | null;
  responseHeadersSchema?: InputFieldDefinition[] | null;
  responseCookiesSchema?: InputFieldDefinition[] | null;
  responseHandling?: ResponseHandling | null;
  errorMapping?: ErrorMapping | null;
  businessErrorMapping?: ErrorMapping | null;
  outputMapping: Record<string, string>;
  outputMeta?: Record<string, { label?: string; remark?: string }> | null;
  retryPolicy?: RetryPolicy | null;
  status: ConfigStatus;
}

export interface HttpSourceResponse extends HttpSourceConfig {
  id: string;
  createdBy?: string | null;
  updatedBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ParsedCookie {
  name: string;
  value: string;
  domain?: string | null;
  path?: string | null;
  expires?: string | null;
  httpOnly: boolean;
  secure: boolean;
  sameSite?: string | null;
  raw: string;
}

export interface BusinessResult {
  isSuccess: boolean;
  reason: string;
  matchedRules: string[];
}

export interface RetryInfo {
  attempts: number;
  lastError?: string | null;
}

export interface HttpSourceTestRequestInfo {
  url: string;
  method: string;
  headers: Record<string, string>;
  query: Record<string, unknown>;
  body?: unknown;
  bodyType: string;
}

export interface HttpSourceTestResponseInfo {
  statusCode?: number | null;
  headers: Record<string, string>;
  body?: unknown;
  cookies: ParsedCookie[];
  elapsedMs?: number | null;
}

export interface HttpSourceTestErrorInfo {
  type: string;
  message: string;
  detail?: string | null;
}

export interface HttpSourceTestResult {
  success: boolean;
  request: HttpSourceTestRequestInfo;
  response?: HttpSourceTestResponseInfo | null;
  businessResult?: BusinessResult | null;
  extractedOutputs: Record<string, unknown>;
  retryInfo?: RetryInfo | null;
  error?: HttpSourceTestErrorInfo | null;
}

// ── SQL 配置（sqlsource）────────────────────────────────────────────────

export interface SqlSourceParameter {
  name: string;
  type: InputFieldType | string;
  required: boolean;
  defaultValue?: unknown;
  description?: string | null;
}

export interface SqlSourceTableMeta {
  id: string;
  tableName: string;
  alias: string;
  description: string;
}

export interface SqlSourceFieldMeta {
  id: string;
  fieldName: string;
  sourceTable: string;
  alias: string;
  description: string;
}

export interface SqlSourceConditionMeta {
  id: string;
  fieldName: string;
  sourceTable: string;
  paramName: string;
  description: string;
}

export interface SqlSourceParseResponse {
  normalizedSql: string;
  operation: SqlOperation;
  tables: SqlSourceTableMeta[];
  resultFields: SqlSourceFieldMeta[];
  conditionFields: SqlSourceConditionMeta[];
  parameters: SqlSourceParameter[];
}

export interface SqlSourceConfig {
  sourceCode: string;
  sourceName: string;
  sysCode: string;
  datasourceCode: string;
  operation: SqlOperation;
  sqlText: string;
  normalizedSql: string;
  tables: SqlSourceTableMeta[];
  resultFields: SqlSourceFieldMeta[];
  conditionFields: SqlSourceConditionMeta[];
  parameters: SqlSourceParameter[];
  safety: SqlTemplateSafety;
  status: ConfigStatus;
}

export interface SqlSourceResponse extends SqlSourceConfig {
  id: string;
  createdBy?: string | null;
  updatedBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SqlExecutionOptions {
  timeoutSeconds?: number;
  maxRows?: number;
  dryRun?: boolean;
  explain?: boolean;
}

export interface SqlExecutionErrorInfo {
  type: string;
  message: string;
  detail?: string | null;
}

export interface SqlExecutionResult {
  success: boolean;
  dbType: string;
  operation: SqlOperation;
  columns: Array<{ name: string; type?: string | null }>;
  rows: Record<string, unknown>[];
  row?: Record<string, unknown> | null;
  affectedRows: number;
  lastInsertId?: unknown;
  generatedKeys: unknown[];
  warnings: string[];
  elapsedMs?: number | null;
  extractedOutputs: Record<string, unknown>;
  error?: SqlExecutionErrorInfo | null;
}

// ── 造数任务（task）──────────────────────────────────────────────────────

export interface TaskStepDefinition {
  stepId: string;
  sceneCode: string;
  stepName?: string | null;
  enabled: boolean;
  dependsOn: string[];
  inputMapping: Record<string, unknown>;
  outputMapping: Record<string, string>;
}

export interface TaskDefinition {
  taskCode: string;
  taskName: string;
  taskRemark?: string | null;
  environmentField: "env";
  inputSchema: InputFieldDefinition[];
  steps: TaskStepDefinition[];
  resultMapping: Record<string, unknown>;
  status: SceneStatus;
}

export interface TaskSummary {
  id: string;
  taskCode: string;
  taskName: string;
  taskRemark?: string | null;
  status: SceneStatus;
  currentVersionNo?: number | null;
  createdBy?: string | null;
  updatedBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TaskVersion {
  id: string;
  taskCode: string;
  versionNo: number;
  versionStatus: VersionStatus;
  definition: TaskDefinition;
  validationResult?: Record<string, unknown> | null;
  createdBy?: string | null;
  createdAt: string;
  publishedBy?: string | null;
  publishedAt?: string | null;
}

export interface TaskValidationIssue {
  field: string;
  message: string;
  level: "ERROR" | "WARNING";
}

export interface TaskValidationResult {
  valid: boolean;
  issues: TaskValidationIssue[];
}

// ── 执行引擎相关类型 ─────────────────────────────────────────────────

/** 执行请求——客户端提交的执行参数 */
export interface ExecutionRequest {
  envCode: string;
  inputs: Record<string, unknown>;
}

/** 单个步骤的执行结果 */
export interface StepResult {
  stepId: string;
  stepName?: string | null;
  type: StepType;
  stepOrder?: number | null;
  timelineOrder?: number | null;
  status: "SUCCESS" | "FAILED" | "SKIPPED";
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  outputs: Record<string, unknown>;
  rawResponse?: unknown;
  error?: string | null;
  statusCode?: number | null;
}

/** 整个场景的执行结果 */
export interface ExecutionResult {
  runId?: string | null;
  sceneCode: string;
  versionNo: number;
  envCode: string;
  inputs: Record<string, unknown>;
  status: "SUCCESS" | "FAILED" | "PARTIAL";
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  stepResults: StepResult[];
  finalOutput: Record<string, unknown>;
  errors: string[];
}

/** 场景执行记录摘要（列表用） */
export interface SceneRunSummary {
  runId: string;
  sceneCode: string;
  versionNo: number;
  envCode: string;
  status: "SUCCESS" | "FAILED" | "PARTIAL";
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  inputs: Record<string, unknown>;
  finalOutput: Record<string, unknown>;
  errors: string[];
  stepCount: number;
  successCount: number;
  failedCount: number;
}

/** 任务中单个场景步骤的执行结果 */
export interface TaskStepExecutionResult {
  stepId: string;
  sceneCode: string;
  status: "SUCCESS" | "FAILED" | "SKIPPED";
  durationMs: number;
  outputs: Record<string, unknown>;
  error?: string | null;
}

/** 整个造数任务的执行结果 */
export interface TaskExecutionResult {
  taskCode: string;
  status: "SUCCESS" | "FAILED" | "PARTIAL";
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  stepResults: TaskStepExecutionResult[];
  finalOutput: Record<string, unknown>;
  errors: string[];
}
