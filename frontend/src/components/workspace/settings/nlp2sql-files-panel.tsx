"use client";

import { FileTextIcon, UploadIcon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { useI18n } from "@/core/i18n/hooks";
import {
  useDeleteKnowledgeFile,
  useKnowledgeFiles,
  useUploadKnowledgeFiles,
} from "@/core/nlp2sql";

function formatBytes(value: number | null | undefined): string {
  if (!value || value < 1024) {
    return `${value ?? 0} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function FileStatusBadge({
  status,
}: {
  status: "pending" | "ready" | "failed";
}) {
  if (status === "ready") {
    return <Badge variant="default">ready</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">failed</Badge>;
  }
  return <Badge variant="outline">pending</Badge>;
}

export function Nlp2SqlFilesPanel({
  dataSourceId,
  controlsDisabled,
}: {
  dataSourceId: string;
  controlsDisabled: boolean;
}) {
  const { t } = useI18n();
  const inputId = useId();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  const { knowledgeFiles, isLoading, error } = useKnowledgeFiles(dataSourceId);
  const uploadMutation = useUploadKnowledgeFiles();
  const deleteMutation = useDeleteKnowledgeFile();

  const busy = uploadMutation.isPending || deleteMutation.isPending;

  async function handleUpload() {
    if (selectedFiles.length === 0) {
      return;
    }
    try {
      await uploadMutation.mutateAsync({
        dataSourceId,
        files: selectedFiles,
      });
      setSelectedFiles([]);
      const input = document.getElementById(inputId) as HTMLInputElement | null;
      if (input) {
        input.value = "";
      }
      toast.success(t.settings.nlp2sql.filesUploadSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(message);
    }
  }

  async function handleDelete(fileId: string) {
    if (!window.confirm(t.settings.nlp2sql.filesDeleteConfirm)) {
      return;
    }
    try {
      await deleteMutation.mutateAsync({
        dataSourceId,
        fileId,
      });
      toast.success(t.settings.nlp2sql.filesDeleteSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border p-4">
        <div className="text-sm font-medium">
          {t.settings.nlp2sql.filesUpload}
        </div>
        <div className="text-muted-foreground mt-1 text-sm">
          {t.settings.nlp2sql.filesUploadHint}
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input
            id={inputId}
            type="file"
            multiple
            disabled={controlsDisabled || busy}
            onChange={(event) =>
              setSelectedFiles(Array.from(event.target.files ?? []))
            }
          />
          <Button
            disabled={
              controlsDisabled || busy || selectedFiles.length === 0
            }
            onClick={handleUpload}
          >
            <UploadIcon className="size-4" />
            {t.settings.nlp2sql.filesUpload}
          </Button>
        </div>
        {selectedFiles.length > 0 ? (
          <div className="text-muted-foreground mt-3 text-sm">
            {selectedFiles.map((file) => file.name).join(", ")}
          </div>
        ) : null}
      </div>

      <section className="space-y-3">
        <div>
          <div className="text-sm font-medium">
            {t.settings.nlp2sql.filesListTitle}
          </div>
          <div className="text-muted-foreground text-sm">
            {knowledgeFiles.length === 0
              ? t.settings.nlp2sql.filesEmptyDescription
              : `${knowledgeFiles.length} ${t.settings.nlp2sql.filesListSuffix}`}
          </div>
        </div>

        {isLoading ? (
          <div className="text-muted-foreground text-sm">{t.common.loading}</div>
        ) : error ? (
          <div className="text-destructive text-sm">{error.message}</div>
        ) : knowledgeFiles.length === 0 ? (
          <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
            {t.settings.nlp2sql.filesEmptyTitle}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {knowledgeFiles.map((file) => (
              <Item key={file.id} variant="outline">
                <ItemContent>
                  <ItemTitle>
                    <FileTextIcon className="size-4" />
                    {file.file_name}
                  </ItemTitle>
                  <ItemDescription>
                    {t.settings.nlp2sql.filesSize}: {formatBytes(file.size_bytes)}
                    {" · "}
                    {t.settings.nlp2sql.filesContentLength}: {file.content_length}
                    {file.mime_type
                      ? ` · ${t.settings.nlp2sql.filesMimeType}: ${file.mime_type}`
                      : ""}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  <FileStatusBadge status={file.index_status} />
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={controlsDisabled || busy}
                    onClick={() => handleDelete(file.id)}
                  >
                    {t.common.delete}
                  </Button>
                </ItemActions>
              </Item>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
