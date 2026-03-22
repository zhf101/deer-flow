from __future__ import annotations

import json
import re
import threading
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier

from deerflow.nlp2sql.knowledge_config import KnowledgeConfig
from deerflow.nlp2sql.knowledge_types import ChunkRecord, EmbeddingProfile, IndexJob, KnowledgeItem

_SAFE_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"


def _distance_operator(metric: str) -> str:
    if metric == "l2":
        return "<->"
    return "<=>"


class KnowledgeRepository:
    def __init__(self, config: KnowledgeConfig) -> None:
        self._config = config
        self._bootstrap_lock = threading.Lock()
        self._bootstrapped = False
        if not _SAFE_SCHEMA_RE.match(config.db_schema):
            raise ValueError(f"Invalid NLP2SQL knowledge schema name: {config.db_schema!r}")

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._config.dsn, row_factory=dict_row)

    def ensure_bootstrap(self) -> None:
        if self._bootstrapped:
            return
        with self._bootstrap_lock:
            if self._bootstrapped:
                return
            schema = Identifier(self._config.db_schema)
            with self._connect() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute(SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
                conn.execute(
                    SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.knowledge_items (
                            id TEXT PRIMARY KEY,
                            data_source_id TEXT NOT NULL,
                            item_type TEXT NOT NULL,
                            title TEXT NOT NULL DEFAULT '',
                            content TEXT NOT NULL DEFAULT '',
                            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                            source_name TEXT NULL,
                            source_uri TEXT NULL,
                            content_checksum TEXT NOT NULL,
                            lifecycle_status TEXT NOT NULL DEFAULT 'active',
                            index_status TEXT NOT NULL DEFAULT 'pending',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE INDEX IF NOT EXISTS knowledge_items_data_source_idx
                        ON {}.knowledge_items (data_source_id, item_type, updated_at DESC)
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.knowledge_chunks (
                            id TEXT PRIMARY KEY,
                            item_id TEXT NOT NULL REFERENCES {}.knowledge_items(id) ON DELETE CASCADE,
                            data_source_id TEXT NOT NULL,
                            chunk_index INTEGER NOT NULL,
                            chunk_type TEXT NOT NULL,
                            chunk_text TEXT NOT NULL,
                            token_count INTEGER NOT NULL DEFAULT 0,
                            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                            search_tsv tsvector GENERATED ALWAYS AS (
                                to_tsvector('simple', coalesce(chunk_text, ''))
                            ) STORED,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (item_id, chunk_index)
                        )
                        """
                    ).format(schema, schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE INDEX IF NOT EXISTS knowledge_chunks_data_source_idx
                        ON {}.knowledge_chunks (data_source_id, item_id)
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx
                        ON {}.knowledge_chunks USING GIN (search_tsv)
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.embedding_profiles (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL UNIQUE,
                            provider TEXT NOT NULL,
                            model TEXT NOT NULL,
                            dimensions INTEGER NOT NULL,
                            distance_metric TEXT NOT NULL,
                            is_active BOOLEAN NOT NULL DEFAULT FALSE,
                            config JSONB NOT NULL DEFAULT '{}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            archived_at TIMESTAMPTZ NULL
                        )
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS embedding_profiles_single_active_idx
                        ON {}.embedding_profiles ((is_active))
                        WHERE is_active
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {{}}.chunk_embeddings (
                            id TEXT PRIMARY KEY,
                            chunk_id TEXT NOT NULL REFERENCES {{}}.knowledge_chunks(id) ON DELETE CASCADE,
                            data_source_id TEXT NOT NULL,
                            embedding_profile_id TEXT NOT NULL REFERENCES {{}}.embedding_profiles(id) ON DELETE CASCADE,
                            embedding VECTOR NOT NULL,
                            embedding_hash TEXT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (chunk_id, embedding_profile_id)
                        )
                        """
                    ).format(schema, schema, schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE INDEX IF NOT EXISTS chunk_embeddings_data_source_idx
                        ON {}.chunk_embeddings (data_source_id, embedding_profile_id)
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.index_jobs (
                            id TEXT PRIMARY KEY,
                            data_source_id TEXT NOT NULL,
                            job_type TEXT NOT NULL,
                            target_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
                            embedding_profile_id TEXT NULL,
                            status TEXT NOT NULL,
                            progress_total INTEGER NOT NULL DEFAULT 0,
                            progress_done INTEGER NOT NULL DEFAULT 0,
                            error_message TEXT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            started_at TIMESTAMPTZ NULL,
                            finished_at TIMESTAMPTZ NULL
                        )
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE INDEX IF NOT EXISTS index_jobs_data_source_idx
                        ON {}.index_jobs (data_source_id, created_at DESC)
                        """
                    ).format(schema)
                )
            self._bootstrapped = True

    def list_items(
        self,
        data_source_id: str,
        *,
        item_type: str | None = None,
        query: str | None = None,
    ) -> list[KnowledgeItem]:
        self.ensure_bootstrap()
        where = ["data_source_id = %s", "lifecycle_status = 'active'"]
        params: list[Any] = [data_source_id]
        if item_type:
            where.append("item_type = %s")
            params.append(item_type)
        if query:
            where.append("(title ILIKE %s OR content ILIKE %s)")
            like = f"%{query}%"
            params.extend([like, like])
        sql = SQL(
            """
            SELECT *
            FROM {}.knowledge_items
            WHERE """
            + " AND ".join(where)
            + """
            ORDER BY updated_at DESC, id ASC
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [KnowledgeItem.model_validate(self._row_to_item(row)) for row in rows]

    def get_item(self, data_source_id: str, item_id: str) -> KnowledgeItem | None:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT *
            FROM {}.knowledge_items
            WHERE data_source_id = %s
              AND id = %s
              AND lifecycle_status = 'active'
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            row = conn.execute(sql, [data_source_id, item_id]).fetchone()
        if row is None:
            return None
        return KnowledgeItem.model_validate(self._row_to_item(row))

    def create_item(self, item: KnowledgeItem) -> KnowledgeItem:
        self.ensure_bootstrap()
        sql = SQL(
            """
            INSERT INTO {}.knowledge_items (
                id,
                data_source_id,
                item_type,
                title,
                content,
                metadata,
                source_name,
                source_uri,
                content_checksum,
                lifecycle_status,
                index_status,
                created_at,
                updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s
            )
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            conn.execute(
                sql,
                [
                    item.id,
                    item.data_source_id,
                    item.item_type,
                    item.title,
                    item.content,
                    json.dumps(item.metadata, ensure_ascii=False),
                    item.source_name,
                    item.source_uri,
                    item.content_checksum,
                    item.lifecycle_status,
                    item.index_status,
                    item.created_at,
                    item.updated_at,
                ],
            )
            conn.commit()
        return item

    def update_item(self, item: KnowledgeItem) -> KnowledgeItem:
        self.ensure_bootstrap()
        sql = SQL(
            """
            UPDATE {}.knowledge_items
            SET
                title = %s,
                content = %s,
                metadata = %s::jsonb,
                source_name = %s,
                source_uri = %s,
                content_checksum = %s,
                index_status = %s,
                updated_at = %s
            WHERE data_source_id = %s
              AND id = %s
              AND lifecycle_status = 'active'
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            conn.execute(
                sql,
                [
                    item.title,
                    item.content,
                    json.dumps(item.metadata, ensure_ascii=False),
                    item.source_name,
                    item.source_uri,
                    item.content_checksum,
                    item.index_status,
                    item.updated_at,
                    item.data_source_id,
                    item.id,
                ],
            )
            conn.commit()
        return item

    def soft_delete_item(self, data_source_id: str, item_id: str) -> bool:
        self.ensure_bootstrap()
        sql = SQL(
            """
            UPDATE {}.knowledge_items
            SET lifecycle_status = 'deleted', updated_at = NOW()
            WHERE data_source_id = %s
              AND id = %s
              AND lifecycle_status = 'active'
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            cursor = conn.execute(sql, [data_source_id, item_id])
            conn.commit()
            return cursor.rowcount > 0

    def replace_chunks_and_embeddings(
        self,
        *,
        item_id: str,
        data_source_id: str,
        chunks: list[ChunkRecord],
        embedding_profile: EmbeddingProfile,
        vectors: list[list[float]],
        embedding_hashes: list[str],
    ) -> None:
        self.ensure_bootstrap()
        schema = Identifier(self._config.db_schema)
        delete_embeddings_sql = SQL(
            """
            DELETE FROM {}.chunk_embeddings
            WHERE chunk_id IN (
                SELECT id FROM {}.knowledge_chunks
                WHERE item_id = %s
            )
            """
        ).format(schema, schema)
        delete_chunks_sql = SQL("DELETE FROM {}.knowledge_chunks WHERE item_id = %s").format(schema)
        insert_chunk_sql = SQL(
            """
            INSERT INTO {}.knowledge_chunks (
                id,
                item_id,
                data_source_id,
                chunk_index,
                chunk_type,
                chunk_text,
                token_count,
                metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            """
        ).format(schema)
        insert_embedding_sql = SQL(
            """
            INSERT INTO {}.chunk_embeddings (
                id,
                chunk_id,
                data_source_id,
                embedding_profile_id,
                embedding,
                embedding_hash
            ) VALUES (
                %s, %s, %s, %s, %s::vector, %s
            )
            """
        ).format(schema)

        with self._connect() as conn:
            with conn.transaction():
                conn.execute(delete_embeddings_sql, [item_id])
                conn.execute(delete_chunks_sql, [item_id])
                for chunk, vector, embedding_hash in zip(chunks, vectors, embedding_hashes, strict=True):
                    chunk_id = f"{item_id}:chunk:{chunk.chunk_index}"
                    conn.execute(
                        insert_chunk_sql,
                        [
                            chunk_id,
                            item_id,
                            data_source_id,
                            chunk.chunk_index,
                            chunk.chunk_type,
                            chunk.chunk_text,
                            chunk.token_count,
                            json.dumps(chunk.metadata, ensure_ascii=False),
                        ],
                    )
                    conn.execute(
                        insert_embedding_sql,
                        [
                            f"{chunk_id}:embedding:{embedding_profile.id}",
                            chunk_id,
                            data_source_id,
                            embedding_profile.id,
                            _vector_literal(vector),
                            embedding_hash,
                        ],
                    )
            conn.commit()

    def list_embedding_profiles(self) -> list[EmbeddingProfile]:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT *
            FROM {}.embedding_profiles
            ORDER BY is_active DESC, created_at DESC, id ASC
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [EmbeddingProfile.model_validate(dict(row)) for row in rows]

    def get_embedding_profile(self, profile_id: str) -> EmbeddingProfile | None:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT *
            FROM {}.embedding_profiles
            WHERE id = %s
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            row = conn.execute(sql, [profile_id]).fetchone()
        if row is None:
            return None
        return EmbeddingProfile.model_validate(dict(row))

    def create_index_job(self, job: IndexJob) -> IndexJob:
        self.ensure_bootstrap()
        sql = SQL(
            """
            INSERT INTO {}.index_jobs (
                id,
                data_source_id,
                job_type,
                target_scope,
                embedding_profile_id,
                status,
                progress_total,
                progress_done,
                error_message,
                created_at,
                started_at,
                finished_at
            ) VALUES (
                %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            conn.execute(
                sql,
                [
                    job.id,
                    job.data_source_id,
                    job.job_type,
                    json.dumps(job.target_scope, ensure_ascii=False),
                    job.embedding_profile_id,
                    job.status,
                    job.progress_total,
                    job.progress_done,
                    job.error_message,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                ],
            )
            conn.commit()
        return job

    def update_index_job(self, job: IndexJob) -> IndexJob:
        self.ensure_bootstrap()
        sql = SQL(
            """
            UPDATE {}.index_jobs
            SET
                target_scope = %s::jsonb,
                embedding_profile_id = %s,
                status = %s,
                progress_total = %s,
                progress_done = %s,
                error_message = %s,
                started_at = %s,
                finished_at = %s
            WHERE id = %s
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            conn.execute(
                sql,
                [
                    json.dumps(job.target_scope, ensure_ascii=False),
                    job.embedding_profile_id,
                    job.status,
                    job.progress_total,
                    job.progress_done,
                    job.error_message,
                    job.started_at,
                    job.finished_at,
                    job.id,
                ],
            )
            conn.commit()
        return job

    def list_index_jobs(self, data_source_id: str) -> list[IndexJob]:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT *
            FROM {}.index_jobs
            WHERE data_source_id = %s
            ORDER BY created_at DESC, id DESC
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            rows = conn.execute(sql, [data_source_id]).fetchall()
        return [self._row_to_index_job(dict(row)) for row in rows]

    def get_index_job(self, data_source_id: str, job_id: str) -> IndexJob | None:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT *
            FROM {}.index_jobs
            WHERE data_source_id = %s
              AND id = %s
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            row = conn.execute(sql, [data_source_id, job_id]).fetchone()
        if row is None:
            return None
        return self._row_to_index_job(dict(row))

    def list_chunks_for_embedding_rebuild(self, data_source_id: str) -> list[dict[str, Any]]:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT
                kc.id AS chunk_id,
                kc.data_source_id,
                kc.chunk_text
            FROM {}.knowledge_chunks AS kc
            JOIN {}.knowledge_items AS ki
              ON ki.id = kc.item_id
            WHERE kc.data_source_id = %s
              AND ki.lifecycle_status = 'active'
            ORDER BY kc.created_at ASC, kc.id ASC
            """
        ).format(
            Identifier(self._config.db_schema),
            Identifier(self._config.db_schema),
        )
        with self._connect() as conn:
            rows = conn.execute(sql, [data_source_id]).fetchall()
        return [dict(row) for row in rows]

    def upsert_chunk_embeddings(
        self,
        *,
        data_source_id: str,
        embedding_profile: EmbeddingProfile,
        rows: list[dict[str, Any]],
    ) -> None:
        if not rows:
            return

        self.ensure_bootstrap()
        sql = SQL(
            """
            INSERT INTO {}.chunk_embeddings (
                id,
                chunk_id,
                data_source_id,
                embedding_profile_id,
                embedding,
                embedding_hash
            ) VALUES (
                %s, %s, %s, %s, %s::vector, %s
            )
            ON CONFLICT (chunk_id, embedding_profile_id)
            DO UPDATE SET
                id = EXCLUDED.id,
                data_source_id = EXCLUDED.data_source_id,
                embedding = EXCLUDED.embedding,
                embedding_hash = EXCLUDED.embedding_hash,
                created_at = NOW()
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            with conn.transaction():
                for row in rows:
                    chunk_id = str(row["chunk_id"])
                    conn.execute(
                        sql,
                        [
                            f"{chunk_id}:embedding:{embedding_profile.id}",
                            chunk_id,
                            data_source_id,
                            embedding_profile.id,
                            _vector_literal(list(row["vector"])),
                            row["embedding_hash"],
                        ],
                    )
            conn.commit()

    def search_semantic(
        self,
        *,
        data_source_id: str,
        embedding_profile: EmbeddingProfile,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.ensure_bootstrap()
        operator = _distance_operator(embedding_profile.distance_metric.casefold())
        sql = SQL(
            f"""
            SELECT
                ce.chunk_id,
                kc.item_id,
                kc.chunk_text,
                kc.chunk_type,
                kc.metadata AS chunk_metadata,
                ki.item_type,
                ki.title,
                ki.source_name,
                ki.source_uri,
                ki.metadata AS item_metadata,
                ce.embedding {operator} %s::vector AS distance
            FROM {{}}.chunk_embeddings AS ce
            JOIN {{}}.knowledge_chunks AS kc
              ON kc.id = ce.chunk_id
            JOIN {{}}.knowledge_items AS ki
              ON ki.id = kc.item_id
            WHERE ce.data_source_id = %s
              AND ce.embedding_profile_id = %s
              AND ki.lifecycle_status = 'active'
            ORDER BY distance ASC
            LIMIT %s
            """
        ).format(
            Identifier(self._config.db_schema),
            Identifier(self._config.db_schema),
            Identifier(self._config.db_schema),
        )
        with self._connect() as conn:
            rows = conn.execute(
                sql,
                [
                    _vector_literal(query_vector),
                    data_source_id,
                    embedding_profile.id,
                    limit,
                ],
            ).fetchall()
        return [dict(row) for row in rows]

    def search_keyword(
        self,
        *,
        data_source_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT
                kc.id AS chunk_id,
                kc.item_id,
                kc.chunk_text,
                kc.chunk_type,
                kc.metadata AS chunk_metadata,
                ki.item_type,
                ki.title,
                ki.source_name,
                ki.source_uri,
                ki.metadata AS item_metadata,
                ts_rank_cd(kc.search_tsv, plainto_tsquery('simple', %s)) AS rank
            FROM {}.knowledge_chunks AS kc
            JOIN {}.knowledge_items AS ki
              ON ki.id = kc.item_id
            WHERE kc.data_source_id = %s
              AND ki.lifecycle_status = 'active'
              AND kc.search_tsv @@ plainto_tsquery('simple', %s)
            ORDER BY rank DESC, kc.created_at DESC
            LIMIT %s
            """
        ).format(
            Identifier(self._config.db_schema),
            Identifier(self._config.db_schema),
        )
        with self._connect() as conn:
            rows = conn.execute(sql, [query, data_source_id, query, limit]).fetchall()
        return [dict(row) for row in rows]

    def get_active_embedding_profile(self) -> EmbeddingProfile | None:
        self.ensure_bootstrap()
        sql = SQL("SELECT * FROM {}.embedding_profiles WHERE is_active = TRUE").format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            row = conn.execute(sql).fetchone()
        if row is None:
            return None
        return EmbeddingProfile.model_validate(dict(row))

    def create_embedding_profile(self, profile: EmbeddingProfile) -> EmbeddingProfile:
        self.ensure_bootstrap()
        sql = SQL(
            """
            INSERT INTO {}.embedding_profiles (
                id,
                name,
                provider,
                model,
                dimensions,
                distance_metric,
                is_active,
                config,
                created_at,
                archived_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s
            )
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            conn.execute(
                sql,
                [
                    profile.id,
                    profile.name,
                    profile.provider,
                    profile.model,
                    profile.dimensions,
                    profile.distance_metric,
                    profile.is_active,
                    json.dumps(profile.config, ensure_ascii=False),
                    profile.created_at,
                    profile.archived_at,
                ],
            )
            conn.commit()
        return profile

    def activate_embedding_profile(self, profile_id: str) -> EmbeddingProfile:
        self.ensure_bootstrap()
        schema = Identifier(self._config.db_schema)
        clear_sql = SQL("UPDATE {}.embedding_profiles SET is_active = FALSE WHERE is_active = TRUE").format(schema)
        activate_sql = SQL(
            "UPDATE {}.embedding_profiles SET is_active = TRUE WHERE id = %s RETURNING *"
        ).format(schema)
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(clear_sql)
                row = conn.execute(activate_sql, [profile_id]).fetchone()
            conn.commit()
        if row is None:
            raise KeyError(profile_id)
        return EmbeddingProfile.model_validate(dict(row))

    @staticmethod
    def _row_to_index_job(row: dict[str, Any]) -> IndexJob:
        payload = dict(row)
        target_scope = payload.get("target_scope") or {}
        if isinstance(target_scope, str):
            target_scope = json.loads(target_scope)
        payload["target_scope"] = target_scope
        return IndexJob.model_validate(payload)

    @staticmethod
    def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        metadata = payload.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        payload["metadata"] = metadata
        payload["question"] = metadata.get("question")
        payload["sql"] = metadata.get("sql")
        return payload
