from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DatabaseType(StrEnum):
    MYSQL = "mysql"
    POSTGRES = "postgres"


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
            self.port = 3306 if self.db_type == DatabaseType.MYSQL else 5432

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
