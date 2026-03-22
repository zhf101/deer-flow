"use client";

import { DatabaseIcon, PlusIcon } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

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
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useClearSchemaCache,
  useCreateDataSource,
  useDataSources,
  useDeleteDataSource,
  useTestDataSource,
  useUpdateDataSource,
  type DataSourceConfig,
  type DatabaseType,
  type ValidationMode,
} from "@/core/nlp2sql";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import { Nlp2SqlEmbeddingPanel } from "./nlp2sql-embedding-panel";
import { Nlp2SqlFilesPanel } from "./nlp2sql-files-panel";
import { Nlp2SqlHistoryPanel } from "./nlp2sql-history-panel";
import { Nlp2SqlJobsPanel } from "./nlp2sql-jobs-panel";
import { Nlp2SqlKnowledgePanel } from "./nlp2sql-knowledge-panel";
import { Nlp2SqlSchemaPanel } from "./nlp2sql-schema-panel";
import { SettingsSection } from "./settings-section";

const NEW_SOURCE_ID = "__new__";
const DEFAULT_PORTS: Record<DatabaseType, number> = {
  mysql: 3306,
  postgres: 5432,
  oracle: 1521,
  dm: 5236,
  kingbase: 54321,
  gaussdb: 8000,
  opengauss: 5432,
  oceanbase: 2881,
  tidb: 4000,
  polardb: 3306,
  goldendb: 3306,
};

function createEmptyDataSource(): DataSourceConfig {
  return {
    id: "",
    name: "",
    db_type: "mysql",
    host: "",
    port: 3306,
    database: "",
    username: "",
    password_env: "",
    service_name: null,
    sid: null,
    oracle_client_path: null,
    readonly: true,
    enabled: true,
    description: "",
    schema_whitelist: null,
    table_whitelist: null,
    connect_timeout_seconds: 10,
    query_timeout_seconds: 60,
    max_rows: 200,
    default_validation_mode: "relaxed",
  };
}

function formatList(values: string[] | null) {
  return values?.join(", ") ?? "";
}

function parseList(value: string): string[] | null {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? items : null;
}

function emptyToNull(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : null;
}

export function Nlp2SqlSettingsPage() {
  const { t } = useI18n();
  const { dataSources, isLoading, error } = useDataSources(false);
  const createMutation = useCreateDataSource();
  const updateMutation = useUpdateDataSource();
  const deleteMutation = useDeleteDataSource();
  const testMutation = useTestDataSource();
  const clearSchemaCacheMutation = useClearSchemaCache();

  const [selectedId, setSelectedId] = useState<string>("");
  const [draft, setDraft] = useState<DataSourceConfig>(createEmptyDataSource());
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("connection");

  const selectedSource = useMemo(
    () => dataSources.find((item) => item.id === selectedId) ?? null,
    [dataSources, selectedId],
  );
  const isExisting = selectedSource !== null;
  const controlsDisabled = env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true";
  const isOracle = draft.db_type === "oracle";

  useEffect(() => {
    if (dataSources.length === 0) {
      setSelectedId(NEW_SOURCE_ID);
      return;
    }
    if (!selectedId) {
      setSelectedId(dataSources[0]!.id);
      return;
    }
    if (
      selectedId !== NEW_SOURCE_ID &&
      !dataSources.some((item) => item.id === selectedId)
    ) {
      setSelectedId(dataSources[0]!.id);
    }
  }, [dataSources, selectedId]);

  useEffect(() => {
    if (selectedSource) {
      setDraft(selectedSource);
      setStatusMessage(null);
      return;
    }
    if (selectedId === NEW_SOURCE_ID) {
      setDraft(createEmptyDataSource());
      setStatusMessage(null);
      setActiveTab("connection");
    }
  }, [selectedId, selectedSource]);

  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    testMutation.isPending ||
    clearSchemaCacheMutation.isPending;

  const saveLabel = isExisting ? t.common.save : t.common.create;

  async function handleSave() {
    try {
      const payload: DataSourceConfig = {
        ...draft,
        id: draft.id.trim(),
        name: draft.name.trim(),
        host: draft.host.trim(),
        database: draft.database.trim(),
        username: draft.username.trim(),
        password_env: draft.password_env.trim(),
        service_name: emptyToNull(draft.service_name),
        sid: emptyToNull(draft.sid),
        oracle_client_path: emptyToNull(draft.oracle_client_path),
        description: draft.description.trim(),
      };
      const result = isExisting
        ? await updateMutation.mutateAsync({
            dataSourceId: selectedSource.id,
            request: payload,
          })
        : await createMutation.mutateAsync(payload);
      setSelectedId(result.id);
      setStatusMessage(
        isExisting
          ? t.settings.nlp2sql.updateSuccess
          : t.settings.nlp2sql.createSuccess,
      );
      toast.success(
        isExisting
          ? t.settings.nlp2sql.updateSuccess
          : t.settings.nlp2sql.createSuccess,
      );
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handleDelete() {
    if (!selectedSource) {
      return;
    }
    if (!window.confirm(t.settings.nlp2sql.deleteConfirm)) {
      return;
    }
    try {
      await deleteMutation.mutateAsync(selectedSource.id);
      setSelectedId(
        dataSources.find((item) => item.id !== selectedSource.id)?.id ??
          NEW_SOURCE_ID,
      );
      setStatusMessage(t.settings.nlp2sql.deleteSuccess);
      toast.success(t.settings.nlp2sql.deleteSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handleTest() {
    if (!selectedSource) {
      return;
    }
    try {
      const result = await testMutation.mutateAsync(selectedSource.id);
      setStatusMessage(result.message);
      toast.success(t.settings.nlp2sql.testSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handleClearSchemaCache() {
    if (!selectedSource) {
      return;
    }
    try {
      const result = await clearSchemaCacheMutation.mutateAsync(
        selectedSource.id,
      );
      setStatusMessage(result.message);
      toast.success(t.settings.nlp2sql.cacheCleared);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  return (
    <SettingsSection
      title={t.settings.nlp2sql.title}
      description={t.settings.nlp2sql.description}
    >
      {isLoading ? (
        <div className="text-muted-foreground text-sm">{t.common.loading}</div>
      ) : error ? (
        <div>Error: {error.message}</div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium">
                  {t.settings.nlp2sql.listTitle}
                </div>
                <div className="text-muted-foreground text-sm">
                  {dataSources.length === 0
                    ? t.settings.nlp2sql.emptyDescription
                    : `${dataSources.length} ${t.settings.nlp2sql.sourceCountSuffix}`}
                </div>
              </div>
              <Button
                size="sm"
                disabled={controlsDisabled}
                onClick={() => setSelectedId(NEW_SOURCE_ID)}
              >
                <PlusIcon className="size-4" />
                {t.settings.nlp2sql.newSource}
              </Button>
            </div>

            <div className="flex flex-col gap-3">
              {dataSources.length === 0 ? (
                <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                  {t.settings.nlp2sql.emptyTitle}
                </div>
              ) : (
                dataSources.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    className="text-left"
                  >
                    <Item
                      variant="outline"
                      className={cn(
                        selectedId === item.id &&
                          "border-primary ring-primary/20 ring-2",
                      )}
                    >
                      <ItemContent>
                        <ItemTitle>{item.name}</ItemTitle>
                        <ItemDescription>
                          {item.db_type} · {item.host}:{item.port} ·{" "}
                          {item.database}
                        </ItemDescription>
                      </ItemContent>
                      <ItemActions>
                        <span
                          className={cn(
                            "rounded-full px-2 py-1 text-xs font-medium",
                            item.enabled
                              ? "bg-emerald-500/15 text-emerald-700"
                              : "bg-muted text-muted-foreground",
                          )}
                        >
                          {item.enabled
                            ? t.settings.nlp2sql.enabledBadge
                            : t.settings.nlp2sql.disabledBadge}
                        </span>
                      </ItemActions>
                    </Item>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="space-y-4 rounded-lg border p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium">
                  <DatabaseIcon className="size-4" />
                  {isExisting
                    ? t.settings.nlp2sql.editorTitleEdit
                    : t.settings.nlp2sql.editorTitleNew}
                </div>
                <p className="text-muted-foreground mt-1 text-sm">
                  {t.settings.nlp2sql.createHint}
                </p>
              </div>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList variant="line">
                <TabsTrigger value="connection">
                  {t.settings.nlp2sql.tabs.connection}
                </TabsTrigger>
                <TabsTrigger value="knowledge">
                  {t.settings.nlp2sql.tabs.knowledge}
                </TabsTrigger>
                <TabsTrigger value="schema">
                  {t.settings.nlp2sql.tabs.schema}
                </TabsTrigger>
                <TabsTrigger value="files">
                  {t.settings.nlp2sql.tabs.files}
                </TabsTrigger>
                <TabsTrigger value="history">
                  {t.settings.nlp2sql.tabs.history}
                </TabsTrigger>
                <TabsTrigger value="jobs">
                  {t.settings.nlp2sql.tabs.jobs}
                </TabsTrigger>
                <TabsTrigger value="embedding">
                  {t.settings.nlp2sql.tabs.embedding}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="connection" className="pt-4">
                <div className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <Field label={t.settings.nlp2sql.idLabel}>
                      <Input
                        value={draft.id}
                        disabled={controlsDisabled || isExisting}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            id: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.nameLabel}>
                      <Input
                        value={draft.name}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            name: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.dbTypeLabel}>
                      <Select
                        value={draft.db_type}
                        onValueChange={(value) =>
                          setDraft((current) => ({
                            ...current,
                            db_type: value as DatabaseType,
                            port: DEFAULT_PORTS[value as DatabaseType],
                            service_name:
                              value === "oracle"
                                ? current.service_name ?? ""
                                : null,
                            sid: value === "oracle" ? current.sid ?? "" : null,
                            oracle_client_path:
                              value === "oracle"
                                ? current.oracle_client_path ?? ""
                                : null,
                          }))
                        }
                        disabled={controlsDisabled}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="mysql">
                            {t.settings.nlp2sql.mysqlLabel}
                          </SelectItem>
                          <SelectItem value="postgres">
                            {t.settings.nlp2sql.postgresLabel}
                          </SelectItem>
                          <SelectItem value="oracle">
                            {t.settings.nlp2sql.oracleLabel}
                          </SelectItem>
                          <SelectItem value="dm">
                            {t.settings.nlp2sql.dmLabel}
                          </SelectItem>
                          <SelectItem value="kingbase">
                            {t.settings.nlp2sql.kingbaseLabel}
                          </SelectItem>
                          <SelectItem value="gaussdb">
                            {t.settings.nlp2sql.gaussdbLabel}
                          </SelectItem>
                          <SelectItem value="opengauss">
                            {t.settings.nlp2sql.opengaussLabel}
                          </SelectItem>
                          <SelectItem value="oceanbase">
                            {t.settings.nlp2sql.oceanbaseLabel}
                          </SelectItem>
                          <SelectItem value="tidb">
                            {t.settings.nlp2sql.tidbLabel}
                          </SelectItem>
                          <SelectItem value="polardb">
                            {t.settings.nlp2sql.polardbLabel}
                          </SelectItem>
                          <SelectItem value="goldendb">
                            {t.settings.nlp2sql.goldendbLabel}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label={t.settings.nlp2sql.defaultValidationModeLabel}>
                      <Select
                        value={draft.default_validation_mode}
                        onValueChange={(value) =>
                          setDraft((current) => ({
                            ...current,
                            default_validation_mode: value as ValidationMode,
                          }))
                        }
                        disabled={controlsDisabled}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="relaxed">
                            {t.settings.nlp2sql.relaxedLabel}
                          </SelectItem>
                          <SelectItem value="strict">
                            {t.settings.nlp2sql.strictLabel}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label={t.settings.nlp2sql.hostLabel}>
                      <Input
                        value={draft.host}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            host: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.portLabel}>
                      <Input
                        type="number"
                        value={draft.port ?? ""}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            port: e.target.value ? Number(e.target.value) : null,
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.databaseLabel}>
                      <Input
                        value={draft.database}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            database: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.usernameLabel}>
                      <Input
                        value={draft.username}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            username: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.passwordEnvLabel}>
                      <Input
                        value={draft.password_env}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            password_env: e.target.value,
                          }))
                        }
                      />
                    </Field>
                    {isOracle ? (
                      <>
                        <Field label={t.settings.nlp2sql.serviceNameLabel}>
                          <Input
                            value={draft.service_name ?? ""}
                            disabled={controlsDisabled}
                            onChange={(e) =>
                              setDraft((current) => ({
                                ...current,
                                service_name: e.target.value,
                              }))
                            }
                          />
                        </Field>
                        <Field label={t.settings.nlp2sql.sidLabel}>
                          <Input
                            value={draft.sid ?? ""}
                            disabled={controlsDisabled}
                            onChange={(e) =>
                              setDraft((current) => ({
                                ...current,
                                sid: e.target.value,
                              }))
                            }
                          />
                        </Field>
                        <Field
                          label={t.settings.nlp2sql.oracleClientPathLabel}
                        >
                          <Input
                            value={draft.oracle_client_path ?? ""}
                            disabled={controlsDisabled}
                            onChange={(e) =>
                              setDraft((current) => ({
                                ...current,
                                oracle_client_path: e.target.value,
                              }))
                            }
                          />
                        </Field>
                      </>
                    ) : null}
                    <Field label={t.settings.nlp2sql.maxRowsLabel}>
                      <Input
                        type="number"
                        value={draft.max_rows}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            max_rows: Number(e.target.value || 0),
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.connectTimeoutLabel}>
                      <Input
                        type="number"
                        value={draft.connect_timeout_seconds}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            connect_timeout_seconds: Number(e.target.value || 0),
                          }))
                        }
                      />
                    </Field>
                    <Field label={t.settings.nlp2sql.queryTimeoutLabel}>
                      <Input
                        type="number"
                        value={draft.query_timeout_seconds}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            query_timeout_seconds: Number(e.target.value || 0),
                          }))
                        }
                      />
                    </Field>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Field
                      label={t.settings.nlp2sql.schemaWhitelistLabel}
                      description={t.settings.nlp2sql.whitelistHint}
                    >
                      <Textarea
                        value={formatList(draft.schema_whitelist)}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            schema_whitelist: parseList(e.target.value),
                          }))
                        }
                      />
                    </Field>
                    <Field
                      label={t.settings.nlp2sql.tableWhitelistLabel}
                      description={t.settings.nlp2sql.whitelistHint}
                    >
                      <Textarea
                        value={formatList(draft.table_whitelist)}
                        disabled={controlsDisabled}
                        onChange={(e) =>
                          setDraft((current) => ({
                            ...current,
                            table_whitelist: parseList(e.target.value),
                          }))
                        }
                      />
                    </Field>
                  </div>

                  <Field label={t.settings.nlp2sql.descriptionLabel}>
                    <Textarea
                      value={draft.description}
                      disabled={controlsDisabled}
                      onChange={(e) =>
                        setDraft((current) => ({
                          ...current,
                          description: e.target.value,
                        }))
                      }
                    />
                  </Field>
                  <div className="grid gap-4 md:grid-cols-2">
                    <ToggleField
                      label={t.settings.nlp2sql.readonlyLabel}
                      checked={draft.readonly}
                      disabled={controlsDisabled}
                      onCheckedChange={(checked) =>
                        setDraft((current) => ({
                          ...current,
                          readonly: checked,
                        }))
                      }
                    />
                    <ToggleField
                      label={t.settings.nlp2sql.enabledLabel}
                      checked={draft.enabled}
                      disabled={controlsDisabled}
                      onCheckedChange={(checked) =>
                        setDraft((current) => ({
                          ...current,
                          enabled: checked,
                        }))
                      }
                    />
                  </div>

                  {statusMessage ? (
                    <div className="bg-muted rounded-md px-3 py-2 text-sm">
                      {statusMessage}
                    </div>
                  ) : null}

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      disabled={controlsDisabled || busy}
                      onClick={handleSave}
                    >
                      {saveLabel}
                    </Button>
                    {isExisting ? (
                      <>
                        <Button
                          variant="outline"
                          disabled={controlsDisabled || busy}
                          onClick={handleTest}
                        >
                          {t.settings.nlp2sql.testConnection}
                        </Button>
                        <Button
                          variant="outline"
                          disabled={controlsDisabled || busy}
                          onClick={handleClearSchemaCache}
                        >
                          {t.settings.nlp2sql.clearSchemaCache}
                        </Button>
                        <Button
                          variant="outline"
                          disabled={controlsDisabled || busy}
                          onClick={handleDelete}
                        >
                          {t.common.delete}
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="knowledge" className="pt-4">
                {selectedSource ? (
                  <Nlp2SqlKnowledgePanel
                    dataSourceId={selectedSource.id}
                    controlsDisabled={controlsDisabled}
                  />
                ) : (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                    {t.settings.nlp2sql.knowledgeRequiresSource}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="schema" className="pt-4">
                {selectedSource ? (
                  <Nlp2SqlSchemaPanel
                    dataSourceId={selectedSource.id}
                    controlsDisabled={controlsDisabled}
                  />
                ) : (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                    {t.settings.nlp2sql.knowledgeRequiresSource}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="files" className="pt-4">
                {selectedSource ? (
                  <Nlp2SqlFilesPanel
                    dataSourceId={selectedSource.id}
                    controlsDisabled={controlsDisabled}
                  />
                ) : (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                    {t.settings.nlp2sql.knowledgeRequiresSource}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="history" className="pt-4">
                {selectedSource ? (
                  <Nlp2SqlHistoryPanel
                    dataSourceId={selectedSource.id}
                    controlsDisabled={controlsDisabled}
                  />
                ) : (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                    {t.settings.nlp2sql.knowledgeRequiresSource}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="jobs" className="pt-4">
                {selectedSource ? (
                  <Nlp2SqlJobsPanel dataSourceId={selectedSource.id} />
                ) : (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
                    {t.settings.nlp2sql.knowledgeRequiresSource}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="embedding" className="pt-4">
                <Nlp2SqlEmbeddingPanel
                  controlsDisabled={controlsDisabled}
                  dataSourceId={selectedSource?.id ?? null}
                />
              </TabsContent>
            </Tabs>
          </section>
        </div>
      )}
    </SettingsSection>
  );
}

function Field({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-2 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {description ? (
        <span className="text-muted-foreground text-xs">{description}</span>
      ) : null}
    </label>
  );
}

function ToggleField({
  label,
  checked,
  disabled,
  onCheckedChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-md border px-3 py-2">
      <span className="text-sm font-medium">{label}</span>
      <Switch
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}
