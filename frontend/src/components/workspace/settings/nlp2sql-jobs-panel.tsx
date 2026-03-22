"use client";

import { ListTodoIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { useI18n } from "@/core/i18n/hooks";
import { useIndexJobs, type IndexJob, type IndexJobStatus, type IndexJobType } from "@/core/nlp2sql";

function formatJobType(
  type: IndexJobType,
  t: ReturnType<typeof useI18n>["t"],
): string {
  switch (type) {
    case "file_import":
      return t.settings.nlp2sql.jobsTypeFileImport;
    case "historical_sql_import":
      return t.settings.nlp2sql.jobsTypeHistoricalSqlImport;
    case "embedding_rebuild":
      return t.settings.nlp2sql.jobsTypeEmbeddingRebuild;
    default:
      return type;
  }
}

function formatJobStatus(
  status: IndexJobStatus,
  t: ReturnType<typeof useI18n>["t"],
): string {
  switch (status) {
    case "queued":
      return t.settings.nlp2sql.jobsStatusQueued;
    case "running":
      return t.settings.nlp2sql.jobsStatusRunning;
    case "completed":
      return t.settings.nlp2sql.jobsStatusCompleted;
    case "failed":
      return t.settings.nlp2sql.jobsStatusFailed;
    default:
      return status;
  }
}

function JobStatusBadge({
  status,
  t,
}: {
  status: IndexJobStatus;
  t: ReturnType<typeof useI18n>["t"];
}) {
  if (status === "completed") {
    return <Badge variant="default">{formatJobStatus(status, t)}</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">{formatJobStatus(status, t)}</Badge>;
  }
  return <Badge variant="outline">{formatJobStatus(status, t)}</Badge>;
}

function describeTargetScope(job: IndexJob): string {
  const targetScope = job.target_scope as {
    files?: unknown;
    source_name?: unknown;
    statement_count?: unknown;
  };
  const rawFiles = targetScope.files;
  const files = Array.isArray(rawFiles)
    ? rawFiles
    : null;
  if (files && files.length > 0) {
    return files
      .map((file) =>
        typeof file === "object" && file !== null && typeof file.file_name === "string"
          ? file.file_name
          : null,
      )
      .filter((value): value is string => Boolean(value))
      .join(", ");
  }
  if (typeof targetScope.source_name === "string") {
    return targetScope.source_name;
  }
  if (typeof targetScope.statement_count === "number") {
    return `${targetScope.statement_count} statements`;
  }
  return "";
}

export function Nlp2SqlJobsPanel({ dataSourceId }: { dataSourceId: string }) {
  const { t } = useI18n();
  const { indexJobs, isLoading, error } = useIndexJobs(dataSourceId);

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium">
          {t.settings.nlp2sql.jobsListTitle}
        </div>
        <div className="text-muted-foreground text-sm">
          {t.settings.nlp2sql.jobsEmptyDescription}
        </div>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : error ? (
        <div className="text-destructive text-sm">{error.message}</div>
      ) : indexJobs.length === 0 ? (
        <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
          {t.settings.nlp2sql.jobsEmptyTitle}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {indexJobs.map((job) => (
            <Item key={job.id} variant="outline">
              <ItemContent>
                <ItemTitle>
                  <ListTodoIcon className="size-4" />
                  {formatJobType(job.job_type, t)}
                </ItemTitle>
                <ItemDescription>
                  {t.settings.nlp2sql.jobsProgress}: {job.progress_done}/
                  {job.progress_total}
                  {describeTargetScope(job)
                    ? ` · ${describeTargetScope(job)}`
                    : ""}
                  {job.created_at
                    ? ` · ${t.settings.nlp2sql.jobsCreatedAt}: ${new Date(job.created_at).toLocaleString()}`
                    : ""}
                </ItemDescription>
                {job.error_message ? (
                  <div className="text-destructive mt-2 text-sm">
                    {t.settings.nlp2sql.jobsError}: {job.error_message}
                  </div>
                ) : null}
              </ItemContent>
              <ItemActions>
                <JobStatusBadge status={job.status} t={t} />
              </ItemActions>
            </Item>
          ))}
        </div>
      )}
    </div>
  );
}
