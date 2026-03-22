"use client";

import {
  ChevronRightIcon,
  Columns3Icon,
  DatabaseIcon,
  SaveIcon,
  Table2Icon,
  XIcon,
} from "lucide-react";
import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useDataSourceSchema,
  useUpsertSchemaComment,
  type SchemaColumn,
  type SchemaTable,
} from "@/core/nlp2sql";
import { cn } from "@/lib/utils";

type SelectedTableRef = {
  schemaName: string;
  tableName: string;
};

function tableKey(schemaName: string, tableName: string) {
  return `${schemaName}.${tableName}`;
}

function columnKey(schemaName: string, tableName: string, columnName: string) {
  return `${schemaName}.${tableName}.${columnName}`;
}

function normalizeComment(value: string | null | undefined) {
  return (value ?? "").trim();
}

function matchesSearch(
  searchTerm: string,
  schemaName: string,
  table: SchemaTable,
) {
  if (!searchTerm) {
    return true;
  }
  const haystacks = [
    schemaName,
    table.name,
    table.comment,
    table.source_comment,
    ...table.columns.flatMap((column) => [
      column.name,
      column.comment,
      column.source_comment,
      String(column.data_type ?? ""),
      String(column.column_type ?? ""),
    ]),
  ];
  return haystacks.some((value) => value.toLowerCase().includes(searchTerm));
}

export function Nlp2SqlSchemaPanel({
  dataSourceId,
  controlsDisabled,
}: {
  dataSourceId: string;
  controlsDisabled: boolean;
}) {
  const { t } = useI18n();
  const { schema, isLoading, error } = useDataSourceSchema(dataSourceId);
  const saveCommentMutation = useUpsertSchemaComment();

  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [selectedTable, setSelectedTable] = useState<SelectedTableRef | null>(
    null,
  );
  const [tableCommentDraft, setTableCommentDraft] = useState("");
  const [columnCommentDrafts, setColumnCommentDrafts] = useState<
    Record<string, string>
  >({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const filteredSchemas = useMemo(() => {
    if (!schema) {
      return [];
    }
    const searchTerm = deferredSearch.trim().toLowerCase();
    return schema.schemas
      .map((schemaItem) => ({
        ...schemaItem,
        tables: schemaItem.tables.filter((table) =>
          matchesSearch(searchTerm, schemaItem.name, table),
        ),
      }))
      .filter((schemaItem) => schemaItem.tables.length > 0);
  }, [deferredSearch, schema]);

  const selectedTableData = useMemo(() => {
    if (!schema || !selectedTable) {
      return null;
    }
    const schemaItem = schema.schemas.find(
      (item) => item.name === selectedTable.schemaName,
    );
    if (!schemaItem) {
      return null;
    }
    const table = schemaItem.tables.find(
      (item) => item.name === selectedTable.tableName,
    );
    return table ? { schemaName: schemaItem.name, table } : null;
  }, [schema, selectedTable]);

  useEffect(() => {
    if (!schema) {
      return;
    }
    const visibleFirstTable = filteredSchemas[0]?.tables[0];
    const visibleFirstSchema = filteredSchemas[0]?.name;
    const fallbackTable = schema.schemas[0]?.tables[0];
    const fallbackSchema = schema.schemas[0]?.name;
    const nextTable =
      (visibleFirstTable && visibleFirstSchema
        ? { schemaName: visibleFirstSchema, tableName: visibleFirstTable.name }
        : null) ??
      (fallbackTable && fallbackSchema
        ? { schemaName: fallbackSchema, tableName: fallbackTable.name }
        : null);

    if (selectedTableData) {
      return;
    }
    startTransition(() => {
      setSelectedTable(nextTable);
    });
  }, [filteredSchemas, schema, selectedTableData]);

  useEffect(() => {
    if (!selectedTableData) {
      setTableCommentDraft("");
      setColumnCommentDrafts({});
      return;
    }
    setTableCommentDraft(selectedTableData.table.user_comment ?? "");
    setColumnCommentDrafts(
      Object.fromEntries(
        selectedTableData.table.columns.map((column) => [
          column.name,
          column.user_comment ?? "",
        ]),
      ),
    );
  }, [selectedTableData]);

  async function handleSaveTableComment() {
    if (!selectedTableData) {
      return;
    }
    const key = tableKey(selectedTableData.schemaName, selectedTableData.table.name);
    setSavingKey(key);
    try {
      const result = await saveCommentMutation.mutateAsync({
        dataSourceId,
        request: {
          schema_name: selectedTableData.schemaName,
          table_name: selectedTableData.table.name,
          comment: tableCommentDraft,
        },
      });
      toast.success(result.message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingKey(null);
    }
  }

  async function handleSaveColumnComment(column: SchemaColumn) {
    if (!selectedTableData) {
      return;
    }
    const key = columnKey(
      selectedTableData.schemaName,
      selectedTableData.table.name,
      column.name,
    );
    setSavingKey(key);
    try {
      const result = await saveCommentMutation.mutateAsync({
        dataSourceId,
        request: {
          schema_name: selectedTableData.schemaName,
          table_name: selectedTableData.table.name,
          column_name: column.name,
          comment: columnCommentDrafts[column.name] ?? "",
        },
      });
      toast.success(result.message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingKey(null);
    }
  }

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">{t.common.loading}</div>;
  }

  if (error) {
    return <div className="text-destructive text-sm">{error.message}</div>;
  }

  if (!schema || schema.schemas.length === 0) {
    return (
      <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
        {t.settings.nlp2sql.schemaEmptyDescription}
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
      <section className="space-y-3">
        <div>
          <div className="text-sm font-medium">
            {t.settings.nlp2sql.schemaExplorerTitle}
          </div>
          <div className="text-muted-foreground text-sm">
            {t.settings.nlp2sql.schemaExplorerDescription}
          </div>
        </div>

        <Input
          value={search}
          placeholder={t.settings.nlp2sql.schemaSearchPlaceholder}
          disabled={controlsDisabled}
          onChange={(e) => setSearch(e.target.value)}
        />

        <div className="space-y-3">
          {filteredSchemas.length === 0 ? (
            <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
              {t.settings.nlp2sql.schemaSearchEmpty}
            </div>
          ) : (
            filteredSchemas.map((schemaItem) => (
              <Collapsible key={schemaItem.name} defaultOpen>
                <div className="rounded-lg border">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                    >
                      <div className="flex items-center gap-2">
                        <DatabaseIcon className="text-muted-foreground size-4" />
                        <div>
                          <div className="text-sm font-medium">{schemaItem.name}</div>
                          <div className="text-muted-foreground text-xs">
                            {schemaItem.tables.length}{" "}
                            {t.settings.nlp2sql.schemaTableCount}
                          </div>
                        </div>
                      </div>
                      <ChevronRightIcon className="text-muted-foreground size-4 transition group-data-[state=open]:rotate-90" />
                    </button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="flex flex-col gap-2 border-t p-2">
                      {schemaItem.tables.map((table) => {
                        const currentKey = tableKey(schemaItem.name, table.name);
                        const selected = currentKey ===
                          (selectedTable
                            ? tableKey(selectedTable.schemaName, selectedTable.tableName)
                            : "");
                        const annotatedColumnCount = table.columns.filter((column) =>
                          normalizeComment(column.user_comment).length > 0,
                        ).length;
                        return (
                          <button
                            type="button"
                            key={currentKey}
                            className={cn(
                              "rounded-md border px-3 py-3 text-left transition",
                              selected
                                ? "border-primary bg-primary/5"
                                : "hover:bg-muted/60 border-transparent",
                            )}
                            onClick={() =>
                              startTransition(() =>
                                setSelectedTable({
                                  schemaName: schemaItem.name,
                                  tableName: table.name,
                                }),
                              )
                            }
                          >
                            <div className="flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  <Table2Icon className="text-muted-foreground size-4" />
                                  <span className="truncate text-sm font-medium">
                                    {table.name}
                                  </span>
                                </div>
                                <div className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                                  {table.comment || t.settings.nlp2sql.schemaNoComment}
                                </div>
                              </div>
                              <div className="flex flex-col items-end gap-1">
                                {normalizeComment(table.user_comment).length > 0 ? (
                                  <Badge variant="secondary">
                                    {t.settings.nlp2sql.schemaUserCommentBadge}
                                  </Badge>
                                ) : null}
                                {annotatedColumnCount > 0 ? (
                                  <Badge variant="outline">
                                    {annotatedColumnCount}{" "}
                                    {t.settings.nlp2sql.schemaColumnCommentCount}
                                  </Badge>
                                ) : null}
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            ))
          )}
        </div>
      </section>

      <section className="space-y-4 rounded-lg border p-4">
        {selectedTableData ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{selectedTableData.schemaName}</Badge>
              <span className="text-sm font-medium">{selectedTableData.table.name}</span>
              <Badge variant="secondary">
                {selectedTableData.table.columns.length}{" "}
                {t.settings.nlp2sql.schemaColumnsLabel}
              </Badge>
            </div>

            <div className="space-y-3 rounded-lg border p-4">
              <div className="flex items-center gap-2">
                <Table2Icon className="text-muted-foreground size-4" />
                <div className="text-sm font-medium">
                  {t.settings.nlp2sql.schemaTableCommentTitle}
                </div>
              </div>
              <CommentPreview
                label={t.settings.nlp2sql.schemaDatabaseCommentLabel}
                value={selectedTableData.table.source_comment}
              />
              <Field label={t.settings.nlp2sql.schemaUserCommentLabel}>
                <Textarea
                  value={tableCommentDraft}
                  disabled={controlsDisabled || saveCommentMutation.isPending}
                  placeholder={t.settings.nlp2sql.schemaTableCommentPlaceholder}
                  onChange={(e) => setTableCommentDraft(e.target.value)}
                />
              </Field>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  disabled={
                    controlsDisabled ||
                    saveCommentMutation.isPending ||
                    normalizeComment(tableCommentDraft) ===
                      normalizeComment(selectedTableData.table.user_comment)
                  }
                  onClick={handleSaveTableComment}
                >
                  <SaveIcon className="size-4" />
                  {savingKey ===
                  tableKey(
                    selectedTableData.schemaName,
                    selectedTableData.table.name,
                  )
                    ? t.common.loading
                    : t.common.save}
                </Button>
                <Button
                  variant="outline"
                  disabled={
                    controlsDisabled ||
                    saveCommentMutation.isPending ||
                    normalizeComment(selectedTableData.table.user_comment).length ===
                      0
                  }
                  onClick={() => setTableCommentDraft("")}
                >
                  <XIcon className="size-4" />
                  {t.settings.nlp2sql.schemaClearComment}
                </Button>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Columns3Icon className="text-muted-foreground size-4" />
                <div className="text-sm font-medium">
                  {t.settings.nlp2sql.schemaColumnsTitle}
                </div>
              </div>
              {selectedTableData.table.columns.map((column) => {
                const currentKey = columnKey(
                  selectedTableData.schemaName,
                  selectedTableData.table.name,
                  column.name,
                );
                const draftValue = columnCommentDrafts[column.name] ?? "";
                return (
                  <div key={currentKey} className="space-y-3 rounded-lg border p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{column.name}</span>
                      {column.column_type || column.data_type ? (
                        <Badge variant="outline">
                          {column.column_type ?? column.data_type}
                        </Badge>
                      ) : null}
                      {column.nullable === false ? (
                        <Badge variant="secondary">
                          {t.settings.nlp2sql.schemaNotNullBadge}
                        </Badge>
                      ) : null}
                      {normalizeComment(column.user_comment).length > 0 ? (
                        <Badge variant="secondary">
                          {t.settings.nlp2sql.schemaUserCommentBadge}
                        </Badge>
                      ) : null}
                    </div>
                    <CommentPreview
                      label={t.settings.nlp2sql.schemaEffectiveCommentLabel}
                      value={column.comment}
                    />
                    <CommentPreview
                      label={t.settings.nlp2sql.schemaDatabaseCommentLabel}
                      value={column.source_comment}
                    />
                    <Field label={t.settings.nlp2sql.schemaUserCommentLabel}>
                      <Textarea
                        value={draftValue}
                        disabled={controlsDisabled || saveCommentMutation.isPending}
                        placeholder={t.settings.nlp2sql.schemaColumnCommentPlaceholder}
                        onChange={(e) =>
                          setColumnCommentDrafts((current) => ({
                            ...current,
                            [column.name]: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        size="sm"
                        disabled={
                          controlsDisabled ||
                          saveCommentMutation.isPending ||
                          normalizeComment(draftValue) ===
                            normalizeComment(column.user_comment)
                        }
                        onClick={() => void handleSaveColumnComment(column)}
                      >
                        <SaveIcon className="size-4" />
                        {savingKey === currentKey ? t.common.loading : t.common.save}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={
                          controlsDisabled ||
                          saveCommentMutation.isPending ||
                          normalizeComment(column.user_comment).length === 0
                        }
                        onClick={() =>
                          setColumnCommentDrafts((current) => ({
                            ...current,
                            [column.name]: "",
                          }))
                        }
                      >
                        <XIcon className="size-4" />
                        {t.settings.nlp2sql.schemaClearComment}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
            {t.settings.nlp2sql.schemaSelectTableHint}
          </div>
        )}
      </section>
    </div>
  );
}

function CommentPreview({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground text-xs font-medium">{label}</div>
      <div className="bg-muted/50 rounded-md px-3 py-2 text-sm">
        {normalizeComment(value) || "-"}
      </div>
    </div>
  );
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
