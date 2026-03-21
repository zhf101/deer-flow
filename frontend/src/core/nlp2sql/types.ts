export type DatabaseType = "mysql" | "postgres";
export type ValidationMode = "relaxed" | "strict";

export interface DataSourceConfig {
  id: string;
  name: string;
  db_type: DatabaseType;
  host: string;
  port: number | null;
  database: string;
  username: string;
  password_env: string;
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
