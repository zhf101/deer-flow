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
  SceneDefinition,
  SceneStatus,
  SceneSummary,
  SceneVersion,
  ServiceEndpointConfig,
  ServiceEndpointResponse,
  SqlSourceConfig,
  SqlSourceParseResponse,
  SqlSourceResponse,
  SqlTemplateConfig,
  SqlTemplateResponse,
  TaskDefinition,
  TaskSummary,
  TaskValidationResult,
  TaskVersion,
  ValidationResult,
} from "./types";

const BASE_PATH = "/api/v1/data-factory";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetchWithAuth(`${BASE_PATH}${path}`, {
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
    // Fall through to status text.
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
  return request<SceneVersion>(`/scenes/${encodeURIComponent(sceneCode)}`, {
    method: "PUT",
    body: JSON.stringify(scene),
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
  return request<{ success: boolean }>(`/scenes/${encodeURIComponent(sceneCode)}/delete`, {
    method: "POST",
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

export async function listServiceEndpoints(
  envCode?: string,
): Promise<ServiceEndpointResponse[]> {
  return request<ServiceEndpointResponse[]>(
    `/service-endpoints${searchParams({ envCode })}`,
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
    `/service-endpoints/${encodeURIComponent(id)}`,
    { method: "PUT", body: JSON.stringify(endpoint) },
  );
}

export async function listDatasources(
  envCode?: string,
): Promise<DatasourceResponse[]> {
  return request<DatasourceResponse[]>(
    `/datasources${searchParams({ envCode })}`,
  );
}

export async function createDatasource(
  datasource: DatasourceConfig,
): Promise<DatasourceResponse> {
  return request<DatasourceResponse>("/datasources", {
    method: "POST",
    body: JSON.stringify(datasource),
  });
}

export async function updateDatasource(
  id: string,
  datasource: DatasourceConfig,
): Promise<DatasourceResponse> {
  return request<DatasourceResponse>(`/datasources/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(datasource),
  });
}

export async function deleteEnvironment(
  envCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/environments/${encodeURIComponent(envCode)}`,
    { method: "DELETE" },
  );
}

export async function deleteServiceEndpoint(
  id: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/service-endpoints/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export async function deleteDatasource(
  id: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/datasources/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
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
  return request<ExecutionResult>(
    `/scenes/${encodeURIComponent(sceneCode)}/run`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// ── HTTP 接口配置（httpsource）───────────────────────────────────────────

export async function listHttpSources(): Promise<HttpSourceResponse[]> {
  return request<HttpSourceResponse[]>("/http-sources");
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
  return request<HttpSourceResponse>(
    `/http-sources/${encodeURIComponent(sourceCode)}`,
    { method: "PUT", body: JSON.stringify(config) },
  );
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

// ── SQL 配置（sqlsource）─────────────────────────────────────────────────

export async function listSqlSources(): Promise<SqlSourceResponse[]> {
  return request<SqlSourceResponse[]>("/sql-sources");
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
  return request<SqlSourceResponse>(
    `/sql-sources/${encodeURIComponent(sourceCode)}`,
    { method: "PUT", body: JSON.stringify(config) },
  );
}

export async function disableSqlSource(
  sourceCode: string,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    `/sql-sources/${encodeURIComponent(sourceCode)}/disable`,
    { method: "POST" },
  );
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
