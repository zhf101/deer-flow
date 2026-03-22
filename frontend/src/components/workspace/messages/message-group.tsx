import type { Message } from "@langchain/langgraph-sdk";
import {
  DatabaseIcon,
  BookOpenTextIcon,
  ChevronUp,
  FolderOpenIcon,
  GlobeIcon,
  LightbulbIcon,
  ListTodoIcon,
  MessageCircleQuestionMarkIcon,
  NotebookPenIcon,
  SearchIcon,
  SquareTerminalIcon,
  WrenchIcon,
} from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";

import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtSearchResult,
  ChainOfThoughtSearchResults,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import { CodeBlock } from "@/components/ai-elements/code-block";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { resolveArtifactURL } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import {
  extractReasoningContentFromMessage,
  findToolCallResult,
} from "@/core/messages/utils";
import { useRehypeSplitWordsIntoSpans } from "@/core/rehype";
import { extractTitleFromMarkdown } from "@/core/utils/markdown";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import { useArtifacts } from "../artifacts";
import { FlipDisplay } from "../flip-display";
import { Tooltip } from "../tooltip";

import { MarkdownContent } from "./markdown-content";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isRowArray(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every((item) => isRecord(item));
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "string") {
    return value;
  }
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  return JSON.stringify(value) ?? "—";
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function getNlp2SqlBucketLabel(
  bucket: string,
  t: ReturnType<typeof useI18n>["t"],
): string {
  switch (bucket) {
    case "example_sql":
      return t.toolCalls.nlp2sql.bucketExampleSql;
    case "glossary":
      return t.toolCalls.nlp2sql.bucketGlossary;
    case "join_hint":
      return t.toolCalls.nlp2sql.bucketJoinHint;
    case "filter_value":
      return t.toolCalls.nlp2sql.bucketFilterValue;
    case "schema_note":
      return t.toolCalls.nlp2sql.bucketSchemaNote;
    case "documentation":
      return t.toolCalls.nlp2sql.bucketDocumentation;
    case "historical_sql":
      return t.toolCalls.nlp2sql.bucketHistoricalSql;
    case "schema":
      return t.toolCalls.nlp2sql.bucketSchema;
    default:
      return bucket;
  }
}

function getNlp2SqlMatchSourceLabel(
  source: string,
  t: ReturnType<typeof useI18n>["t"],
): string {
  switch (source) {
    case "semantic":
      return t.toolCalls.nlp2sql.matchSourceSemantic;
    case "keyword":
      return t.toolCalls.nlp2sql.matchSourceKeyword;
    case "schema":
      return t.toolCalls.nlp2sql.matchSourceSchema;
    default:
      return source;
  }
}

function extractExportedArtifactPath(result: string): string | null {
  const match = /(\/mnt\/user-data\/outputs\/\S+)/.exec(result);
  return match?.[1] ?? null;
}

function renderNlp2SqlToolCall({
  id,
  name,
  result,
  threadId,
  t,
}: {
  id?: string;
  name: string;
  result?: unknown;
  threadId?: string;
  t: ReturnType<typeof useI18n>["t"];
}): ReactNode | null {
  if (name === "validate_sql" && isRecord(result)) {
    const warnings = toStringList(result.warnings);
    const errors = toStringList(result.errors);
    const normalizedSql =
      typeof result.normalized_sql === "string" ? result.normalized_sql : "";
    const ok = result.ok === true;
    const mode = typeof result.mode === "string" ? result.mode : null;

    return (
      <ChainOfThoughtStep
        key={id}
        label={
          ok
            ? t.toolCalls.nlp2sql.validationPassed
            : t.toolCalls.nlp2sql.validationFailed
        }
        icon={WrenchIcon}
      >
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant={ok ? "default" : "destructive"}>
              {ok
                ? t.toolCalls.nlp2sql.validationPassed
                : t.toolCalls.nlp2sql.validationFailed}
            </Badge>
            {mode ? <Badge variant="outline">{mode}</Badge> : null}
          </div>
          {normalizedSql ? (
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs font-medium">
                {t.toolCalls.nlp2sql.normalizedSql}
              </div>
              <CodeBlock
                className="mx-0 border-none px-0"
                code={normalizedSql}
                language="sql"
                showLineNumbers={false}
              />
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs font-medium">
                {t.toolCalls.nlp2sql.warnings}
              </div>
              <ul className="text-sm leading-6">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {errors.length > 0 ? (
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs font-medium">
                {t.toolCalls.nlp2sql.errors}
              </div>
              <ul className="text-sm leading-6">
                {errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "list_data_sources" && isRecord(result)) {
    const dataSources = Array.isArray(result.data_sources)
      ? result.data_sources.filter(isRecord)
      : [];

    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.availableDataSources}
        icon={DatabaseIcon}
      >
        <div className="mt-3 space-y-2">
          {dataSources.map((dataSource) => {
            const sourceId =
              typeof dataSource.id === "string" ? dataSource.id : "";
            const name =
              typeof dataSource.name === "string" ? dataSource.name : sourceId;
            const dbType =
              typeof dataSource.db_type === "string" ? dataSource.db_type : "";
            const host =
              typeof dataSource.host === "string" ? dataSource.host : "";
            const database =
              typeof dataSource.database === "string"
                ? dataSource.database
                : "";

            return (
              <div
                key={sourceId || name}
                className="rounded-md border px-3 py-2 text-sm"
              >
                <div className="font-medium">{name}</div>
                <div className="text-muted-foreground text-xs">
                  {sourceId}
                  {dbType ? ` · ${dbType}` : ""}
                  {host ? ` · ${host}` : ""}
                  {database ? ` · ${database}` : ""}
                </div>
              </div>
            );
          })}
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "use_data_source" && isRecord(result)) {
    const dataSourceId =
      typeof result.data_source_id === "string" ? result.data_source_id : "";
    const validationMode =
      typeof result.default_validation_mode === "string"
        ? result.default_validation_mode
        : "";

    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.usingDataSource}
        icon={DatabaseIcon}
      >
        <div className="mt-3 space-y-2 text-sm">
          <div className="font-medium">{dataSourceId}</div>
          {validationMode ? (
            <div className="text-muted-foreground">
              {t.toolCalls.nlp2sql.defaultValidationMode}: {validationMode}
            </div>
          ) : null}
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "get_current_data_source" && isRecord(result)) {
    const dataSource = isRecord(result.data_source) ? result.data_source : null;
    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.currentDataSource}
        icon={DatabaseIcon}
      >
        <div className="mt-3 text-sm">
          {dataSource ? (
            <>
              <div className="font-medium">
                {typeof dataSource.name === "string"
                  ? dataSource.name
                  : typeof dataSource.id === "string"
                    ? dataSource.id
                    : t.toolCalls.nlp2sql.currentDataSource}
              </div>
              <div className="text-muted-foreground text-xs">
                {typeof dataSource.id === "string" ? dataSource.id : ""}
                {typeof dataSource.db_type === "string"
                  ? ` · ${dataSource.db_type}`
                  : ""}
                {typeof dataSource.database === "string"
                  ? ` · ${dataSource.database}`
                  : ""}
              </div>
            </>
          ) : (
            <div className="text-muted-foreground">
              {t.toolCalls.nlp2sql.noDataSourceSelected}
            </div>
          )}
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "search_schema" && isRecord(result)) {
    const hits = Array.isArray(result.hits) ? result.hits.filter(isRecord) : [];

    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.schemaMatches}
        icon={SearchIcon}
      >
        <div className="mt-3 space-y-2">
          {hits.map((hit, index) => {
            const schemaName =
              typeof hit.schema_name === "string" ? hit.schema_name : "";
            const tableName =
              typeof hit.table_name === "string" ? hit.table_name : "";
            const columnName =
              typeof hit.column_name === "string" ? hit.column_name : "";
            const matchType =
              typeof hit.match_type === "string" ? hit.match_type : "";
            const score =
              typeof hit.score === "number" ? hit.score.toFixed(2) : "";
            const snippet = typeof hit.snippet === "string" ? hit.snippet : "";

            return (
              <div
                key={`${schemaName}.${tableName}.${columnName}.${index}`}
                className="rounded-md border px-3 py-2 text-sm"
              >
                <div className="font-medium">
                  {schemaName ? `${schemaName}.` : ""}
                  {tableName}
                  {columnName ? `.${columnName}` : ""}
                </div>
                <div className="text-muted-foreground text-xs">
                  {matchType
                    ? `${t.toolCalls.nlp2sql.matchType}: ${matchType}`
                    : ""}
                  {score ? ` · ${t.toolCalls.nlp2sql.score}: ${score}` : ""}
                </div>
                {snippet ? <div className="mt-1 text-xs">{snippet}</div> : null}
              </div>
            );
          })}
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "retrieve_knowledge_context" && isRecord(result)) {
    const buckets = Array.isArray(result.buckets)
      ? result.buckets.filter(isRecord)
      : [];
    const warnings = toStringList(result.warnings);
    const activeEmbeddingProfile =
      typeof result.active_embedding_profile_id === "string"
        ? result.active_embedding_profile_id
        : "";

    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.retrievalContext}
        icon={SearchIcon}
      >
        <div className="mt-3 space-y-4">
          <div className="flex flex-wrap gap-2">
            {activeEmbeddingProfile ? (
              <Badge variant="secondary">
                {t.toolCalls.nlp2sql.activeEmbeddingProfile}:{" "}
                {activeEmbeddingProfile}
              </Badge>
            ) : null}
            {buckets.map((bucket) => {
              const bucketName =
                typeof bucket.bucket === "string" ? bucket.bucket : "";
              const hits = Array.isArray(bucket.hits) ? bucket.hits : [];

              return (
                <Badge key={bucketName} variant="outline">
                  {getNlp2SqlBucketLabel(bucketName, t)}: {hits.length}
                </Badge>
              );
            })}
          </div>

          {warnings.length > 0 ? (
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs font-medium">
                {t.toolCalls.nlp2sql.retrievalWarnings}
              </div>
              <ul className="text-sm leading-6">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {buckets.length > 0 ? (
            buckets.map((bucket) => {
              const bucketName =
                typeof bucket.bucket === "string" ? bucket.bucket : "";
              const hits = Array.isArray(bucket.hits)
                ? bucket.hits.filter(isRecord)
                : [];

              return (
                <div key={bucketName} className="space-y-2">
                  <div className="text-muted-foreground text-xs font-medium">
                    {getNlp2SqlBucketLabel(bucketName, t)}
                  </div>
                  {hits.map((hit, index) => {
                    const title =
                      typeof hit.title === "string" ? hit.title : bucketName;
                    const snippet =
                      typeof hit.snippet === "string" ? hit.snippet : "";
                    const score =
                      typeof hit.score === "number"
                        ? hit.score.toFixed(2)
                        : null;
                    const matchSources = Array.isArray(hit.match_sources)
                      ? hit.match_sources.filter(
                          (item): item is string => typeof item === "string",
                        )
                      : [];
                    const sourceName =
                      typeof hit.source_name === "string" ? hit.source_name : "";
                    const sourceUri =
                      typeof hit.source_uri === "string" ? hit.source_uri : "";

                    return (
                      <div
                        key={`${bucketName}-${title}-${index}`}
                        className="space-y-2 rounded-md border px-3 py-2 text-sm"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="font-medium">{title}</div>
                          {score ? (
                            <Badge variant="outline">
                              {t.toolCalls.nlp2sql.score}: {score}
                            </Badge>
                          ) : null}
                        </div>

                        {matchSources.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {matchSources.map((source) => (
                              <Badge key={source} variant="secondary">
                                {getNlp2SqlMatchSourceLabel(source, t)}
                              </Badge>
                            ))}
                          </div>
                        ) : null}

                        {snippet ? (
                          <div className="text-muted-foreground text-xs leading-5">
                            {snippet}
                          </div>
                        ) : null}

                        {sourceName || sourceUri ? (
                          <div className="text-muted-foreground flex flex-wrap gap-3 text-xs">
                            {sourceName ? (
                              <span>
                                {t.toolCalls.nlp2sql.sourceName}: {sourceName}
                              </span>
                            ) : null}
                            {sourceUri ? (
                              isHttpUrl(sourceUri) ? (
                                <a
                                  href={sourceUri}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary underline underline-offset-4"
                                >
                                  {t.toolCalls.nlp2sql.sourceUri}
                                </a>
                              ) : (
                                <span>
                                  {t.toolCalls.nlp2sql.sourceUri}: {sourceUri}
                                </span>
                              )
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              );
            })
          ) : (
            <div className="text-muted-foreground text-sm">
              {t.settings.nlp2sql.retrievalPreviewEmpty}
            </div>
          )}
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "execute_sql" && isRecord(result)) {
    const sql = typeof result.sql === "string" ? result.sql : "";
    const allRows = isRowArray(result.rows) ? result.rows : [];
    const previewRows = allRows.slice(0, 10);
    const columns = isStringArray(result.columns)
      ? result.columns
      : previewRows[0]
        ? Object.keys(previewRows[0])
        : [];
    const rowCount =
      typeof result.row_count === "number" ? result.row_count : allRows.length;
    const fetchedRowCount =
      typeof result.fetched_row_count === "number"
        ? result.fetched_row_count
        : rowCount;
    const executionMs =
      typeof result.execution_ms === "number" ? result.execution_ms : null;
    const truncated = result.truncated === true;

    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.executeSql}
        icon={SquareTerminalIcon}
      >
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">
              {t.toolCalls.nlp2sql.rowCount}: {rowCount}
            </Badge>
            {truncated && fetchedRowCount > rowCount ? (
              <Badge variant="outline">
                {t.toolCalls.nlp2sql.fetchedRowCount}: {fetchedRowCount}
              </Badge>
            ) : null}
            {executionMs !== null ? (
              <Badge variant="outline">
                {t.toolCalls.nlp2sql.executionMs}: {executionMs} ms
              </Badge>
            ) : null}
            {truncated ? (
              <Badge variant="outline">{t.toolCalls.nlp2sql.truncated}</Badge>
            ) : null}
          </div>
          {truncated && fetchedRowCount > rowCount ? (
            <div className="text-muted-foreground text-xs">
              {t.toolCalls.nlp2sql.truncatedByRowCap(
                rowCount,
                fetchedRowCount,
              )}
            </div>
          ) : null}
          {sql ? (
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs font-medium">
                {t.toolCalls.nlp2sql.sql}
              </div>
              <CodeBlock
                className="mx-0 border-none px-0"
                code={sql}
                language="sql"
                showLineNumbers={false}
              />
            </div>
          ) : null}
          <div className="space-y-1">
            <div className="text-muted-foreground text-xs font-medium">
              {t.toolCalls.nlp2sql.resultPreview}
            </div>
            {previewRows.length > 0 && columns.length > 0 ? (
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full min-w-max text-left text-sm">
                  <thead className="bg-muted/60">
                    <tr>
                      {columns.map((column) => (
                        <th key={column} className="px-3 py-2 font-medium">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, index) => (
                      <tr key={index} className="border-t align-top">
                        {columns.map((column) => (
                          <td
                            key={`${index}-${column}`}
                            className="max-w-80 px-3 py-2 break-words whitespace-pre-wrap"
                          >
                            {formatCellValue(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-muted-foreground text-sm">
                {t.toolCalls.nlp2sql.noRows}
              </div>
            )}
            {allRows.length > previewRows.length ? (
              <div className="text-muted-foreground text-xs">
                {t.toolCalls.nlp2sql.previewLimited(
                  previewRows.length,
                  allRows.length,
                )}
              </div>
            ) : null}
          </div>
        </div>
      </ChainOfThoughtStep>
    );
  }

  if (name === "export_query_result" && typeof result === "string") {
    const artifactPath = extractExportedArtifactPath(result);
    const artifactUrl =
      artifactPath && threadId
        ? resolveArtifactURL(artifactPath, threadId)
        : null;

    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.nlp2sql.exportedFile}
        icon={FolderOpenIcon}
      >
        <div className="mt-3 space-y-2 text-sm">
          <div>{result}</div>
          {artifactPath && artifactUrl ? (
            <a
              href={artifactUrl}
              target="_blank"
              rel="noreferrer"
              className="text-primary inline-flex underline underline-offset-4"
            >
              {t.toolCalls.nlp2sql.openArtifact}
            </a>
          ) : null}
        </div>
      </ChainOfThoughtStep>
    );
  }

  return null;
}

export function MessageGroup({
  className,
  messages,
  isLoading = false,
}: {
  className?: string;
  messages: Message[];
  isLoading?: boolean;
}) {
  const { t } = useI18n();
  const [showAbove, setShowAbove] = useState(
    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true",
  );
  const [showLastThinking, setShowLastThinking] = useState(
    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true",
  );
  const steps = useMemo(() => convertToSteps(messages), [messages]);
  const lastToolCallStep = useMemo(() => {
    const filteredSteps = steps.filter((step) => step.type === "toolCall");
    return filteredSteps[filteredSteps.length - 1];
  }, [steps]);
  const aboveLastToolCallSteps = useMemo(() => {
    if (lastToolCallStep) {
      const index = steps.indexOf(lastToolCallStep);
      return steps.slice(0, index);
    }
    return [];
  }, [lastToolCallStep, steps]);
  const lastReasoningStep = useMemo(() => {
    if (lastToolCallStep) {
      const index = steps.indexOf(lastToolCallStep);
      return steps.slice(index + 1).find((step) => step.type === "reasoning");
    } else {
      const filteredSteps = steps.filter((step) => step.type === "reasoning");
      return filteredSteps[filteredSteps.length - 1];
    }
  }, [lastToolCallStep, steps]);
  const rehypePlugins = useRehypeSplitWordsIntoSpans(isLoading);
  return (
    <ChainOfThought
      className={cn("w-full gap-2 rounded-lg border p-0.5", className)}
      open={true}
    >
      {aboveLastToolCallSteps.length > 0 && (
        <Button
          key="above"
          className="w-full items-start justify-start text-left"
          variant="ghost"
          onClick={() => setShowAbove(!showAbove)}
        >
          <ChainOfThoughtStep
            label={
              <span className="opacity-60">
                {showAbove
                  ? t.toolCalls.lessSteps
                  : t.toolCalls.moreSteps(aboveLastToolCallSteps.length)}
              </span>
            }
            icon={
              <ChevronUp
                className={cn(
                  "size-4 opacity-60 transition-transform duration-200",
                  showAbove ? "rotate-180" : "",
                )}
              />
            }
          ></ChainOfThoughtStep>
        </Button>
      )}
      {lastToolCallStep && (
        <ChainOfThoughtContent className="px-4 pb-2">
          {showAbove &&
            aboveLastToolCallSteps.map((step) =>
              step.type === "reasoning" ? (
                <ChainOfThoughtStep
                  key={step.id}
                  label={
                    <MarkdownContent
                      content={step.reasoning ?? ""}
                      isLoading={isLoading}
                      rehypePlugins={rehypePlugins}
                    />
                  }
                ></ChainOfThoughtStep>
              ) : (
                <ToolCall key={step.id} {...step} isLoading={isLoading} />
              ),
            )}
          {lastToolCallStep && (
            <FlipDisplay uniqueKey={lastToolCallStep.id ?? ""}>
              <ToolCall
                key={lastToolCallStep.id}
                {...lastToolCallStep}
                isLast={true}
                isLoading={isLoading}
              />
            </FlipDisplay>
          )}
        </ChainOfThoughtContent>
      )}
      {lastReasoningStep && (
        <>
          <Button
            key={lastReasoningStep.id}
            className="w-full items-start justify-start text-left"
            variant="ghost"
            onClick={() => setShowLastThinking(!showLastThinking)}
          >
            <div className="flex w-full items-center justify-between">
              <ChainOfThoughtStep
                className="font-normal"
                label={t.common.thinking}
                icon={LightbulbIcon}
              ></ChainOfThoughtStep>
              <div>
                <ChevronUp
                  className={cn(
                    "text-muted-foreground size-4",
                    showLastThinking ? "" : "rotate-180",
                  )}
                />
              </div>
            </div>
          </Button>
          {showLastThinking && (
            <ChainOfThoughtContent className="px-4 pb-2">
              <ChainOfThoughtStep
                key={lastReasoningStep.id}
                label={
                  <MarkdownContent
                    content={lastReasoningStep.reasoning ?? ""}
                    isLoading={isLoading}
                    rehypePlugins={rehypePlugins}
                  />
                }
              ></ChainOfThoughtStep>
            </ChainOfThoughtContent>
          )}
        </>
      )}
    </ChainOfThought>
  );
}

function ToolCall({
  id,
  messageId,
  name,
  args,
  result,
  isLast = false,
  isLoading = false,
}: {
  id?: string;
  messageId?: string;
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  isLast?: boolean;
  isLoading?: boolean;
}) {
  const { t } = useI18n();
  const { thread_id } = useParams<{ thread_id: string }>();
  const { setOpen, autoOpen, autoSelect, selectedArtifact, select } =
    useArtifacts();
  const nlp2sqlStep = renderNlp2SqlToolCall({
    id,
    name,
    result,
    threadId: thread_id,
    t,
  });

  if (nlp2sqlStep) {
    return nlp2sqlStep;
  }

  if (name === "web_search") {
    let label: React.ReactNode = t.toolCalls.searchForRelatedInfo;
    if (typeof args.query === "string") {
      label = t.toolCalls.searchOnWebFor(args.query);
    }
    return (
      <ChainOfThoughtStep key={id} label={label} icon={SearchIcon}>
        {Array.isArray(result) && (
          <ChainOfThoughtSearchResults>
            {result.map((item) => (
              <ChainOfThoughtSearchResult key={item.url}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.title}
                </a>
              </ChainOfThoughtSearchResult>
            ))}
          </ChainOfThoughtSearchResults>
        )}
      </ChainOfThoughtStep>
    );
  } else if (name === "image_search") {
    let label: React.ReactNode = t.toolCalls.searchForRelatedImages;
    if (typeof args.query === "string") {
      label = t.toolCalls.searchForRelatedImagesFor(args.query);
    }
    const results = (
      result as {
        results: {
          source_url: string;
          thumbnail_url: string;
          image_url: string;
          title: string;
        }[];
      }
    )?.results;
    return (
      <ChainOfThoughtStep key={id} label={label} icon={SearchIcon}>
        {Array.isArray(results) && (
          <ChainOfThoughtSearchResults>
            {Array.isArray(results) &&
              results.map((item) => (
                <Tooltip key={item.image_url} content={item.title}>
                  <a
                    className="size-24 overflow-hidden rounded-lg object-cover"
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <div className="bg-accent size-24">
                      <img
                        className="size-full object-cover"
                        src={item.thumbnail_url}
                        alt={item.title}
                        width={100}
                        height={100}
                      />
                    </div>
                  </a>
                </Tooltip>
              ))}
          </ChainOfThoughtSearchResults>
        )}
      </ChainOfThoughtStep>
    );
  } else if (name === "web_fetch") {
    const url = (args as { url: string })?.url;
    let title = url;
    if (typeof result === "string") {
      const potentialTitle = extractTitleFromMarkdown(result);
      if (potentialTitle && potentialTitle.toLowerCase() !== "untitled") {
        title = potentialTitle;
      }
    }
    return (
      <ChainOfThoughtStep
        key={id}
        className="cursor-pointer"
        label={t.toolCalls.viewWebPage}
        icon={GlobeIcon}
        onClick={() => {
          window.open(url, "_blank");
        }}
      >
        <ChainOfThoughtSearchResult>
          {url && (
            <a href={url} target="_blank" rel="noreferrer">
              {title}
            </a>
          )}
        </ChainOfThoughtSearchResult>
      </ChainOfThoughtStep>
    );
  } else if (name === "ls") {
    let description: string | undefined = (args as { description: string })
      ?.description;
    if (!description) {
      description = t.toolCalls.listFolder;
    }
    const path: string | undefined = (args as { path: string })?.path;
    return (
      <ChainOfThoughtStep key={id} label={description} icon={FolderOpenIcon}>
        {path && (
          <ChainOfThoughtSearchResult className="cursor-pointer">
            {path}
          </ChainOfThoughtSearchResult>
        )}
      </ChainOfThoughtStep>
    );
  } else if (name === "read_file") {
    let description: string | undefined = (args as { description: string })
      ?.description;
    if (!description) {
      description = t.toolCalls.readFile;
    }
    const { path } = args as { path: string; content: string };
    return (
      <ChainOfThoughtStep key={id} label={description} icon={BookOpenTextIcon}>
        {path && (
          <ChainOfThoughtSearchResult className="cursor-pointer">
            {path}
          </ChainOfThoughtSearchResult>
        )}
      </ChainOfThoughtStep>
    );
  } else if (name === "write_file" || name === "str_replace") {
    let description: string | undefined = (args as { description: string })
      ?.description;
    if (!description) {
      description = t.toolCalls.writeFile;
    }
    const path: string | undefined = (args as { path: string })?.path;
    if (isLoading && isLast && autoOpen && autoSelect && path) {
      setTimeout(() => {
        const url = new URL(
          `write-file:${path}?message_id=${messageId}&tool_call_id=${id}`,
        ).toString();
        if (selectedArtifact === url) {
          return;
        }
        select(url, true);
        setOpen(true);
      }, 100);
    }

    return (
      <ChainOfThoughtStep
        key={id}
        className="cursor-pointer"
        label={description}
        icon={NotebookPenIcon}
        onClick={() => {
          select(
            new URL(
              `write-file:${path}?message_id=${messageId}&tool_call_id=${id}`,
            ).toString(),
          );
          setOpen(true);
        }}
      >
        {path && (
          <ChainOfThoughtSearchResult className="cursor-pointer">
            {path}
          </ChainOfThoughtSearchResult>
        )}
      </ChainOfThoughtStep>
    );
  } else if (name === "bash") {
    const description: string | undefined = (args as { description: string })
      ?.description;
    if (!description) {
      return t.toolCalls.executeCommand;
    }
    const command: string | undefined = (args as { command: string })?.command;
    return (
      <ChainOfThoughtStep
        key={id}
        label={description}
        icon={SquareTerminalIcon}
      >
        {command && (
          <CodeBlock
            className="mx-0 cursor-pointer border-none px-0"
            showLineNumbers={false}
            language="bash"
            code={command}
          />
        )}
      </ChainOfThoughtStep>
    );
  } else if (name === "ask_clarification") {
    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.needYourHelp}
        icon={MessageCircleQuestionMarkIcon}
      ></ChainOfThoughtStep>
    );
  } else if (name === "write_todos") {
    return (
      <ChainOfThoughtStep
        key={id}
        label={t.toolCalls.writeTodos}
        icon={ListTodoIcon}
      ></ChainOfThoughtStep>
    );
  } else {
    const description: string | undefined = (args as { description: string })
      ?.description;
    return (
      <ChainOfThoughtStep
        key={id}
        label={description ?? t.toolCalls.useTool(name)}
        icon={WrenchIcon}
      ></ChainOfThoughtStep>
    );
  }
}

interface GenericCoTStep<T extends string = string> {
  id?: string;
  messageId?: string;
  type: T;
}

interface CoTReasoningStep extends GenericCoTStep<"reasoning"> {
  reasoning: string | null;
}

interface CoTToolCallStep extends GenericCoTStep<"toolCall"> {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
}

type CoTStep = CoTReasoningStep | CoTToolCallStep;

function convertToSteps(messages: Message[]): CoTStep[] {
  const steps: CoTStep[] = [];
  for (const message of messages) {
    if (message.type === "ai") {
      const reasoning = extractReasoningContentFromMessage(message);
      if (reasoning) {
        const step: CoTReasoningStep = {
          id: message.id,
          messageId: message.id,
          type: "reasoning",
          reasoning: extractReasoningContentFromMessage(message),
        };
        steps.push(step);
      }
      for (const tool_call of message.tool_calls ?? []) {
        if (tool_call.name === "task") {
          continue;
        }
        const step: CoTToolCallStep = {
          id: tool_call.id,
          messageId: message.id,
          type: "toolCall",
          name: tool_call.name,
          args: tool_call.args,
        };
        const toolCallId = tool_call.id;
        if (toolCallId) {
          const toolCallResult = findToolCallResult(toolCallId, messages);
          if (toolCallResult) {
            try {
              const json = JSON.parse(toolCallResult);
              step.result = json;
            } catch {
              step.result = toolCallResult;
            }
          }
        }
        steps.push(step);
      }
    }
  }
  return steps;
}
