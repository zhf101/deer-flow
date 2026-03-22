from __future__ import annotations

import os

from pydantic import BaseModel, Field


class KnowledgeConfig(BaseModel):
    dsn: str = Field(..., min_length=1)
    db_schema: str = Field(default="nlp2sql_knowledge", min_length=1)
    embedding_provider: str = Field(default="deterministic", min_length=1)
    embedding_model: str = Field(default="hash-v1", min_length=1)
    embedding_dimensions: int = Field(default=64, ge=8, le=8192)
    distance_metric: str = Field(default="cosine", min_length=1)


_config: KnowledgeConfig | None = None


def get_knowledge_config() -> KnowledgeConfig:
    global _config
    if _config is None:
        dsn = (
            os.getenv("DEER_FLOW_NLP2SQL_KNOWLEDGE_DSN")
            or os.getenv("DEER_FLOW_NLP2SQL_KNOWLEDGE_DATABASE_URL")
            or ""
        ).strip()
        if not dsn:
            raise RuntimeError(
                "NLP2SQL knowledge database is not configured. Set "
                "DEER_FLOW_NLP2SQL_KNOWLEDGE_DSN or "
                "DEER_FLOW_NLP2SQL_KNOWLEDGE_DATABASE_URL."
            )

        _config = KnowledgeConfig(
            dsn=dsn,
            db_schema=os.getenv("DEER_FLOW_NLP2SQL_KNOWLEDGE_SCHEMA", "nlp2sql_knowledge").strip()
            or "nlp2sql_knowledge",
            embedding_provider=os.getenv("DEER_FLOW_NLP2SQL_EMBEDDING_PROVIDER", "deterministic").strip()
            or "deterministic",
            embedding_model=os.getenv("DEER_FLOW_NLP2SQL_EMBEDDING_MODEL", "hash-v1").strip() or "hash-v1",
            embedding_dimensions=int(os.getenv("DEER_FLOW_NLP2SQL_EMBEDDING_DIMENSIONS", "64")),
            distance_metric=os.getenv("DEER_FLOW_NLP2SQL_DISTANCE_METRIC", "cosine").strip() or "cosine",
        )
    return _config


def _reset_knowledge_config() -> None:
    global _config
    _config = None
