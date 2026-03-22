from __future__ import annotations

from collections import defaultdict
from typing import Any

from deerflow.nlp2sql.knowledge_service import KnowledgeService, get_knowledge_service
from deerflow.nlp2sql.knowledge_types import (
    RetrievalPreviewBucket,
    RetrievalPreviewHit,
    RetrievalPreviewResponse,
)
from deerflow.nlp2sql.service import DatabaseService, get_database_service


def _clip_snippet(value: str, max_chars: int = 220) -> str:
    stripped = " ".join(value.split())
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3].rstrip() + "..."


class RetrievalService:
    def __init__(
        self,
        knowledge_service: KnowledgeService,
        database_service: DatabaseService | None = None,
    ) -> None:
        self._knowledge_service = knowledge_service
        self._database_service = database_service or get_database_service()

    def preview(
        self,
        *,
        data_source_id: str,
        query: str,
        limit_per_bucket: int = 3,
    ) -> RetrievalPreviewResponse:
        profile = self._knowledge_service.ensure_default_embedding_profile()
        warnings: list[str] = []
        bucket_hits: dict[str, dict[str, RetrievalPreviewHit]] = defaultdict(dict)

        query_vector = self._knowledge_service.embed_text(query, profile=profile)
        semantic_rows = self._knowledge_service.search_semantic(
            data_source_id=data_source_id,
            embedding_profile=profile,
            query_vector=query_vector,
            limit=max(limit_per_bucket * 4, 8),
        )
        keyword_rows = self._knowledge_service.search_keyword(
            data_source_id=data_source_id,
            query=query,
            limit=max(limit_per_bucket * 4, 8),
        )

        for row in semantic_rows:
            hit = self._row_to_hit(row, match_source="semantic")
            self._upsert_hit(bucket_hits, hit)

        for row in keyword_rows:
            hit = self._row_to_hit(row, match_source="keyword")
            self._upsert_hit(bucket_hits, hit)

        try:
            schema_hits = self._database_service.search_schema(
                data_source_id,
                query=query,
                limit=max(limit_per_bucket * 2, 6),
            )
        except Exception as exc:
            schema_hits = []
            warnings.append(f"Schema retrieval unavailable: {exc}")

        for schema_hit in schema_hits:
            key = f"{schema_hit.schema_name}.{schema_hit.table_name}.{schema_hit.column_name or ''}"
            bucket_hits["schema"][key] = RetrievalPreviewHit(
                bucket="schema",
                title=".".join(
                    part
                    for part in [
                        schema_hit.schema_name,
                        schema_hit.table_name,
                        schema_hit.column_name,
                    ]
                    if part
                ),
                snippet=schema_hit.snippet,
                score=max(0.0, min(1.0, schema_hit.score)),
                match_sources=["schema"],
                schema_name=schema_hit.schema_name,
                table_name=schema_hit.table_name,
                column_name=schema_hit.column_name,
            )

        ordered_buckets: list[RetrievalPreviewBucket] = []
        for bucket in [
            "example_sql",
            "glossary",
            "join_hint",
            "filter_value",
            "schema_note",
            "documentation",
            "historical_sql",
            "schema",
        ]:
            hits = list(bucket_hits.get(bucket, {}).values())
            if not hits:
                continue
            hits.sort(key=lambda hit: (-hit.score, hit.title.casefold(), hit.snippet.casefold()))
            ordered_buckets.append(
                RetrievalPreviewBucket(bucket=bucket, hits=hits[:limit_per_bucket])
            )

        return RetrievalPreviewResponse(
            query=query,
            data_source_id=data_source_id,
            active_embedding_profile_id=profile.id,
            buckets=ordered_buckets,
            warnings=warnings,
        )

    def _upsert_hit(
        self,
        bucket_hits: dict[str, dict[str, RetrievalPreviewHit]],
        incoming: RetrievalPreviewHit,
    ) -> None:
        bucket = bucket_hits[incoming.bucket]
        key = incoming.chunk_id or incoming.item_id or incoming.title
        existing = bucket.get(key)
        if existing is None:
            bucket[key] = incoming
            return

        existing.score = max(existing.score, incoming.score)
        existing.match_sources = sorted(set(existing.match_sources + incoming.match_sources))
        if len(incoming.snippet) > len(existing.snippet):
            existing.snippet = incoming.snippet

    def _row_to_hit(self, row: dict[str, Any], *, match_source: str) -> RetrievalPreviewHit:
        item_type = str(row["item_type"])
        item_metadata = self._coerce_metadata(row.get("item_metadata"))
        score = self._row_score(row, match_source=match_source)
        return RetrievalPreviewHit(
            bucket=item_type,
            item_id=str(row["item_id"]),
            chunk_id=str(row["chunk_id"]),
            title=str(row.get("title") or item_metadata.get("question") or item_type),
            snippet=_clip_snippet(str(row.get("chunk_text") or "")),
            score=score,
            match_sources=[match_source],
            source_name=row.get("source_name"),
            source_uri=row.get("source_uri"),
        )

    @staticmethod
    def _coerce_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _row_score(row: dict[str, Any], *, match_source: str) -> float:
        if match_source == "semantic":
            distance = float(row.get("distance") or 1.0)
            return max(0.0, min(1.0, 1.0 - distance))
        rank = float(row.get("rank") or 0.0)
        return max(0.0, min(1.0, rank))


_retrieval_service: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(
            knowledge_service=get_knowledge_service(),
        )
    return _retrieval_service


def _reset_retrieval_service() -> None:
    global _retrieval_service
    _retrieval_service = None
