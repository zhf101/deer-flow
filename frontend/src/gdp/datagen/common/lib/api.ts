import { fetch as fetchWithAuth } from "@/core/api/fetcher";

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
  SqlTemplateConfig,
  SqlTemplateResponse,
  SysConfig,
  SysResponse,
  TaskDefinition,
  TaskExecutionResult,
  TaskSummary,
  TaskValidationResult,
  TaskVersion,
  ValidationResult,
} from "./types";

const DATAGEN_BASE_PATH = "/api/v1/datagen";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetchWithAuth(`${DATAGEN_BASE_PATH}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const detail = await readError(response);
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as unknown;
    if (typeof data === "object" && data !== null) {
      const detail = Reflect.get(data, "detail");
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail ?? data);
    }
  } catch {
    // 继续使用状态文本。
  }
  return response.statusText || `HTTP ${response.status}`;
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
  return request<SceneSummary[]>(
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
  return request<SceneVersion>("/scenes", {
    method: "POST",
    body: JSON.stringify(scene),
  });
}

export async function getScene(sceneCode: string): Promise<SceneDefinition> {
  return request<SceneDefinition>(`/scenes/${encodeURIComponent(sceneCode)}`);
}

export async function updateScene(
  sceneCode: string,
  scene: SceneDefinition,
): Promise<SceneVersion> {
  return request<SceneVersion>("/scenes/update", {
    method: "POST",
    body: JSON.stringify({ sceneCode, definition: scene }),
  });
}

export async function validateScene(
  sceneCode: string,
): Promise<ValidationResult> {
  return request<ValidationResult>(
    `/scenes/${encodeURIComponent(sceneCode)}/validate`,
    { method: "POST" },
  );
}

export async function publishScene(sceneCode: string): Promise<SceneVersion> {
  return request<SceneVersion>(
    `/scenes/${encodeURIComponent(sceneCode)}/publish`,
    { method: "POST" },
  );
}

export async function deleteScene(sceneCode: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/scenes/delete", {
    method: "POST",
    body: JSON.stringify({ sceneCode }),
  });
}

export async function copyScene(
  sceneCode: string,
  targetSceneCode: string,
): Promise<SceneVersion> {
  return request<SceneVersion>(
    `/scenes/${encodeURIComponent(sceneCode)}/copy${searchParams({
      targetSceneCode,
    })}`,
    { method: "POST" },
  );
}

export async function listEnvironments(): Promise<EnvironmentResponse[]> {
  return request<EnvironmentResponse[]>("/environments");
}

export async function saveEnvironment(
  env: EnvironmentConfig,
): Promise<EnvironmentResponse> {
  return request<EnvironmentResponse>("/environments", {
    method: "POST",
    body: JSON.stringify(env),
  });
}

export async function listSystems(): Promise<SysResponse[]> {
  return request<SysResponse[]>("/systems");
}

export async function saveSystem(config: SysConfig): Promise<SysResponse> {
  return request<SysResponse>("/systems", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function deleteSystem(
  sysCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/systems/delete", {
    method: "POST",
    body: JSON.stringify({ sysCode }),
  });
}

export async function listServiceEndpoints(
  params?: { envCode?: string; sysCode?: string } | string,
): Promise<ServiceEndpointResponse[]> {
  const query =
    typeof params === "string" ? { envCode: params } : (params ?? {});
  return request<ServiceEndpointResponse[]>(
    `/service-endpoints${searchParams(query)}`,
  );
}

export async function createServiceEndpoint(
  endpoint: ServiceEndpointConfig,
): Promise<ServiceEndpointResponse> {
  return request<ServiceEndpointResponse>("/service-endpoints", {
    method: "POST",
    body: JSON.stringify(endpoint),
  });
}

export async function updateServiceEndpoint(
  id: string,
  endpoint: ServiceEndpointConfig,
): Promise<ServiceEndpointResponse> {
  return request<ServiceEndpointResponse>(
    "/service-endpoints/update",
    { method: "POST", body: JSON.stringify({ endpointId: id, config: endpoint }) },
  );
}

export async function listDatasources(
  params?: { envCode?: string; sysCode?: string } | string,
): Promise<DatasourceResponse[]> {
  const query =
    typeof params === "string" ? { envCode: params } : (params ?? {});
  return request<DatasourceResponse[]>(
    `/datasources${searchParams(query)}`,
  );
}

export async function createDatasource(
  config: DatasourceConfig,
): Promise<DatasourceResponse> {
  return request<DatasourceResponse>("/datasources", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function updateDatasource(
  id: string,
  config: DatasourceConfig,
): Promise<DatasourceResponse> {
  return request<DatasourceResponse>("/datasources/update", {
    method: "POST",
    body: JSON.stringify({ datasourceId: id, config }),
  });
}

export async function deleteEnvironment(
  envCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/environments/delete", {
    method: "POST",
    body: JSON.stringify({ envCode }),
  });
}

export async function deleteServiceEndpoint(
  id: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/service-endpoints/delete", {
    method: "POST",
    body: JSON.stringify({ endpointId: id }),
  });
}

export async function deleteDatasource(
  id: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/datasources/delete", {
    method: "POST",
    body: JSON.stringify({ datasourceId: id }),
  });
}

export async function listSqlTemplates(): Promise<SqlTemplateResponse[]> {
  return request<SqlTemplateResponse[]>("/sql-templates");
}

export async function createSqlTemplate(
  template: SqlTemplateConfig,
): Promise<SqlTemplateResponse> {
  return request<SqlTemplateResponse>("/sql-templates", {
    method: "POST",
    body: JSON.stringify(template),
  });
}

export async function updateSqlTemplate(
  templateCode: string,
  template: SqlTemplateConfig,
): Promise<SqlTemplateResponse> {
  return request<SqlTemplateResponse>(
    `/sql-templates/${encodeURIComponent(templateCode)}`,
    { method: "PUT", body: JSON.stringify(template) },
  );
}

// ── 场景执行 ─────────────────────────────────────────────────────────

/** 执行已发布的造数场景 */
export async function runScene(
  sceneCode: string,
  body: ExecutionRequest,
): Promise<ExecutionResult> {
  return request<ExecutionResult>("/scenes/run", {
    method: "POST",
    body: JSON.stringify({ sceneCode, ...body }),
  });
}

/** 查询已持久化的场景执行详情 */
export async function getSceneRun(runId: string): Promise<ExecutionResult> {
  return request<ExecutionResult>(`/scenes/runs/${encodeURIComponent(runId)}`);
}

/** 查询场景执行历史列表 */
export async function listSceneRuns(params: {
  sceneCode?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<SceneRunSummary[]> {
  return request<SceneRunSummary[]>(
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
  return request<HttpSourceResponse[]>(
    `/http-sources${searchParams(params ?? {})}`,
  );
}

export async function createHttpSource(
  config: HttpSourceConfig,
): Promise<HttpSourceResponse> {
  return request<HttpSourceResponse>("/http-sources", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function getHttpSource(
  sourceCode: string,
): Promise<HttpSourceResponse> {
  return request<HttpSourceResponse>(
    `/http-sources/${encodeURIComponent(sourceCode)}`,
  );
}

export async function updateHttpSource(
  sourceCode: string,
  config: HttpSourceConfig,
): Promise<HttpSourceResponse> {
  return request<HttpSourceResponse>("/http-sources/update", {
    method: "POST",
    body: JSON.stringify({ ...config, sourceCode }),
  });
}

export async function disableHttpSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/http-sources/${encodeURIComponent(sourceCode)}/disable`,
    { method: "POST" },
  );
}

export async function deleteHttpSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/http-sources/${encodeURIComponent(sourceCode)}/delete`,
    { method: "POST" },
  );
}

export async function testHttpSource(
  envCode: string,
  config: HttpSourceConfig,
): Promise<HttpSourceTestResult> {
  return request<HttpSourceTestResult>("/http-sources/test", {
    method: "POST",
    body: JSON.stringify({ envCode, config }),
  });
}

// ── SQL 配置（sqlsource）─────────────────────────────────────────────────

export async function listSqlSources(params?: {
  sysCode?: string;
}): Promise<SqlSourceResponse[]> {
  return request<SqlSourceResponse[]>(
    `/sql-sources${searchParams(params ?? {})}`,
  );
}

export async function parseSqlSource(
  sqlText: string,
  parameters: SqlSourceConfig["parameters"] = [],
): Promise<SqlSourceParseResponse> {
  return request<SqlSourceParseResponse>("/sql-sources/parse", {
    method: "POST",
    body: JSON.stringify({ sqlText, parameters }),
  });
}

export async function createSqlSource(
  config: SqlSourceConfig,
): Promise<SqlSourceResponse> {
  return request<SqlSourceResponse>("/sql-sources", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function getSqlSource(
  sourceCode: string,
): Promise<SqlSourceResponse> {
  return request<SqlSourceResponse>(
    `/sql-sources/${encodeURIComponent(sourceCode)}`,
  );
}

export async function updateSqlSource(
  sourceCode: string,
  config: SqlSourceConfig,
): Promise<SqlSourceResponse> {
  return request<SqlSourceResponse>("/sql-sources/update", {
    method: "POST",
    body: JSON.stringify({ ...config, sourceCode }),
  });
}

export async function disableSqlSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/sql-sources/${encodeURIComponent(sourceCode)}/disable`,
    { method: "POST" },
  );
}

export async function deleteSqlSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/sql-sources/${encodeURIComponent(sourceCode)}/delete`,
    { method: "POST" },
  );
}

export async function testSqlSource(
  envCode: string,
  sourceCode: string,
  parameters: Record<string, unknown>,
  options?: SqlExecutionOptions,
): Promise<SqlExecutionResult> {
  return request<SqlExecutionResult>("/sql-sources/test", {
    method: "POST",
    body: JSON.stringify({ envCode, sourceCode, parameters, options }),
  });
}

export async function executeSql(
  envCode: string,
  config: SqlSourceConfig,
  parameters: Record<string, unknown>,
  options?: SqlExecutionOptions,
): Promise<SqlExecutionResult> {
  return request<SqlExecutionResult>("/sql/execute", {
    method: "POST",
    body: JSON.stringify({
      envCode,
      sysCode: config.sysCode,
      datasourceCode: config.datasourceCode,
      operation: config.operation,
      sqlText: config.normalizedSql || config.sqlText,
      parameters,
      safety: config.safety,
      options,
    }),
  });
}

// ── 造数任务（task）──────────────────────────────────────────────────────

export async function listTasks(params?: {
  keyword?: string;
  status?: SceneStatus | "";
  limit?: number;
  offset?: number;
}): Promise<TaskSummary[]> {
  return request<TaskSummary[]>(
    `/tasks${searchParams({
      keyword: params?.keyword,
      status: params?.status === "" ? undefined : params?.status,
      limit: params?.limit ?? 100,
      offset: params?.offset ?? 0,
    })}`,
  );
}

export async function createTask(
  task: TaskDefinition,
): Promise<TaskVersion> {
  return request<TaskVersion>("/tasks", {
    method: "POST",
    body: JSON.stringify(task),
  });
}

export async function getTask(taskCode: string): Promise<TaskDefinition> {
  return request<TaskDefinition>(`/tasks/${encodeURIComponent(taskCode)}`);
}

export async function updateTask(
  taskCode: string,
  task: TaskDefinition,
): Promise<TaskVersion> {
  return request<TaskVersion>(`/tasks/${encodeURIComponent(taskCode)}`, {
    method: "PUT",
    body: JSON.stringify(task),
  });
}

export async function validateTask(
  taskCode: string,
): Promise<TaskValidationResult> {
  return request<TaskValidationResult>(
    `/tasks/${encodeURIComponent(taskCode)}/validate`,
    { method: "POST" },
  );
}

export async function publishTask(
  taskCode: string,
): Promise<TaskVersion> {
  return request<TaskVersion>(
    `/tasks/${encodeURIComponent(taskCode)}/publish`,
    { method: "POST" },
  );
}

export async function disableTask(
  taskCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/tasks/${encodeURIComponent(taskCode)}/disable`,
    { method: "POST" },
  );
}

export async function deleteTask(
  taskCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/tasks/${encodeURIComponent(taskCode)}/delete`,
    { method: "POST" },
  );
}

export async function listTaskVersions(
  taskCode: string,
): Promise<TaskVersion[]> {
  return request<TaskVersion[]>(
    `/tasks/${encodeURIComponent(taskCode)}/versions`,
  );
}

export async function runTask(
  taskCode: string,
  body: ExecutionRequest,
): Promise<TaskExecutionResult> {
  return request<TaskExecutionResult>(
    `/tasks/${encodeURIComponent(taskCode)}/run`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
