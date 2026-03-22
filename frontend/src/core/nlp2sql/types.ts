export type DatabaseType =
  | "mysql"
  | "postgres"
  | "oracle"
  | "dm"
  | "kingbase"
  | "gaussdb"
  | "opengauss"
  | "oceanbase"
  | "tidb"
  | "polardb"
  | "goldendb";
export type ValidationMode = "relaxed" | "strict";
export type KnowledgeItemType =
  | "example_sql"
  | "documentation"
  | "glossary"
  | "join_hint"
  | "filter_value"
  | "schema_note"
  | "historical_sql"
  | "file";

export interface DataSourceConfig {
  id: string;
  name: string;
  db_type: DatabaseType;
  host: string;
  port: number | null;
  database: string;
  username: string;
  password_env: string;
  service_name?: string | null;
  sid?: string | null;
  oracle_client_path?: string | null;
  readonly: boolean;
  enabled: boolean;
  description: string;
  schema_whitelist: string[] | null;
  table_whitelist: string[] | null;
  connect_timeout_seconds: number;
  query_timeout_seconds: number;
  max_rows: number;
  default_validation_mode: ValidationMode;
}

export type CreateDataSourceRequest = DataSourceConfig;
export type UpdateDataSourceRequest = DataSourceConfig;

export interface DataSourcesResponse {
  data_sources: DataSourceConfig[];
}

export interface ConnectionTestResponse {
  ok: boolean;
  data_source_id: string;
  message: string;
}

export interface SchemaCacheClearResponse {
  ok: boolean;
  data_source_id: string;
  message: string;
}

export interface SchemaColumn {
  name: string;
  data_type?: string | null;
  column_type?: string | null;
  nullable?: boolean | null;
  default?: unknown;
  comment: string;
  source_comment: string;
  user_comment?: string | null;
  comment_source: "database" | "user" | "none" | string;
  ordinal_position?: number | null;
  enum_values: unknown[];
}

export interface SchemaTable {
  name: string;
  comment: string;
  source_comment: string;
  user_comment?: string | null;
  comment_source: "database" | "user" | "none" | string;
  note_item_id?: string | null;
  columns: SchemaColumn[];
  primary_key: string[];
  foreign_keys: Array<Record<string, unknown>>;
}

export interface SchemaNamespace {
  name: string;
  tables: SchemaTable[];
}

export interface SchemaDocument {
  database?: string | null;
  db_type?: string | null;
  schemas: SchemaNamespace[];
}

export interface SchemaCommentUpsertRequest {
  schema_name: string;
  table_name: string;
  column_name?: string | null;
  comment: string;
}

export interface SchemaCommentUpsertResponse {
  ok: boolean;
  data_source_id: string;
  action: "created" | "updated" | "deleted" | "noop" | string;
  message: string;
  note_item_id?: string | null;
}

export interface KnowledgeItem {
  id: string;
  data_source_id: string;
  item_type: KnowledgeItemType;
  title: string;
  content: string;
  question?: string | null;
  sql?: string | null;
  source_name?: string | null;
  source_uri?: string | null;
  metadata: Record<string, unknown>;
  content_checksum: string;
  lifecycle_status: "active" | "deleted";
  index_status: "pending" | "ready" | "failed";
  created_at?: string;
  updated_at?: string;
}

export interface KnowledgeItemsResponse {
  knowledge_items: KnowledgeItem[];
}

export interface KnowledgeFile {
  id: string;
  data_source_id: string;
  file_name: string;
  mime_type?: string | null;
  size_bytes?: number | null;
  title: string;
  source_name?: string | null;
  content_length: number;
  lifecycle_status: "active" | "deleted";
  index_status: "pending" | "ready" | "failed";
  created_at?: string;
  updated_at?: string;
  metadata: Record<string, unknown>;
}

export interface KnowledgeFilesResponse {
  knowledge_files: KnowledgeFile[];
}

export type IndexJobType =
  | "file_import"
  | "historical_sql_import"
  | "embedding_rebuild";

export type IndexJobStatus = "queued" | "running" | "completed" | "failed";

export interface IndexJob {
  id: string;
  data_source_id: string;
  job_type: IndexJobType;
  target_scope: Record<string, unknown>;
  embedding_profile_id?: string | null;
  status: IndexJobStatus;
  progress_total: number;
  progress_done: number;
  error_message?: string | null;
  created_at?: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface IndexJobsResponse {
  index_jobs: IndexJob[];
}

export interface CreateKnowledgeItemRequest {
  item_type: KnowledgeItemType;
  title?: string;
  content?: string;
  question?: string | null;
  sql?: string | null;
  source_name?: string | null;
  source_uri?: string | null;
  metadata?: Record<string, unknown>;
}

export interface UpdateKnowledgeItemRequest {
  title?: string;
  content?: string;
  question?: string | null;
  sql?: string | null;
  source_name?: string | null;
  source_uri?: string | null;
  metadata?: Record<string, unknown>;
}

export interface EmbeddingProfile {
  id: string;
  name: string;
  provider: string;
  model: string;
  dimensions: number;
  distance_metric: string;
  is_active: boolean;
  config: Record<string, unknown>;
  created_at?: string;
  archived_at?: string | null;
}

export interface EmbeddingProfilesResponse {
  embedding_profiles: EmbeddingProfile[];
}

export interface CreateEmbeddingProfileRequest {
  name: string;
  provider: string;
  model: string;
  dimensions: number;
  distance_metric?: string;
  config?: Record<string, unknown>;
}

export interface ActivateEmbeddingProfileResponse {
  ok: boolean;
  embedding_profile: EmbeddingProfile;
}

export interface EmbeddingRebuildRequest {
  data_source_id?: string | null;
  all_data_sources?: boolean;
}

export interface RetrievalPreviewRequest {
  query: string;
  limit_per_bucket?: number;
}

export interface RetrievalPreviewHit {
  bucket: string;
  item_id?: string | null;
  chunk_id?: string | null;
  title: string;
  snippet: string;
  score: number;
  match_sources: string[];
  source_name?: string | null;
  source_uri?: string | null;
  schema_name?: string | null;
  table_name?: string | null;
  column_name?: string | null;
}

export interface RetrievalPreviewBucket {
  bucket: string;
  hits: RetrievalPreviewHit[];
}

export interface RetrievalPreviewResponse {
  query: string;
  data_source_id: string;
  active_embedding_profile_id?: string | null;
  buckets: RetrievalPreviewBucket[];
  warnings: string[];
}

export interface HistoricalSqlImportRequest {
  sql_text: string;
  source_name?: string | null;
}
