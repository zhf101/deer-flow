import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import {
  activateEmbeddingProfile,
  clearSchemaCache,
  createEmbeddingProfile,
  createKnowledgeItem,
  createDataSource,
  deleteKnowledgeItem,
  deleteKnowledgeFile,
  deleteDataSource,
  getDataSourceSchema,
  getDataSource,
  importHistoricalSql,
  listEmbeddingProfiles,
  listIndexJobs,
  listKnowledgeFiles,
  listKnowledgeItems,
  listDataSources,
  previewRetrieval,
  rebuildEmbeddingProfile,
  testDataSource,
  upsertSchemaComment,
  uploadKnowledgeFiles,
  updateKnowledgeItem,
  updateDataSource,
} from "./api";
import type {
  CreateEmbeddingProfileRequest,
  CreateKnowledgeItemRequest,
  CreateDataSourceRequest,
  EmbeddingRebuildRequest,
  HistoricalSqlImportRequest,
  KnowledgeItemType,
  RetrievalPreviewRequest,
  SchemaCommentUpsertRequest,
  UpdateKnowledgeItemRequest,
  UpdateDataSourceRequest,
} from "./types";

export function useDataSources(enabledOnly = false) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["nlp2sql", "data-sources", enabledOnly],
    queryFn: () => listDataSources(enabledOnly),
  });
  return { dataSources: data ?? [], isLoading, error };
}

export function useDataSource(dataSourceId: string | null | undefined) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["nlp2sql", "data-source", dataSourceId],
    queryFn: () => getDataSource(dataSourceId!),
    enabled: !!dataSourceId,
  });
  return { dataSource: data ?? null, isLoading, error };
}

function invalidateDataSources(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["nlp2sql", "data-sources"] });
}

export function useCreateDataSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateDataSourceRequest) => createDataSource(request),
    onSuccess: (data) => {
      invalidateDataSources(queryClient);
      void queryClient.invalidateQueries({
        queryKey: ["nlp2sql", "data-source", data.id],
      });
    },
  });
}

export function useUpdateDataSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      request,
    }: {
      dataSourceId: string;
      request: UpdateDataSourceRequest;
    }) => updateDataSource(dataSourceId, request),
    onSuccess: (data, variables) => {
      invalidateDataSources(queryClient);
      void queryClient.invalidateQueries({
        queryKey: ["nlp2sql", "data-source", variables.dataSourceId],
      });
      if (data.id !== variables.dataSourceId) {
        void queryClient.invalidateQueries({
          queryKey: ["nlp2sql", "data-source", data.id],
        });
      }
    },
  });
}

export function useDeleteDataSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dataSourceId: string) => deleteDataSource(dataSourceId),
    onSuccess: () => {
      invalidateDataSources(queryClient);
    },
  });
}

export function useTestDataSource() {
  return useMutation({
    mutationFn: (dataSourceId: string) => testDataSource(dataSourceId),
  });
}

export function useClearSchemaCache() {
  return useMutation({
    mutationFn: (dataSourceId: string) => clearSchemaCache(dataSourceId),
  });
}

export function useDataSourceSchema(
  dataSourceId: string | null | undefined,
  options?: { forceRefresh?: boolean },
) {
  const { data, isLoading, error } = useQuery({
    queryKey: [
      "nlp2sql",
      "schema",
      dataSourceId,
      options?.forceRefresh === true,
    ],
    queryFn: () =>
      getDataSourceSchema(dataSourceId!, {
        forceRefresh: options?.forceRefresh,
      }),
    enabled: !!dataSourceId,
  });
  return { schema: data ?? null, isLoading, error };
}

function invalidateSchema(
  queryClient: ReturnType<typeof useQueryClient>,
  dataSourceId: string,
) {
  void queryClient.invalidateQueries({
    queryKey: ["nlp2sql", "schema", dataSourceId],
  });
}

export function useUpsertSchemaComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      request,
    }: {
      dataSourceId: string;
      request: SchemaCommentUpsertRequest;
    }) => upsertSchemaComment(dataSourceId, request),
    onSuccess: (_data, variables) => {
      invalidateSchema(queryClient, variables.dataSourceId);
      invalidateKnowledgeItems(queryClient, variables.dataSourceId);
    },
  });
}

export function useKnowledgeItems(
  dataSourceId: string | null | undefined,
  options?: { itemType?: KnowledgeItemType | ""; query?: string },
) {
  const { data, isLoading, error } = useQuery({
    queryKey: [
      "nlp2sql",
      "knowledge-items",
      dataSourceId,
      options?.itemType ?? "",
      options?.query ?? "",
    ],
    queryFn: () =>
      listKnowledgeItems(dataSourceId!, {
        itemType: options?.itemType ?? undefined,
        query: options?.query ?? undefined,
      }),
    enabled: !!dataSourceId,
  });
  return { knowledgeItems: data ?? [], isLoading, error };
}

function invalidateKnowledgeItems(
  queryClient: ReturnType<typeof useQueryClient>,
  dataSourceId: string,
) {
  void queryClient.invalidateQueries({
    queryKey: ["nlp2sql", "knowledge-items", dataSourceId],
  });
}

export function useCreateKnowledgeItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      request,
    }: {
      dataSourceId: string;
      request: CreateKnowledgeItemRequest;
    }) => createKnowledgeItem(dataSourceId, request),
    onSuccess: (data) => {
      invalidateKnowledgeItems(queryClient, data.data_source_id);
    },
  });
}

export function useUpdateKnowledgeItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      itemId,
      request,
    }: {
      dataSourceId: string;
      itemId: string;
      request: UpdateKnowledgeItemRequest;
    }) => updateKnowledgeItem(dataSourceId, itemId, request),
    onSuccess: (data) => {
      invalidateKnowledgeItems(queryClient, data.data_source_id);
    },
  });
}

export function useDeleteKnowledgeItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      itemId,
    }: {
      dataSourceId: string;
      itemId: string;
    }) => deleteKnowledgeItem(dataSourceId, itemId),
    onSuccess: (_data, variables) => {
      invalidateKnowledgeItems(queryClient, variables.dataSourceId);
    },
  });
}

export function useKnowledgeFiles(dataSourceId: string | null | undefined) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["nlp2sql", "knowledge-files", dataSourceId],
    queryFn: () => listKnowledgeFiles(dataSourceId!),
    enabled: !!dataSourceId,
  });
  return { knowledgeFiles: data ?? [], isLoading, error };
}

export function useIndexJobs(dataSourceId: string | null | undefined) {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["nlp2sql", "index-jobs", dataSourceId],
    queryFn: () => listIndexJobs(dataSourceId!),
    enabled: !!dataSourceId,
    refetchInterval: 3000,
    staleTime: 0,
    gcTime: 0,
  });

  useEffect(() => {
    if (!dataSourceId || !data) {
      return;
    }
    if (data.some((job) => job.status === "completed")) {
      invalidateKnowledgeFiles(queryClient, dataSourceId);
      invalidateKnowledgeItems(queryClient, dataSourceId);
    }
  }, [data, dataSourceId, queryClient]);

  return { indexJobs: data ?? [], isLoading, error };
}

function invalidateKnowledgeFiles(
  queryClient: ReturnType<typeof useQueryClient>,
  dataSourceId: string,
) {
  void queryClient.invalidateQueries({
    queryKey: ["nlp2sql", "knowledge-files", dataSourceId],
  });
}

function invalidateIndexJobs(
  queryClient: ReturnType<typeof useQueryClient>,
  dataSourceId: string,
) {
  void queryClient.invalidateQueries({
    queryKey: ["nlp2sql", "index-jobs", dataSourceId],
  });
}

export function useUploadKnowledgeFiles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      files,
    }: {
      dataSourceId: string;
      files: File[];
    }) => uploadKnowledgeFiles(dataSourceId, files),
    onSuccess: (_data, variables) => {
      invalidateIndexJobs(queryClient, variables.dataSourceId);
    },
  });
}

export function useDeleteKnowledgeFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      fileId,
    }: {
      dataSourceId: string;
      fileId: string;
    }) => deleteKnowledgeFile(dataSourceId, fileId),
    onSuccess: (_data, variables) => {
      invalidateKnowledgeFiles(queryClient, variables.dataSourceId);
      invalidateKnowledgeItems(queryClient, variables.dataSourceId);
    },
  });
}

export function useImportHistoricalSql() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      dataSourceId,
      request,
    }: {
      dataSourceId: string;
      request: HistoricalSqlImportRequest;
    }) => importHistoricalSql(dataSourceId, request),
    onSuccess: (_data, variables) => {
      invalidateIndexJobs(queryClient, variables.dataSourceId);
    },
  });
}

export function useEmbeddingProfiles() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["nlp2sql", "embedding-profiles"],
    queryFn: () => listEmbeddingProfiles(),
  });
  return { embeddingProfiles: data ?? [], isLoading, error };
}

export function useCreateEmbeddingProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateEmbeddingProfileRequest) =>
      createEmbeddingProfile(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["nlp2sql", "embedding-profiles"],
      });
    },
  });
}

export function useActivateEmbeddingProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => activateEmbeddingProfile(profileId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["nlp2sql", "embedding-profiles"],
      });
    },
  });
}

export function useRebuildEmbeddingProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      profileId,
      request,
    }: {
      profileId: string;
      request: EmbeddingRebuildRequest;
    }) => rebuildEmbeddingProfile(profileId, request),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["nlp2sql", "index-jobs"],
      });
      if (variables.request.data_source_id) {
        invalidateKnowledgeFiles(queryClient, variables.request.data_source_id);
        invalidateKnowledgeItems(queryClient, variables.request.data_source_id);
      }
    },
  });
}

export function useRetrievalPreview() {
  return useMutation({
    mutationFn: ({
      dataSourceId,
      request,
    }: {
      dataSourceId: string;
      request: RetrievalPreviewRequest;
    }) => previewRetrieval(dataSourceId, request),
  });
}
