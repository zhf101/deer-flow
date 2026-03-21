import { getBackendBaseURL } from "@/core/config";

import type {
  ConnectionTestResponse,
  CreateDataSourceRequest,
  DataSourceConfig,
  DataSourcesResponse,
  SchemaCacheClearResponse,
  UpdateDataSourceRequest,
} from "./types";

async function parseJsonOrThrow<T>(
  response: Response,
  fallbackMessage: string,
): Promise<T> {
  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(errorData.detail ?? fallbackMessage);
  }
  return response.json() as Promise<T>;
}

export async function listDataSources(enabledOnly = false) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources?enabled_only=${enabledOnly}`,
  );
  const data = await parseJsonOrThrow<DataSourcesResponse>(
    response,
    "Failed to load data sources",
  );
  return data.data_sources;
}

export async function getDataSource(dataSourceId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}`,
  );
  return parseJsonOrThrow<DataSourceConfig>(
    response,
    `Failed to load data source '${dataSourceId}'`,
  );
}

export async function createDataSource(request: CreateDataSourceRequest) {
  const response = await fetch(`${getBackendBaseURL()}/api/nlp2sql/data-sources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonOrThrow<DataSourceConfig>(
    response,
    "Failed to create data source",
  );
}

export async function updateDataSource(
  dataSourceId: string,
  request: UpdateDataSourceRequest,
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  return parseJsonOrThrow<DataSourceConfig>(
    response,
    "Failed to update data source",
  );
}

export async function deleteDataSource(dataSourceId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(errorData.detail ?? "Failed to delete data source");
  }
}

export async function testDataSource(dataSourceId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/test`,
    {
      method: "POST",
    },
  );
  return parseJsonOrThrow<ConnectionTestResponse>(
    response,
    "Failed to test data source",
  );
}

export async function clearSchemaCache(dataSourceId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/schema-cache`,
    {
      method: "DELETE",
    },
  );
  return parseJsonOrThrow<SchemaCacheClearResponse>(
    response,
    "Failed to clear schema cache",
  );
}
