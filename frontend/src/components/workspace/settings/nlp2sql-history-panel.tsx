"use client";

import { DatabaseIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useDeleteKnowledgeItem,
  useImportHistoricalSql,
  useKnowledgeItems,
} from "@/core/nlp2sql";

function HistoryStatusBadge({
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

export function Nlp2SqlHistoryPanel({
  dataSourceId,
  controlsDisabled,
}: {
  dataSourceId: string;
  controlsDisabled: boolean;
}) {
  const { t } = useI18n();
  const [sourceName, setSourceName] = useState("historical-sql-import");
  const [sqlText, setSqlText] = useState("");

  const { knowledgeItems, isLoading, error } = useKnowledgeItems(dataSourceId, {
    itemType: "historical_sql",
  });
  const importMutation = useImportHistoricalSql();
  const deleteMutation = useDeleteKnowledgeItem();

  const busy = importMutation.isPending || deleteMutation.isPending;

  async function handleImport() {
    if (!sqlText.trim()) {
      return;
    }
    try {
      await importMutation.mutateAsync({
        dataSourceId,
        request: {
          sql_text: sqlText.trim(),
          source_name: sourceName.trim() || null,
        },
      });
      setSqlText("");
      toast.success(t.settings.nlp2sql.historyImportSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(message);
    }
  }

  async function handleDelete(itemId: string) {
    if (!window.confirm(t.settings.nlp2sql.knowledgeDeleteConfirm)) {
      return;
    }
    try {
      await deleteMutation.mutateAsync({
        dataSourceId,
        itemId,
      });
      toast.success(t.settings.nlp2sql.knowledgeDeleteSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border p-4">
        <div className="text-sm font-medium">
          {t.settings.nlp2sql.historyImportTitle}
        </div>
        <div className="mt-4 grid gap-4">
          <label className="flex flex-col gap-2 text-sm">
            <span className="font-medium">
              {t.settings.nlp2sql.historyImportSourceLabel}
            </span>
            <Input
              value={sourceName}
              disabled={controlsDisabled || busy}
              onChange={(event) => setSourceName(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            <span className="font-medium">
              {t.settings.nlp2sql.historyImportContentLabel}
            </span>
            <Textarea
              value={sqlText}
              disabled={controlsDisabled || busy}
              placeholder={t.settings.nlp2sql.historyImportPlaceholder}
              onChange={(event) => setSqlText(event.target.value)}
            />
          </label>
          <div>
            <Button
              disabled={controlsDisabled || busy || sqlText.trim().length === 0}
              onClick={handleImport}
            >
              {t.settings.nlp2sql.historyImportAction}
            </Button>
          </div>
        </div>
      </div>

      <section className="space-y-3">
        <div>
          <div className="text-sm font-medium">
            {t.settings.nlp2sql.historyListTitle}
          </div>
          <div className="text-muted-foreground text-sm">
            {knowledgeItems.length === 0
              ? t.settings.nlp2sql.historyEmptyDescription
              : `${knowledgeItems.length} ${t.settings.nlp2sql.historyListSuffix}`}
          </div>
        </div>

        {isLoading ? (
          <div className="text-muted-foreground text-sm">{t.common.loading}</div>
        ) : error ? (
          <div className="text-destructive text-sm">{error.message}</div>
        ) : knowledgeItems.length === 0 ? (
          <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
            {t.settings.nlp2sql.historyEmptyTitle}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {knowledgeItems.map((item) => (
              <Item key={item.id} variant="outline">
                <ItemContent>
                  <ItemTitle>
                    <DatabaseIcon className="size-4" />
                    {item.title}
                  </ItemTitle>
                  <ItemDescription>
                    {item.source_name ?? "historical-sql-import"}
                  </ItemDescription>
                  <pre className="bg-muted/40 mt-2 overflow-x-auto rounded-md p-3 text-xs whitespace-pre-wrap">
                    {item.content}
                  </pre>
                </ItemContent>
                <ItemActions>
                  <HistoryStatusBadge status={item.index_status} />
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={controlsDisabled || busy}
                    onClick={() => handleDelete(item.id)}
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
