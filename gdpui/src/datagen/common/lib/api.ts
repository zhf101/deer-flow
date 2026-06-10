// Datagen API layer.
//
// Ported from the Next.js source (`fetch` + CSRF double-submit cookie) onto a
// dedicated axios instance. The gateway authenticates via an HttpOnly cookie
// and enforces CSRF on state-changing methods via a `csrf_token` cookie echoed
// in the `X-CSRF-Token` header — axios handles this automatically through
// `withCredentials` + `xsrfCookieName`/`xsrfHeaderName`.
//
// Error contract preserved from the source: every function rejects with a
// plain `Error` whose `message` is the backend `detail` string, so call sites
// can keep using `error instanceof Error ? error.message : "..."`.

import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig } from "axios";

import { buildLoginPath } from "@/auth/types";

import type {
  DatasourceConfig,
  DatasourceResponse,
  EnvironmentConfig,
  EnvironmentResponse,
  ExecutionRequest,
  ExecutionResult,
  HttpSourceConfig,
  HttpSourceResponse,
  HttpSourceTestResult,
  SceneDefinition,
  SceneStatus,
  SceneSummary,
  SceneRunSummary,
  SceneVersion,
  ServiceEndpointConfig,
  ServiceEndpointResponse,
  SqlSourceConfig,
  SqlExecutionOptions,
  SqlExecutionResult,
  SqlSourceParseResponse,
  SqlSourceResponse,
  SysConfig,
  SysResponse,
  TaskDefinition,
  TaskExecutionResult,
  TaskSummary,
  TaskValidationResult,
  TaskVersion,
  ValidationResult,
} from "./types";

// gdpui's axios baseURL is "/api" (proxied in dev), so the datagen prefix here
// is relative to that. Matches the source's "/api/v1/datagen".
const DATAGEN_BASE_PATH = "/v1/datagen";
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

const client: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}${DATAGEN_BASE_PATH}`,
  timeout: 60_000,
  // Send the HttpOnly auth cookie on cross-origin SSR-routed requests.
  withCredentials: true,
  // Double Submit Cookie: axios reads `csrf_token` and echoes it as the header
  // on state-changing methods, mirroring the gateway's CSRFMiddleware.
  xsrfCookieName: "csrf_token",
  xsrfHeaderName: "X-CSRF-Token",
  headers: { Accept: "application/json" },
});

/** Extract the backend `detail` message from an axios error response. */
function readErrorDetail(error: AxiosError): string {
  const data = error.response?.data as unknown;
  if (typeof data === "object" && data !== null) {
    const detail = Reflect.get(data, "detail");
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
    return JSON.stringify(data);
  }
  if (typeof data === "string" && data) return data;
  return error.response?.statusText || error.message || "请求失败";
}

async function request<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  try {
    const response = await client.request<T>({ url: path, ...config });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.response?.status === 401 && window.location.pathname !== "/login") {
        window.location.href = buildLoginPath(window.location.pathname + window.location.search);
      }
      throw new Error(readErrorDetail(error));
    }
    throw error;
  }
}

/** GET-style helper for read endpoints. */
function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

/** POST/PUT-style helper that serializes a JSON body. */
function send<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE" | "PATCH",
  body?: unknown,
): Promise<T> {
  return request<T>(path, {
    method,
    data: body,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
  });
}

function searchParams(params: Record<string, string | number | undefined>) {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      sp.set(key, String(value));
    }
  }
  const query = sp.toString();
  return query ? `?${query}` : "";
}

export async function listScenes(params: {
  sceneType?: string;
  status?: SceneStatus | "";
  keyword?: string;
  limit?: number;
  offset?: number;
}): Promise<SceneSummary[]> {
  return get<SceneSummary[]>(
    `/scenes${searchParams({
      sceneType: params.sceneType,
      status: params.status === "" ? undefined : params.status,
      keyword: params.keyword,
      limit: params.limit ?? 100,
      offset: params.offset ?? 0,
    })}`,
  );
}

export async function createScene(scene: SceneDefinition): Promise<SceneVersion> {
  return send<SceneVersion>("/scenes", "POST", scene);
}

export async function getScene(sceneCode: string): Promise<SceneDefinition> {
  return get<SceneDefinition>(`/scenes/${encodeURIComponent(sceneCode)}`);
}

export async function updateScene(
  sceneCode: string,
  scene: SceneDefinition,
): Promise<SceneVersion> {
  return send<SceneVersion>("/scenes/update", "POST", { sceneCode, definition: scene });
}

export async function validateScene(sceneCode: string): Promise<ValidationResult> {
  return send<ValidationResult>(
    `/scenes/${encodeURIComponent(sceneCode)}/validate`,
    "POST",
  );
}

export async function publishScene(sceneCode: string): Promise<SceneVersion> {
  return send<SceneVersion>(
    `/scenes/${encodeURIComponent(sceneCode)}/publish`,
    "POST",
  );
}

export async function deleteScene(sceneCode: string): Promise<{ success: boolean }> {
  return send<{ success: boolean }>("/scenes/delete", "POST", { sceneCode });
}

export async function copyScene(
  sceneCode: string,
  targetSceneCode: string,
): Promise<SceneVersion> {
  return send<SceneVersion>(
    `/scenes/${encodeURIComponent(sceneCode)}/copy${searchParams({ targetSceneCode })}`,
    "POST",
  );
}

export async function listEnvironments(): Promise<EnvironmentResponse[]> {
  return get<EnvironmentResponse[]>("/environments");
}

export async function saveEnvironment(
  env: EnvironmentConfig,
): Promise<EnvironmentResponse> {
  return send<EnvironmentResponse>("/environments", "POST", env);
}

export async function listSystems(): Promise<SysResponse[]> {
  return get<SysResponse[]>("/systems");
}

export async function saveSystem(config: SysConfig): Promise<SysResponse> {
  return send<SysResponse>("/systems", "POST", config);
}

export async function deleteSystem(sysCode: string): Promise<{ success: boolean }> {
  return send<{ success: boolean }>("/systems/delete", "POST", { sysCode });
}

export async function listServiceEndpoints(
  params?: { envCode?: string; sysCode?: string } | string,
): Promise<ServiceEndpointResponse[]> {
  const query = typeof params === "string" ? { envCode: params } : (params ?? {});
  return get<ServiceEndpointResponse[]>(`/service-endpoints${searchParams(query)}`);
}

export async function createServiceEndpoint(
  endpoint: ServiceEndpointConfig,
): Promise<ServiceEndpointResponse> {
  return send<ServiceEndpointResponse>("/service-endpoints", "POST", endpoint);
}

export async function updateServiceEndpoint(
  id: string,
  endpoint: ServiceEndpointConfig,
): Promise<ServiceEndpointResponse> {
  return send<ServiceEndpointResponse>("/service-endpoints/update", "POST", {
    endpointId: id,
    config: endpoint,
  });
}

export async function listDatasources(
  params?: { envCode?: string; sysCode?: string } | string,
): Promise<DatasourceResponse[]> {
  const query = typeof params === "string" ? { envCode: params } : (params ?? {});
  return get<DatasourceResponse[]>(`/datasources${searchParams(query)}`);
}

export async function createDatasource(
  config: DatasourceConfig,
): Promise<DatasourceResponse> {
  return send<DatasourceResponse>("/datasources", "POST", config);
}

export async function updateDatasource(
  id: string,
  config: DatasourceConfig,
): Promise<DatasourceResponse> {
  return send<DatasourceResponse>("/datasources/update", "POST", {
    datasourceId: id,
    config,
  });
}

export async function deleteEnvironment(
  envCode: string,
): Promise<{ success: boolean }> {
  return send<{ success: boolean }>("/environments/delete", "POST", { envCode });
}

export async function deleteServiceEndpoint(
  id: string,
): Promise<{ success: boolean }> {
  return send<{ success: boolean }>("/service-endpoints/delete", "POST", {
    endpointId: id,
  });
}

export async function deleteDatasource(id: string): Promise<{ success: boolean }> {
  return send<{ success: boolean }>("/datasources/delete", "POST", {
    datasourceId: id,
  });
}

// ── 场景执行 ─────────────────────────────────────────────────────────

/** 执行已发布的造数场景 */
export async function runScene(
  sceneCode: string,
  body: ExecutionRequest,
): Promise<ExecutionResult> {
  return send<ExecutionResult>("/scenes/run", "POST", { sceneCode, ...body });
}

/** 查询已持久化的场景执行详情 */
export async function getSceneRun(runId: string): Promise<ExecutionResult> {
  return get<ExecutionResult>(`/scenes/runs/${encodeURIComponent(runId)}`);
}

/** 查询场景执行历史列表 */
export async function listSceneRuns(params: {
  sceneCode?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<SceneRunSummary[]> {
  return get<SceneRunSummary[]>(
    `/scenes/runs${searchParams({
      sceneCode: params.sceneCode,
      status: params.status,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    })}`,
  );
}

// ── HTTP 接口配置（httpsource）───────────────────────────────────────────

export async function listHttpSources(params?: {
  sysCode?: string;
}): Promise<HttpSourceResponse[]> {
  return get<HttpSourceResponse[]>(`/http-sources${searchParams(params ?? {})}`);
}

export async function createHttpSource(
  config: HttpSourceConfig,
): Promise<HttpSourceResponse> {
  return send<HttpSourceResponse>("/http-sources", "POST", config);
}

export async function getHttpSource(
  sourceCode: string,
): Promise<HttpSourceResponse> {
  return get<HttpSourceResponse>(`/http-sources/${encodeURIComponent(sourceCode)}`);
}

export async function updateHttpSource(
  sourceCode: string,
  config: HttpSourceConfig,
): Promise<HttpSourceResponse> {
  return send<HttpSourceResponse>("/http-sources/update", "POST", {
    ...config,
    sourceCode,
  });
}

export async function disableHttpSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return send<{ success: boolean }>(
    `/http-sources/${encodeURIComponent(sourceCode)}/disable`,
    "POST",
  );
}

export async function deleteHttpSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return send<{ success: boolean }>(
    `/http-sources/${encodeURIComponent(sourceCode)}/delete`,
    "POST",
  );
}

export async function testHttpSource(
  envCode: string,
  config: HttpSourceConfig,
): Promise<HttpSourceTestResult> {
  return send<HttpSourceTestResult>("/http-sources/test", "POST", { envCode, config });
}

// ── SQL 配置（sqlsource）─────────────────────────────────────────────────

export async function listSqlSources(params?: {
  sysCode?: string;
}): Promise<SqlSourceResponse[]> {
  return get<SqlSourceResponse[]>(`/sql-sources${searchParams(params ?? {})}`);
}

export async function parseSqlSource(
  sqlText: string,
  parameters: SqlSourceConfig["parameters"] = [],
): Promise<SqlSourceParseResponse> {
  return send<SqlSourceParseResponse>("/sql-sources/parse", "POST", {
    sqlText,
    parameters,
  });
}

export async function createSqlSource(
  config: SqlSourceConfig,
): Promise<SqlSourceResponse> {
  return send<SqlSourceResponse>("/sql-sources", "POST", config);
}

export async function getSqlSource(sourceCode: string): Promise<SqlSourceResponse> {
  return get<SqlSourceResponse>(`/sql-sources/${encodeURIComponent(sourceCode)}`);
}

export async function updateSqlSource(
  sourceCode: string,
  config: SqlSourceConfig,
): Promise<SqlSourceResponse> {
  return send<SqlSourceResponse>("/sql-sources/update", "POST", {
    ...config,
    sourceCode,
  });
}

export async function disableSqlSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return send<{ success: boolean }>(
    `/sql-sources/${encodeURIComponent(sourceCode)}/disable`,
    "POST",
  );
}

export async function deleteSqlSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return send<{ success: boolean }>(
    `/sql-sources/${encodeURIComponent(sourceCode)}/delete`,
    "POST",
  );
}

export async function testSqlSource(
  envCode: string,
  sourceCode: string,
  parameters: Record<string, unknown>,
  options?: SqlExecutionOptions,
): Promise<SqlExecutionResult> {
  return send<SqlExecutionResult>("/sql-sources/test", "POST", {
    envCode,
    sourceCode,
    parameters,
    options,
  });
}

export async function executeSql(
  envCode: string,
  config: SqlSourceConfig,
  parameters: Record<string, unknown>,
  options?: SqlExecutionOptions,
): Promise<SqlExecutionResult> {
  return send<SqlExecutionResult>("/sql/execute", "POST", {
    envCode,
    sysCode: config.sysCode,
    datasourceCode: config.datasourceCode,
    operation: config.operation,
    sqlText: config.normalizedSql || config.sqlText,
    parameters,
    safety: config.safety,
    options,
  });
}

// ── 造数任务（task）──────────────────────────────────────────────────────

export async function listTasks(params?: {
  keyword?: string;
  status?: SceneStatus | "";
  limit?: number;
  offset?: number;
}): Promise<TaskSummary[]> {
  return get<TaskSummary[]>(
    `/tasks${searchParams({
      keyword: params?.keyword,
      status: params?.status === "" ? undefined : params?.status,
      limit: params?.limit ?? 100,
      offset: params?.offset ?? 0,
    })}`,
  );
}

export async function createTask(task: TaskDefinition): Promise<TaskVersion> {
  return send<TaskVersion>("/tasks", "POST", task);
}

export async function getTask(taskCode: string): Promise<TaskDefinition> {
  return get<TaskDefinition>(`/tasks/${encodeURIComponent(taskCode)}`);
}

export async function updateTask(
  taskCode: string,
  task: TaskDefinition,
): Promise<TaskVersion> {
  return send<TaskVersion>(`/tasks/${encodeURIComponent(taskCode)}`, "PUT", task);
}

export async function validateTask(
  taskCode: string,
): Promise<TaskValidationResult> {
  return send<TaskValidationResult>(
    `/tasks/${encodeURIComponent(taskCode)}/validate`,
    "POST",
  );
}

export async function publishTask(taskCode: string): Promise<TaskVersion> {
  return send<TaskVersion>(`/tasks/${encodeURIComponent(taskCode)}/publish`, "POST");
}

export async function disableTask(taskCode: string): Promise<{ success: boolean }> {
  return send<{ success: boolean }>(
    `/tasks/${encodeURIComponent(taskCode)}/disable`,
    "POST",
  );
}

export async function deleteTask(taskCode: string): Promise<{ success: boolean }> {
  return send<{ success: boolean }>(
    `/tasks/${encodeURIComponent(taskCode)}/delete`,
    "POST",
  );
}

export async function listTaskVersions(taskCode: string): Promise<TaskVersion[]> {
  return get<TaskVersion[]>(`/tasks/${encodeURIComponent(taskCode)}/versions`);
}

export async function runTask(
  taskCode: string,
  body: ExecutionRequest,
): Promise<TaskExecutionResult> {
  return send<TaskExecutionResult>(
    `/tasks/${encodeURIComponent(taskCode)}/run`,
    "POST",
    body,
  );
}
