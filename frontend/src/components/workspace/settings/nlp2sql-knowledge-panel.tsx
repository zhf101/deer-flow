"use client";

import { PlusIcon, SparklesIcon } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useCreateKnowledgeItem,
  useDeleteKnowledgeItem,
  useKnowledgeItems,
  useRetrievalPreview,
  useUpdateKnowledgeItem,
  type CreateKnowledgeItemRequest,
  type KnowledgeItem,
  type KnowledgeItemType,
} from "@/core/nlp2sql";
import { cn } from "@/lib/utils";

const NEW_KNOWLEDGE_ID = "__new_knowledge__";
const KNOWLEDGE_TYPES: KnowledgeItemType[] = [
  "documentation",
  "example_sql",
  "glossary",
  "join_hint",
  "filter_value",
  "schema_note",
];

type KnowledgeDraft = CreateKnowledgeItemRequest;

function createEmptyKnowledgeDraft(): KnowledgeDraft {
  return {
    item_type: "documentation",
    title: "",
    content: "",
    question: "",
    sql: "",
    source_name: "",
    source_uri: "",
    metadata: {},
  };
}

function toKnowledgeDraft(item: KnowledgeItem): KnowledgeDraft {
  return {
    item_type: item.item_type,
    title: item.title,
    content: item.content,
    question: item.question ?? "",
    sql: item.sql ?? "",
    source_name: item.source_name ?? "",
    source_uri: item.source_uri ?? "",
    metadata: item.metadata ?? {},
  };
}

function emptyToNull(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : null;
}

export function Nlp2SqlKnowledgePanel({
  dataSourceId,
  controlsDisabled,
}: {
  dataSourceId: string;
  controlsDisabled: boolean;
}) {
  const { t } = useI18n();
  const [selectedItemId, setSelectedItemId] = useState<string>(NEW_KNOWLEDGE_ID);
  const [filterType, setFilterType] = useState<KnowledgeItemType | "all">("all");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<KnowledgeDraft>(createEmptyKnowledgeDraft());
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [previewQuery, setPreviewQuery] = useState("");

  const { knowledgeItems, isLoading, error } = useKnowledgeItems(dataSourceId, {
    itemType: filterType === "all" ? "" : filterType,
    query: search,
  });
  const createMutation = useCreateKnowledgeItem();
  const updateMutation = useUpdateKnowledgeItem();
  const deleteMutation = useDeleteKnowledgeItem();
  const previewMutation = useRetrievalPreview();

  const selectedItem = useMemo(
    () => knowledgeItems.find((item) => item.id === selectedItemId) ?? null,
    [knowledgeItems, selectedItemId],
  );
  const isExisting = selectedItem !== null;

  useEffect(() => {
    if (knowledgeItems.length === 0) {
      setSelectedItemId(NEW_KNOWLEDGE_ID);
      return;
    }
    if (
      selectedItemId !== NEW_KNOWLEDGE_ID &&
      !knowledgeItems.some((item) => item.id === selectedItemId)
    ) {
      setSelectedItemId(knowledgeItems[0]!.id);
    }
  }, [knowledgeItems, selectedItemId]);

  useEffect(() => {
    if (selectedItem) {
      setDraft(toKnowledgeDraft(selectedItem));
      setStatusMessage(null);
      return;
    }
    if (selectedItemId === NEW_KNOWLEDGE_ID) {
      setDraft(createEmptyKnowledgeDraft());
      setStatusMessage(null);
    }
  }, [selectedItem, selectedItemId]);

  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending;
  const isExampleSql = draft.item_type === "example_sql";

  async function handleSave() {
    try {
      const payload: CreateKnowledgeItemRequest = {
        item_type: draft.item_type,
        title: draft.title?.trim() ?? "",
        content: draft.content?.trim() ?? "",
        question: emptyToNull(draft.question),
        sql: emptyToNull(draft.sql),
        source_name: emptyToNull(draft.source_name),
        source_uri: emptyToNull(draft.source_uri),
        metadata: draft.metadata ?? {},
      };
      if (isExisting) {
        await updateMutation.mutateAsync({
          dataSourceId,
          itemId: selectedItem.id,
          request: payload,
        });
        setStatusMessage(t.settings.nlp2sql.knowledgeUpdateSuccess);
        toast.success(t.settings.nlp2sql.knowledgeUpdateSuccess);
      } else {
        const result = await createMutation.mutateAsync({
          dataSourceId,
          request: payload,
        });
        setSelectedItemId(result.id);
        setStatusMessage(t.settings.nlp2sql.knowledgeCreateSuccess);
        toast.success(t.settings.nlp2sql.knowledgeCreateSuccess);
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handleDelete() {
    if (!selectedItem) {
      return;
    }
    if (!window.confirm(t.settings.nlp2sql.knowledgeDeleteConfirm)) {
      return;
    }
    try {
      await deleteMutation.mutateAsync({
        dataSourceId,
        itemId: selectedItem.id,
      });
      setSelectedItemId(knowledgeItems[0]?.id ?? NEW_KNOWLEDGE_ID);
      setStatusMessage(t.settings.nlp2sql.knowledgeDeleteSuccess);
      toast.success(t.settings.nlp2sql.knowledgeDeleteSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handlePreview() {
    try {
      await previewMutation.mutateAsync({
        dataSourceId,
        request: {
          query: previewQuery.trim(),
          limit_per_bucket: 3,
        },
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(message);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-sm font-medium">
              {t.settings.nlp2sql.knowledgeListTitle}
            </div>
            <div className="text-muted-foreground text-sm">
              {knowledgeItems.length === 0
                ? t.settings.nlp2sql.knowledgeEmptyDescription
                : `${knowledgeItems.length} ${t.settings.nlp2sql.knowledgeListSuffix}`}
            </div>
          </div>
          <Button
            size="sm"
            disabled={controlsDisabled}
            onClick={() => setSelectedItemId(NEW_KNOWLEDGE_ID)}
          >
            <PlusIcon className="size-4" />
            {t.settings.nlp2sql.knowledgeNewItem}
          </Button>
        </div>

        <div className="space-y-2">
          <Input
            value={search}
            placeholder={t.settings.nlp2sql.knowledgeSearchPlaceholder}
            disabled={controlsDisabled}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            value={filterType}
            onValueChange={(value) =>
              setFilterType(value as KnowledgeItemType | "all")
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                {t.settings.nlp2sql.knowledgeFilterAll}
              </SelectItem>
              {KNOWLEDGE_TYPES.map((itemType) => (
                <SelectItem key={itemType} value={itemType}>
                  {itemType}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-3">
          {isLoading ? (
            <div className="text-muted-foreground text-sm">
              {t.common.loading}
            </div>
          ) : error ? (
            <div className="text-destructive text-sm">{error.message}</div>
          ) : knowledgeItems.length === 0 ? (
            <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
              {t.settings.nlp2sql.knowledgeEmptyTitle}
            </div>
          ) : (
            knowledgeItems.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => setSelectedItemId(item.id)}
                className="text-left"
              >
                <Item
                  variant="outline"
                  className={cn(
                    selectedItemId === item.id &&
                      "border-primary ring-primary/20 ring-2",
                  )}
                >
                  <ItemContent>
                    <ItemTitle>{item.title}</ItemTitle>
                    <ItemDescription>
                      {item.item_type} · {item.index_status}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <KnowledgeStatusBadge status={item.index_status} />
                  </ItemActions>
                </Item>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="space-y-4 rounded-lg border p-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <SparklesIcon className="size-4" />
          {isExisting
            ? t.settings.nlp2sql.knowledgeEditorEdit
            : t.settings.nlp2sql.knowledgeEditorNew}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t.settings.nlp2sql.knowledgeTypeLabel}>
            <Select
              value={draft.item_type}
              onValueChange={(value) =>
                setDraft((current) => ({
                  ...current,
                  item_type: value as KnowledgeItemType,
                }))
              }
              disabled={controlsDisabled || isExisting}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KNOWLEDGE_TYPES.map((itemType) => (
                  <SelectItem key={itemType} value={itemType}>
                    {itemType}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label={t.settings.nlp2sql.knowledgeTitleLabel}>
            <Input
              value={draft.title ?? ""}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({ ...current, title: e.target.value }))
              }
            />
          </Field>
          <Field label={t.settings.nlp2sql.knowledgeSourceNameLabel}>
            <Input
              value={draft.source_name ?? ""}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  source_name: e.target.value,
                }))
              }
            />
          </Field>
          <Field label={t.settings.nlp2sql.knowledgeSourceUriLabel}>
            <Input
              value={draft.source_uri ?? ""}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  source_uri: e.target.value,
                }))
              }
            />
          </Field>
        </div>

        {isExampleSql ? (
          <div className="grid gap-4">
            <Field label={t.settings.nlp2sql.knowledgeQuestionLabel}>
              <Textarea
                value={draft.question ?? ""}
                disabled={controlsDisabled}
                onChange={(e) =>
                  setDraft((current) => ({
                    ...current,
                    question: e.target.value,
                  }))
                }
              />
            </Field>
            <Field label={t.settings.nlp2sql.knowledgeSqlLabel}>
              <Textarea
                value={draft.sql ?? ""}
                disabled={controlsDisabled}
                onChange={(e) =>
                  setDraft((current) => ({ ...current, sql: e.target.value }))
                }
              />
            </Field>
          </div>
        ) : (
          <Field label={t.settings.nlp2sql.knowledgeContentLabel}>
            <Textarea
              value={draft.content ?? ""}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  content: e.target.value,
                }))
              }
            />
          </Field>
        )}

        {statusMessage ? (
          <div className="bg-muted rounded-md px-3 py-2 text-sm">
            {statusMessage}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={controlsDisabled || busy} onClick={handleSave}>
            {isExisting ? t.common.save : t.common.create}
          </Button>
          {isExisting ? (
            <Button
              variant="outline"
              disabled={controlsDisabled || busy}
              onClick={handleDelete}
            >
              {t.common.delete}
            </Button>
          ) : null}
        </div>

        <div className="space-y-3 border-t pt-4">
          <div className="text-sm font-medium">
            {t.settings.nlp2sql.retrievalPreviewTitle}
          </div>
          <div className="flex gap-2">
            <Input
              value={previewQuery}
              placeholder={t.settings.nlp2sql.retrievalPreviewPlaceholder}
              disabled={controlsDisabled}
              onChange={(e) => setPreviewQuery(e.target.value)}
            />
            <Button
              variant="outline"
              disabled={
                controlsDisabled ||
                previewMutation.isPending ||
                previewQuery.trim().length === 0
              }
              onClick={handlePreview}
            >
              {t.common.search}
            </Button>
          </div>

          {previewMutation.data ? (
            <div className="space-y-3">
              {previewMutation.data.warnings.length > 0 ? (
                <div className="rounded-md border border-amber-300/60 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  {previewMutation.data.warnings.join(" ")}
                </div>
              ) : null}
              {previewMutation.data.buckets.length === 0 ? (
                <div className="text-muted-foreground text-sm">
                  {t.settings.nlp2sql.retrievalPreviewEmpty}
                </div>
              ) : (
                previewMutation.data.buckets.map((bucket) => (
                  <div key={bucket.bucket} className="space-y-2">
                    <div className="text-muted-foreground text-xs font-medium uppercase">
                      {bucket.bucket}
                    </div>
                    {bucket.hits.map((hit) => (
                      <div
                        key={`${bucket.bucket}-${hit.chunk_id ?? hit.item_id ?? hit.title}`}
                        className="rounded-md border px-3 py-2 text-sm"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{hit.title}</span>
                          <Badge variant="outline">
                            {hit.score.toFixed(2)}
                          </Badge>
                          <Badge variant="secondary">
                            {hit.match_sources.join(" + ")}
                          </Badge>
                        </div>
                        <div className="text-muted-foreground mt-1 text-xs">
                          {hit.source_name ?? hit.table_name ?? ""}
                        </div>
                        <div className="mt-2 text-sm">{hit.snippet}</div>
                      </div>
                    ))}
                  </div>
                ))
              )}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function KnowledgeStatusBadge({
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

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-2 text-sm">
      <span className="font-medium">{label}</span>
      {children}
    </label>
  );
}
