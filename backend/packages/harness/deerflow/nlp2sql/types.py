from __future__ import annotations

import os
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DatabaseType(StrEnum):
    MYSQL = "mysql"
    POSTGRES = "postgres"
    ORACLE = "oracle"
    DM = "dm"
    KINGBASE = "kingbase"
    GAUSSDB = "gaussdb"
    OPENGAUSS = "opengauss"
    OCEANBASE = "oceanbase"
    TIDB = "tidb"
    POLARDB = "polardb"
    GOLDENDB = "goldendb"


class ValidationMode(StrEnum):
    RELAXED = "relaxed"
    STRICT = "strict"


class DataSourceConfig(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    db_type: DatabaseType
    host: str = Field(..., min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password_env: str = Field(..., min_length=1)
    service_name: str | None = None
    sid: str | None = None
    oracle_client_path: str | None = None
    readonly: bool = True
    enabled: bool = True
    description: str = ""
    schema_whitelist: list[str] | None = None
    table_whitelist: list[str] | None = None
    connect_timeout_seconds: int = Field(default=10, ge=1, le=300)
    query_timeout_seconds: int = Field(default=60, ge=1, le=3600)
    max_rows: int = Field(default=200, ge=1, le=10000)
    default_validation_mode: ValidationMode = ValidationMode.RELAXED
    model_config = ConfigDict(use_enum_values=False)

    def model_post_init(self, __context: Any) -> None:
        if self.port is None:
            self.port = _DEFAULT_PORTS[self.db_type]

    def get_password(self) -> str:
        password = os.getenv(self.password_env)
        if password is None:
            raise ValueError(f"Environment variable '{self.password_env}' is not set")
        return password


class SchemaSearchHit(BaseModel):
    schema_name: str
    table_name: str
    column_name: str | None = None
    match_type: str
    score: float
    snippet: str


class SchemaColumn(BaseModel):
    name: str
    data_type: str | None = None
    column_type: str | None = None
    nullable: bool | None = None
    default: Any | None = None
    comment: str = ""
    source_comment: str = ""
    user_comment: str | None = None
    comment_source: str = "none"
    ordinal_position: int | None = None
    enum_values: list[Any] = Field(default_factory=list)


class SchemaTable(BaseModel):
    name: str
    comment: str = ""
    source_comment: str = ""
    user_comment: str | None = None
    comment_source: str = "none"
    note_item_id: str | None = None
    columns: list[SchemaColumn] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[dict[str, Any]] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    name: str
    tables: list[SchemaTable] = Field(default_factory=list)


class SchemaDocument(BaseModel):
    database: str | None = None
    db_type: str | None = None
    schemas: list[DatabaseSchema] = Field(default_factory=list)


class SchemaCommentUpsertRequest(BaseModel):
    schema_name: str = Field(..., min_length=1)
    table_name: str = Field(..., min_length=1)
    column_name: str | None = None
    comment: str = ""


class SchemaCommentUpsertResponse(BaseModel):
    ok: bool
    data_source_id: str
    action: str
    message: str
    note_item_id: str | None = None


class SqlValidationResult(BaseModel):
    ok: bool
    mode: ValidationMode
    normalized_sql: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    readonly: bool = True
    has_limit: bool = False
    row_cap_applied: bool = False
    explain_summary: dict[str, Any] | None = None


class QueryExecutionResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    fetched_row_count: int
    truncated: bool
    execution_ms: int
    data_source_id: str


class ThreadDatabaseSession(BaseModel):
    thread_id: str
    data_source_id: str | None = None
    validation_mode: ValidationMode = ValidationMode.RELAXED
    last_sql: str | None = None
    last_result: QueryExecutionResult | None = None
    last_used_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.last_used_at = utc_now()


_DEFAULT_PORTS: dict[DatabaseType, int] = {
    DatabaseType.MYSQL: 3306,
    DatabaseType.POSTGRES: 5432,
    DatabaseType.ORACLE: 1521,
    DatabaseType.DM: 5236,
    DatabaseType.KINGBASE: 54321,
    DatabaseType.GAUSSDB: 8000,
    DatabaseType.OPENGAUSS: 5432,
    DatabaseType.OCEANBASE: 2881,
    DatabaseType.TIDB: 4000,
    DatabaseType.POLARDB: 3306,
    DatabaseType.GOLDENDB: 3306,
}
