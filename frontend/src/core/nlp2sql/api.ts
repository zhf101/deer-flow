import { getBackendBaseURL } from "@/core/config";

import type {
  ActivateEmbeddingProfileResponse,
  EmbeddingProfile,
  EmbeddingRebuildRequest,
  CreateEmbeddingProfileRequest,
  ConnectionTestResponse,
  CreateKnowledgeItemRequest,
  CreateDataSourceRequest,
  DataSourceConfig,
  DataSourcesResponse,
  EmbeddingProfilesResponse,
  HistoricalSqlImportRequest,
  IndexJobsResponse,
  KnowledgeFilesResponse,
  KnowledgeItem,
  KnowledgeItemsResponse,
  RetrievalPreviewRequest,
  RetrievalPreviewResponse,
  SchemaCacheClearResponse,
  UpdateKnowledgeItemRequest,
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

export async function listKnowledgeItems(
  dataSourceId: string,
  options?: { itemType?: string; query?: string },
) {
  const params = new URLSearchParams();
  if (options?.itemType) {
    params.set("item_type", options.itemType);
  }
  if (options?.query) {
    params.set("query", options.query);
  }
  const query = params.size > 0 ? `?${params.toString()}` : "";
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-items${query}`,
  );
  const data = await parseJsonOrThrow<KnowledgeItemsResponse>(
    response,
    "Failed to load knowledge items",
  );
  return data.knowledge_items;
}

export async function createKnowledgeItem(
  dataSourceId: string,
  request: CreateKnowledgeItemRequest,
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-items`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  return parseJsonOrThrow<KnowledgeItem>(
    response,
    "Failed to create knowledge item",
  );
}

export async function updateKnowledgeItem(
  dataSourceId: string,
  itemId: string,
  request: UpdateKnowledgeItemRequest,
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-items/${encodeURIComponent(itemId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  return parseJsonOrThrow<KnowledgeItem>(
    response,
    "Failed to update knowledge item",
  );
}

export async function deleteKnowledgeItem(dataSourceId: string, itemId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-items/${encodeURIComponent(itemId)}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(errorData.detail ?? "Failed to delete knowledge item");
  }
}

export async function listKnowledgeFiles(dataSourceId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-files`,
  );
  const data = await parseJsonOrThrow<KnowledgeFilesResponse>(
    response,
    "Failed to load knowledge files",
  );
  return data.knowledge_files;
}

export async function uploadKnowledgeFiles(
  dataSourceId: string,
  files: File[],
) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-files`,
    {
      method: "POST",
      body: formData,
    },
  );
  const data = await parseJsonOrThrow<IndexJobsResponse>(
    response,
    "Failed to upload knowledge files",
  );
  return data.index_jobs;
}

export async function deleteKnowledgeFile(dataSourceId: string, fileId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/knowledge-files/${encodeURIComponent(fileId)}`,
    {
      method: "DELETE",
    },
  );
  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(errorData.detail ?? "Failed to delete knowledge file");
  }
}

export async function importHistoricalSql(
  dataSourceId: string,
  request: HistoricalSqlImportRequest,
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/historical-sql/import`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  const data = await parseJsonOrThrow<IndexJobsResponse>(
    response,
    "Failed to import historical SQL",
  );
  return data.index_jobs;
}

export async function listIndexJobs(dataSourceId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/index-jobs`,
  );
  const data = await parseJsonOrThrow<IndexJobsResponse>(
    response,
    "Failed to load index jobs",
  );
  return data.index_jobs;
}

export async function listEmbeddingProfiles() {
  const response = await fetch(`${getBackendBaseURL()}/api/nlp2sql/embedding-profiles`);
  const data = await parseJsonOrThrow<EmbeddingProfilesResponse>(
    response,
    "Failed to load embedding profiles",
  );
  return data.embedding_profiles;
}

export async function createEmbeddingProfile(
  request: CreateEmbeddingProfileRequest,
) {
  const response = await fetch(`${getBackendBaseURL()}/api/nlp2sql/embedding-profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return parseJsonOrThrow<EmbeddingProfile>(
    response,
    "Failed to create embedding profile",
  );
}

export async function activateEmbeddingProfile(profileId: string) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/embedding-profiles/${encodeURIComponent(profileId)}/activate`,
    {
      method: "POST",
    },
  );
  return parseJsonOrThrow<ActivateEmbeddingProfileResponse>(
    response,
    "Failed to activate embedding profile",
  );
}

export async function rebuildEmbeddingProfile(
  profileId: string,
  request: EmbeddingRebuildRequest,
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/embedding-profiles/${encodeURIComponent(profileId)}/rebuild`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  const data = await parseJsonOrThrow<IndexJobsResponse>(
    response,
    "Failed to rebuild embedding profile",
  );
  return data.index_jobs;
}

export async function previewRetrieval(
  dataSourceId: string,
  request: RetrievalPreviewRequest,
) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/nlp2sql/data-sources/${encodeURIComponent(dataSourceId)}/retrieve-preview`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  return parseJsonOrThrow<RetrievalPreviewResponse>(
    response,
    "Failed to preview retrieval",
  );
}
