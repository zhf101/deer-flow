import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  clearSchemaCache,
  createDataSource,
  deleteDataSource,
  getDataSource,
  listDataSources,
  testDataSource,
  updateDataSource,
} from "./api";
import type {
  CreateDataSourceRequest,
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
