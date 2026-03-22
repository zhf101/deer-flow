from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class KnowledgeItemType(StrEnum):
    EXAMPLE_SQL = "example_sql"
    DOCUMENTATION = "documentation"
    GLOSSARY = "glossary"
    JOIN_HINT = "join_hint"
    FILTER_VALUE = "filter_value"
    SCHEMA_NOTE = "schema_note"
    HISTORICAL_SQL = "historical_sql"
    FILE = "file"


class KnowledgeLifecycleStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class KnowledgeIndexStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class IndexJobType(StrEnum):
    FILE_IMPORT = "file_import"
    HISTORICAL_SQL_IMPORT = "historical_sql_import"
    EMBEDDING_REBUILD = "embedding_rebuild"


class IndexJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EmbeddingProfileCreate(BaseModel):
    name: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    dimensions: int = Field(..., ge=8, le=8192)
    distance_metric: str = Field(default="cosine", min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)


class EmbeddingProfile(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    dimensions: int
    distance_metric: str
    is_active: bool
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None


class KnowledgeItemCreate(BaseModel):
    item_type: KnowledgeItemType
    title: str = ""
    content: str = ""
    question: str | None = None
    sql: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeItemUpdate(BaseModel):
    title: str = ""
    content: str = ""
    question: str | None = None
    sql: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeItem(BaseModel):
    id: str
    data_source_id: str
    item_type: KnowledgeItemType
    title: str = ""
    content: str = ""
    question: str | None = None
    sql: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_checksum: str
    lifecycle_status: KnowledgeLifecycleStatus = KnowledgeLifecycleStatus.ACTIVE
    index_status: KnowledgeIndexStatus = KnowledgeIndexStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeItemsResponse(BaseModel):
    knowledge_items: list[KnowledgeItem]


class KnowledgeFile(BaseModel):
    id: str
    data_source_id: str
    file_name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    title: str = ""
    source_name: str | None = None
    content_length: int = 0
    lifecycle_status: KnowledgeLifecycleStatus = KnowledgeLifecycleStatus.ACTIVE
    index_status: KnowledgeIndexStatus = KnowledgeIndexStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeFilesResponse(BaseModel):
    knowledge_files: list[KnowledgeFile]


class IndexJob(BaseModel):
    id: str
    data_source_id: str
    job_type: IndexJobType
    target_scope: dict[str, Any] = Field(default_factory=dict)
    embedding_profile_id: str | None = None
    status: IndexJobStatus = IndexJobStatus.QUEUED
    progress_total: int = 0
    progress_done: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class IndexJobsResponse(BaseModel):
    index_jobs: list[IndexJob]


class EmbeddingProfilesResponse(BaseModel):
    embedding_profiles: list[EmbeddingProfile]


class EmbeddingRebuildRequest(BaseModel):
    data_source_id: str | None = None
    all_data_sources: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> EmbeddingRebuildRequest:
        if self.all_data_sources and self.data_source_id:
            raise ValueError("Provide either data_source_id or all_data_sources=true, not both")
        if not self.all_data_sources and not self.data_source_id:
            raise ValueError("Either data_source_id or all_data_sources=true is required")
        return self


class ChunkRecord(BaseModel):
    chunk_index: int
    chunk_type: str
    chunk_text: str
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalPreviewRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit_per_bucket: int = Field(default=3, ge=1, le=10)


class HistoricalSqlImportRequest(BaseModel):
    sql_text: str = Field(..., min_length=1)
    source_name: str | None = None


class RetrievalPreviewHit(BaseModel):
    bucket: str
    item_id: str | None = None
    chunk_id: str | None = None
    title: str
    snippet: str
    score: float
    match_sources: list[str] = Field(default_factory=list)
    source_name: str | None = None
    source_uri: str | None = None
    schema_name: str | None = None
    table_name: str | None = None
    column_name: str | None = None


class RetrievalPreviewBucket(BaseModel):
    bucket: str
    hits: list[RetrievalPreviewHit] = Field(default_factory=list)


class RetrievalPreviewResponse(BaseModel):
    query: str
    data_source_id: str
    active_embedding_profile_id: str | None = None
    buckets: list[RetrievalPreviewBucket] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
