from __future__ import annotations

from unittest.mock import MagicMock

from deerflow.nlp2sql.knowledge_types import EmbeddingProfile
from deerflow.nlp2sql.retrieval_service import RetrievalService


class StubKnowledgeService:
    def __init__(self):
        self.profile = EmbeddingProfile.model_validate(
            {
                "id": "profile-1",
                "name": "deterministic:hash-v1",
                "provider": "deterministic",
                "model": "hash-v1",
                "dimensions": 64,
                "distance_metric": "cosine",
                "is_active": True,
                "config": {},
            }
        )

    def ensure_default_embedding_profile(self):
        return self.profile

    def embed_text(self, text: str) -> list[float]:
        assert text == "gmv"
        return [0.1, 0.2]

    def search_semantic(self, **_kwargs):
        return [
            {
                "chunk_id": "chunk-1",
                "item_id": "knowledge-1",
                "chunk_text": "GMV excludes cancelled orders.",
                "chunk_type": "documentation",
                "chunk_metadata": {},
                "item_type": "documentation",
                "title": "GMV definition",
                "source_name": "wiki",
                "source_uri": None,
                "item_metadata": {},
                "distance": 0.1,
            }
        ]

    def search_keyword(self, **_kwargs):
        return [
            {
                "chunk_id": "chunk-1",
                "item_id": "knowledge-1",
                "chunk_text": "GMV excludes cancelled orders.",
                "chunk_type": "documentation",
                "chunk_metadata": {},
                "item_type": "documentation",
                "title": "GMV definition",
                "source_name": "wiki",
                "source_uri": None,
                "item_metadata": {},
                "rank": 0.5,
            }
        ]


def test_preview_merges_semantic_and_keyword_hits():
    database_service = MagicMock()
    database_service.search_schema.return_value = []
    service = RetrievalService(
        knowledge_service=StubKnowledgeService(),
        database_service=database_service,
    )

    result = service.preview(data_source_id="sales-db", query="gmv", limit_per_bucket=3)

    assert result.active_embedding_profile_id == "profile-1"
    assert len(result.buckets) == 1
    assert result.buckets[0].bucket == "documentation"
    assert result.buckets[0].hits[0].match_sources == ["keyword", "semantic"]
    assert result.buckets[0].hits[0].score == 0.9


def test_preview_returns_warning_when_schema_search_fails():
    database_service = MagicMock()
    database_service.search_schema.side_effect = RuntimeError("schema unavailable")
    service = RetrievalService(
        knowledge_service=StubKnowledgeService(),
        database_service=database_service,
    )

    result = service.preview(data_source_id="sales-db", query="gmv", limit_per_bucket=2)

    assert result.warnings == ["Schema retrieval unavailable: schema unavailable"]
