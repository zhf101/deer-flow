from __future__ import annotations

import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlglot

from deerflow.nlp2sql.knowledge_config import get_knowledge_config
from deerflow.nlp2sql.knowledge_embedder import (
    Embedder,
    build_embedder,
    build_embedder_from_settings,
)
from deerflow.nlp2sql.knowledge_repository import KnowledgeRepository
from deerflow.nlp2sql.knowledge_types import (
    ChunkRecord,
    EmbeddingProfile,
    EmbeddingProfileCreate,
    IndexJob,
    IndexJobStatus,
    IndexJobType,
    KnowledgeFile,
    KnowledgeIndexStatus,
    KnowledgeItem,
    KnowledgeItemCreate,
    KnowledgeItemType,
    KnowledgeItemUpdate,
    KnowledgeLifecycleStatus,
    utc_now,
)
from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS, convert_file_to_markdown


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _embedding_hash(vector: list[float]) -> str:
    payload = ",".join(f"{value:.10f}" for value in vector)
    return _checksum(payload)


def _estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped.split()))


def _decode_text_bytes(payload: bytes) -> str:
    if b"\x00" in payload:
        raise ValueError("Binary files are not supported for direct text indexing")

    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            text = payload.decode(encoding)
            if text:
                suspicious = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
                if suspicious > max(3, len(text) // 20):
                    continue
            return text
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode file content as text")


_index_job_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="nlp2sql-index",
)


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._config = get_knowledge_config()
        self._repository = repository or KnowledgeRepository(self._config)
        self._embedder = embedder or build_embedder(self._config)
        self._custom_embedder = embedder is not None
        self._embedder_cache: dict[tuple[str, str, int], Embedder] = {}

    def ensure_default_embedding_profile(self) -> EmbeddingProfile:
        active = self._repository.get_active_embedding_profile()
        if active is not None:
            return active

        existing = self._repository.list_embedding_profiles()
        if existing:
            return self._repository.activate_embedding_profile(existing[0].id)

        profile = EmbeddingProfile(
            id=f"profile-{uuid4().hex}",
            name=f"{self._config.embedding_provider}:{self._config.embedding_model}",
            provider=self._config.embedding_provider,
            model=self._config.embedding_model,
            dimensions=self._config.embedding_dimensions,
            distance_metric=self._config.distance_metric,
            is_active=True,
            config={},
        )
        return self._repository.create_embedding_profile(profile)

    def list_embedding_profiles(self) -> list[EmbeddingProfile]:
        self.ensure_default_embedding_profile()
        return self._repository.list_embedding_profiles()

    def create_embedding_profile(self, request: EmbeddingProfileCreate) -> EmbeddingProfile:
        profile = EmbeddingProfile(
            id=f"profile-{uuid4().hex}",
            name=request.name.strip(),
            provider=request.provider.strip(),
            model=request.model.strip(),
            dimensions=request.dimensions,
            distance_metric=request.distance_metric.strip(),
            is_active=False,
            config=request.config,
        )
        return self._repository.create_embedding_profile(profile)

    def activate_embedding_profile(self, profile_id: str) -> EmbeddingProfile:
        return self._repository.activate_embedding_profile(profile_id)

    def embed_text(
        self,
        text: str,
        *,
        profile: EmbeddingProfile | None = None,
    ) -> list[float]:
        return self._get_embedder(profile).embed(text)

    def search_semantic(
        self,
        *,
        data_source_id: str,
        embedding_profile: EmbeddingProfile,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._repository.search_semantic(
            data_source_id=data_source_id,
            embedding_profile=embedding_profile,
            query_vector=query_vector,
            limit=limit,
        )

    def search_keyword(
        self,
        *,
        data_source_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self._repository.search_keyword(
            data_source_id=data_source_id,
            query=query,
            limit=limit,
        )

    def list_items(
        self,
        data_source_id: str,
        *,
        item_type: str | None = None,
        query: str | None = None,
    ) -> list[KnowledgeItem]:
        self.ensure_default_embedding_profile()
        return self._repository.list_items(data_source_id, item_type=item_type, query=query)

    def get_item(self, data_source_id: str, item_id: str) -> KnowledgeItem | None:
        self.ensure_default_embedding_profile()
        return self._repository.get_item(data_source_id, item_id)

    def list_files(self, data_source_id: str) -> list[KnowledgeFile]:
        items = self.list_items(data_source_id, item_type=KnowledgeItemType.FILE)
        return [self._to_knowledge_file(item) for item in items]

    def list_index_jobs(self, data_source_id: str) -> list[IndexJob]:
        return self._repository.list_index_jobs(data_source_id)

    def get_index_job(self, data_source_id: str, job_id: str) -> IndexJob | None:
        return self._repository.get_index_job(data_source_id, job_id)

    def list_structured_schema_notes(self, data_source_id: str) -> list[KnowledgeItem]:
        items = self.list_items(data_source_id, item_type=KnowledgeItemType.SCHEMA_NOTE)
        notes: list[KnowledgeItem] = []
        for item in items:
            metadata = dict(item.metadata)
            schema_name = metadata.get("schema_name")
            table_name = metadata.get("table_name")
            note_kind = metadata.get("note_kind")
            if not isinstance(schema_name, str) or not schema_name.strip():
                continue
            if not isinstance(table_name, str) or not table_name.strip():
                continue
            if note_kind not in {None, "user_comment"}:
                continue
            notes.append(item)
        return notes

    def upsert_schema_comment(
        self,
        data_source_id: str,
        *,
        schema_name: str,
        table_name: str,
        column_name: str | None = None,
        comment: str,
    ) -> tuple[str, KnowledgeItem | None]:
        normalized_schema_name = schema_name.strip()
        normalized_table_name = table_name.strip()
        normalized_column_name = column_name.strip() if column_name and column_name.strip() else None
        normalized_comment = comment.strip()

        if not normalized_schema_name:
            raise ValueError("schema_name is required")
        if not normalized_table_name:
            raise ValueError("table_name is required")

        existing = self._find_structured_schema_note(
            data_source_id,
            schema_name=normalized_schema_name,
            table_name=normalized_table_name,
            column_name=normalized_column_name,
        )

        if not normalized_comment:
            deleted = False
            if existing is not None:
                deleted = self.delete_item(data_source_id, existing.id)
            self._clear_schema_cache_best_effort(data_source_id)
            return ("deleted" if deleted else "noop"), None

        metadata = {
            "schema_name": normalized_schema_name,
            "table_name": normalized_table_name,
            "note_kind": "user_comment",
        }
        if normalized_column_name is not None:
            metadata["column_name"] = normalized_column_name

        title = ".".join(
            part for part in [normalized_schema_name, normalized_table_name, normalized_column_name] if part
        )

        if existing is None:
            item = self.create_item(
                data_source_id,
                KnowledgeItemCreate(
                    item_type=KnowledgeItemType.SCHEMA_NOTE,
                    title=title,
                    content=normalized_comment,
                    source_name=title,
                    metadata=metadata,
                ),
            )
            self._clear_schema_cache_best_effort(data_source_id)
            return "created", item

        item = self.update_item(
            data_source_id,
            existing.id,
            KnowledgeItemUpdate(
                title=title,
                content=normalized_comment,
                source_name=title,
                metadata=metadata,
            ),
        )
        self._clear_schema_cache_best_effort(data_source_id)
        return "updated", item

    def create_item(self, data_source_id: str, request: KnowledgeItemCreate) -> KnowledgeItem:
        profile = self.ensure_default_embedding_profile()
        prepared = self._prepare_item(
            item_id=f"knowledge-{uuid4().hex}",
            data_source_id=data_source_id,
            item_type=request.item_type,
            title=request.title,
            content=request.content,
            question=request.question,
            sql=request.sql,
            source_name=request.source_name,
            source_uri=request.source_uri,
            metadata=request.metadata,
        )
        self._repository.create_item(prepared)
        self._index_item(prepared, profile)
        if prepared.item_type == KnowledgeItemType.SCHEMA_NOTE:
            self._clear_schema_cache_best_effort(data_source_id)
        return self._repository.get_item(data_source_id, prepared.id) or prepared

    async def import_uploaded_file(
        self,
        data_source_id: str,
        *,
        file_name: str,
        content: bytes,
        mime_type: str | None = None,
    ) -> KnowledgeFile:
        extracted_text = await self._extract_file_text(file_name=file_name, content=content)
        metadata = {
            "file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "original_extension": Path(file_name).suffix.lower(),
            "content_length": len(extracted_text),
        }
        item = self.create_item(
            data_source_id,
            KnowledgeItemCreate(
                item_type=KnowledgeItemType.FILE,
                title=file_name,
                content=extracted_text,
                source_name=file_name,
                metadata=metadata,
            ),
        )
        return self._to_knowledge_file(item)

    def submit_file_import_job(
        self,
        data_source_id: str,
        *,
        files: list[dict[str, Any]],
    ) -> IndexJob:
        if not files:
            raise ValueError("No files provided")

        job = IndexJob(
            id=f"index-job-{uuid4().hex}",
            data_source_id=data_source_id,
            job_type=IndexJobType.FILE_IMPORT,
            target_scope={
                "files": [
                    {
                        "file_name": str(file["file_name"]),
                        "mime_type": file.get("mime_type"),
                        "size_bytes": len(file["content"]),
                    }
                    for file in files
                ]
            },
            status=IndexJobStatus.QUEUED,
            progress_total=len(files),
            progress_done=0,
        )
        self._repository.create_index_job(job)
        _index_job_executor.submit(self._run_file_import_job, job.id, data_source_id, files)
        return job

    def import_historical_sql(
        self,
        data_source_id: str,
        *,
        sql_text: str,
        source_name: str | None = None,
    ) -> list[KnowledgeItem]:
        statements = self._split_sql_statements(sql_text)
        if not statements:
            raise ValueError("No SQL statements were found in the provided text")

        imported_items: list[KnowledgeItem] = []
        normalized_source_name = source_name.strip() if source_name and source_name.strip() else "historical-sql-import"
        for index, statement in enumerate(statements, start=1):
            imported_items.append(
                self.create_item(
                    data_source_id,
                    KnowledgeItemCreate(
                        item_type=KnowledgeItemType.HISTORICAL_SQL,
                        title=self._build_historical_sql_title(statement, index),
                        content=statement,
                        source_name=normalized_source_name,
                        metadata={
                            "statement_index": index,
                            "source_type": "historical_sql_import",
                        },
                    ),
                )
            )
        return imported_items

    def submit_historical_sql_job(
        self,
        data_source_id: str,
        *,
        sql_text: str,
        source_name: str | None = None,
    ) -> IndexJob:
        statements = self._split_sql_statements(sql_text)
        if not statements:
            raise ValueError("No SQL statements were found in the provided text")

        job = IndexJob(
            id=f"index-job-{uuid4().hex}",
            data_source_id=data_source_id,
            job_type=IndexJobType.HISTORICAL_SQL_IMPORT,
            target_scope={
                "statement_count": len(statements),
                "source_name": source_name.strip() if source_name and source_name.strip() else "historical-sql-import",
            },
            status=IndexJobStatus.QUEUED,
            progress_total=len(statements),
            progress_done=0,
        )
        self._repository.create_index_job(job)
        _index_job_executor.submit(
            self._run_historical_sql_job,
            job.id,
            data_source_id,
            statements,
            source_name,
        )
        return job

    def submit_embedding_rebuild_job(
        self,
        profile_id: str,
        *,
        data_source_id: str,
    ) -> IndexJob:
        profile = self._require_embedding_profile(profile_id)
        chunks = self._repository.list_chunks_for_embedding_rebuild(data_source_id)
        job = IndexJob(
            id=f"index-job-{uuid4().hex}",
            data_source_id=data_source_id,
            job_type=IndexJobType.EMBEDDING_REBUILD,
            target_scope={
                "rebuild_scope": "data_source",
                "chunk_count": len(chunks),
            },
            embedding_profile_id=profile.id,
            status=IndexJobStatus.QUEUED,
            progress_total=len(chunks),
            progress_done=0,
        )
        self._repository.create_index_job(job)
        _index_job_executor.submit(
            self._run_embedding_rebuild_job,
            job.id,
            data_source_id,
            profile.id,
        )
        return job

    def update_item(self, data_source_id: str, item_id: str, request: KnowledgeItemUpdate) -> KnowledgeItem:
        existing = self._repository.get_item(data_source_id, item_id)
        if existing is None:
            raise KeyError(item_id)
        profile = self.ensure_default_embedding_profile()
        merged_metadata = dict(existing.metadata)
        merged_metadata.update(request.metadata)
        prepared = self._prepare_item(
            item_id=item_id,
            data_source_id=data_source_id,
            item_type=existing.item_type,
            title=request.title,
            content=request.content,
            question=request.question,
            sql=request.sql,
            source_name=request.source_name,
            source_uri=request.source_uri,
            metadata=merged_metadata,
        )
        prepared.created_at = existing.created_at
        self._repository.update_item(prepared)
        self._index_item(prepared, profile)
        if prepared.item_type == KnowledgeItemType.SCHEMA_NOTE:
            self._clear_schema_cache_best_effort(data_source_id)
        return self._repository.get_item(data_source_id, prepared.id) or prepared

    def delete_item(self, data_source_id: str, item_id: str) -> bool:
        deleted = self._repository.soft_delete_item(data_source_id, item_id)
        if deleted:
            self._clear_schema_cache_best_effort(data_source_id)
        return deleted

    async def _extract_file_text(self, *, file_name: str, content: bytes) -> str:
        suffix = Path(file_name).suffix.lower()
        if suffix in CONVERTIBLE_EXTENSIONS:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir) / Path(file_name).name
                temp_path.write_bytes(content)
                markdown_path = await convert_file_to_markdown(temp_path)
                if markdown_path is None or not markdown_path.exists():
                    raise ValueError(f"Failed to extract text from '{file_name}'")
                extracted = markdown_path.read_text(encoding="utf-8").strip()
        else:
            extracted = _decode_text_bytes(content).strip()

        if not extracted:
            raise ValueError(f"'{file_name}' did not contain any indexable text")
        return extracted

    def _run_file_import_job(
        self,
        job_id: str,
        data_source_id: str,
        files: list[dict[str, Any]],
    ) -> None:
        job = self._require_index_job(data_source_id, job_id)
        self._mark_job_running(job)
        try:
            for index, file in enumerate(files, start=1):
                self._run_async(
                    self.import_uploaded_file(
                        data_source_id,
                        file_name=str(file["file_name"]),
                        content=bytes(file["content"]),
                        mime_type=file.get("mime_type"),
                    )
                )
                self._mark_job_progress(data_source_id, job_id, progress_done=index)
            self._mark_job_completed(data_source_id, job_id)
        except Exception as exc:
            self._mark_job_failed(data_source_id, job_id, str(exc))

    def _run_historical_sql_job(
        self,
        job_id: str,
        data_source_id: str,
        statements: list[str],
        source_name: str | None,
    ) -> None:
        job = self._require_index_job(data_source_id, job_id)
        self._mark_job_running(job)
        normalized_source_name = source_name.strip() if source_name and source_name.strip() else "historical-sql-import"
        try:
            for index, statement in enumerate(statements, start=1):
                self.create_item(
                    data_source_id,
                    KnowledgeItemCreate(
                        item_type=KnowledgeItemType.HISTORICAL_SQL,
                        title=self._build_historical_sql_title(statement, index),
                        content=statement,
                        source_name=normalized_source_name,
                        metadata={
                            "statement_index": index,
                            "source_type": "historical_sql_import",
                        },
                    ),
                )
                self._mark_job_progress(data_source_id, job_id, progress_done=index)
            self._mark_job_completed(data_source_id, job_id)
        except Exception as exc:
            self._mark_job_failed(data_source_id, job_id, str(exc))

    def _run_embedding_rebuild_job(
        self,
        job_id: str,
        data_source_id: str,
        profile_id: str,
    ) -> None:
        job = self._require_index_job(data_source_id, job_id)
        self._mark_job_running(job)
        try:
            profile = self._require_embedding_profile(profile_id)
            chunks = self._repository.list_chunks_for_embedding_rebuild(data_source_id)
            self._mark_job_progress(
                data_source_id,
                job_id,
                progress_done=0,
                progress_total=len(chunks),
            )
            if not chunks:
                self._mark_job_completed(data_source_id, job_id)
                return

            batch: list[dict[str, Any]] = []
            for index, chunk in enumerate(chunks, start=1):
                vector = self.embed_text(str(chunk["chunk_text"]), profile=profile)
                batch.append(
                    {
                        "chunk_id": str(chunk["chunk_id"]),
                        "vector": vector,
                        "embedding_hash": _embedding_hash(vector),
                    }
                )
                if len(batch) >= 32:
                    self._repository.upsert_chunk_embeddings(
                        data_source_id=data_source_id,
                        embedding_profile=profile,
                        rows=batch,
                    )
                    batch = []
                    self._mark_job_progress(data_source_id, job_id, progress_done=index)

            if batch:
                self._repository.upsert_chunk_embeddings(
                    data_source_id=data_source_id,
                    embedding_profile=profile,
                    rows=batch,
                )
            self._mark_job_completed(data_source_id, job_id)
        except Exception as exc:
            self._mark_job_failed(data_source_id, job_id, str(exc))

    def _prepare_item(
        self,
        *,
        item_id: str,
        data_source_id: str,
        item_type: KnowledgeItemType,
        title: str,
        content: str,
        question: str | None,
        sql: str | None,
        source_name: str | None,
        source_uri: str | None,
        metadata: dict[str, Any],
    ) -> KnowledgeItem:
        clean_metadata = dict(metadata)
        normalized_title = title.strip()
        normalized_source_name = source_name.strip() if source_name else None
        normalized_source_uri = source_uri.strip() if source_uri else None

        if item_type == KnowledgeItemType.EXAMPLE_SQL:
            normalized_question = (question or clean_metadata.get("question") or "").strip()
            normalized_sql = (sql or clean_metadata.get("sql") or "").strip()
            if not normalized_question:
                raise ValueError("question is required for example_sql knowledge items")
            if not normalized_sql:
                raise ValueError("sql is required for example_sql knowledge items")
            clean_metadata["question"] = normalized_question
            clean_metadata["sql"] = normalized_sql
            normalized_content = f"Question: {normalized_question}\nSQL:\n{normalized_sql}"
            if not normalized_title:
                normalized_title = normalized_question
        else:
            normalized_question = None
            normalized_sql = None
            normalized_content = content.strip()
            if not normalized_content:
                raise ValueError("content is required for non-example_sql knowledge items")
            if not normalized_title:
                normalized_title = normalized_content.splitlines()[0][:80]

        now = utc_now()
        checksum_input = json.dumps(
            {
                "item_type": item_type,
                "title": normalized_title,
                "content": normalized_content,
                "metadata": clean_metadata,
                "source_name": normalized_source_name,
                "source_uri": normalized_source_uri,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return KnowledgeItem(
            id=item_id,
            data_source_id=data_source_id,
            item_type=item_type,
            title=normalized_title,
            content=normalized_content,
            question=normalized_question,
            sql=normalized_sql,
            source_name=normalized_source_name,
            source_uri=normalized_source_uri,
            metadata=clean_metadata,
            content_checksum=_checksum(checksum_input),
            lifecycle_status=KnowledgeLifecycleStatus.ACTIVE,
            index_status=KnowledgeIndexStatus.READY,
            created_at=now,
            updated_at=now,
        )

    def _build_chunks(self, item: KnowledgeItem) -> list[ChunkRecord]:
        chunk_text = item.content
        if item.item_type == KnowledgeItemType.SCHEMA_NOTE:
            metadata = dict(item.metadata)
            schema_name = metadata.get("schema_name")
            table_name = metadata.get("table_name")
            column_name = metadata.get("column_name")
            if isinstance(schema_name, str) and isinstance(table_name, str):
                if isinstance(column_name, str) and column_name.strip():
                    chunk_text = (
                        f"Column comment for {schema_name}.{table_name}.{column_name}: {item.content}"
                    )
                else:
                    chunk_text = f"Table comment for {schema_name}.{table_name}: {item.content}"
        return [
            ChunkRecord(
                chunk_index=0,
                chunk_type=item.item_type,
                chunk_text=chunk_text,
                token_count=_estimate_token_count(chunk_text),
                metadata=dict(item.metadata),
            )
        ]

    def _index_item(self, item: KnowledgeItem, profile: EmbeddingProfile) -> None:
        chunks = self._build_chunks(item)
        vectors = [self.embed_text(chunk.chunk_text, profile=profile) for chunk in chunks]
        hashes = [_embedding_hash(vector) for vector in vectors]
        self._repository.replace_chunks_and_embeddings(
            item_id=item.id,
            data_source_id=item.data_source_id,
            chunks=chunks,
            embedding_profile=profile,
            vectors=vectors,
            embedding_hashes=hashes,
        )

    def _require_index_job(self, data_source_id: str, job_id: str) -> IndexJob:
        job = self._repository.get_index_job(data_source_id, job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _mark_job_running(self, job: IndexJob) -> None:
        job.status = IndexJobStatus.RUNNING
        job.started_at = utc_now()
        job.error_message = None
        self._repository.update_index_job(job)

    def _mark_job_progress(
        self,
        data_source_id: str,
        job_id: str,
        *,
        progress_done: int,
        progress_total: int | None = None,
    ) -> None:
        job = self._require_index_job(data_source_id, job_id)
        job.progress_done = progress_done
        if progress_total is not None:
            job.progress_total = progress_total
        self._repository.update_index_job(job)

    def _mark_job_completed(self, data_source_id: str, job_id: str) -> None:
        job = self._require_index_job(data_source_id, job_id)
        job.status = IndexJobStatus.COMPLETED
        job.progress_done = job.progress_total
        job.finished_at = utc_now()
        job.error_message = None
        self._repository.update_index_job(job)

    def _mark_job_failed(self, data_source_id: str, job_id: str, message: str) -> None:
        job = self._require_index_job(data_source_id, job_id)
        job.status = IndexJobStatus.FAILED
        job.error_message = message
        job.finished_at = utc_now()
        self._repository.update_index_job(job)

    def _get_embedder(self, profile: EmbeddingProfile | None = None) -> Embedder:
        if profile is None or self._custom_embedder:
            return self._embedder

        default_key = (
            self._config.embedding_provider.casefold(),
            self._config.embedding_model,
            self._config.embedding_dimensions,
        )
        profile_key = (
            profile.provider.casefold(),
            profile.model,
            profile.dimensions,
        )
        if profile_key == default_key:
            return self._embedder

        cached = self._embedder_cache.get(profile_key)
        if cached is not None:
            return cached

        embedder = build_embedder_from_settings(
            provider=profile.provider,
            model=profile.model,
            dimensions=profile.dimensions,
        )
        self._embedder_cache[profile_key] = embedder
        return embedder

    def _require_embedding_profile(self, profile_id: str) -> EmbeddingProfile:
        profile = self._repository.get_embedding_profile(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        return profile

    @staticmethod
    def _split_sql_statements(sql_text: str) -> list[str]:
        try:
            parsed = sqlglot.parse(sql_text)
        except Exception as exc:
            raise ValueError(f"Failed to parse SQL text: {exc}") from exc

        statements = [expression.sql(pretty=False).strip() for expression in parsed]
        return [statement for statement in statements if statement]

    @staticmethod
    def _build_historical_sql_title(statement: str, index: int) -> str:
        first_line = " ".join(statement.splitlines()).strip()
        title = first_line[:80]
        if len(first_line) > 80:
            title = title.rstrip() + "..."
        return f"Statement {index}: {title}"

    @staticmethod
    def _run_async(awaitable) -> Any:
        import asyncio

        return asyncio.run(awaitable)

    @staticmethod
    def _to_knowledge_file(item: KnowledgeItem) -> KnowledgeFile:
        metadata = dict(item.metadata)
        file_name = str(metadata.get("file_name") or item.source_name or item.title)
        content_length = metadata.get("content_length")
        if not isinstance(content_length, int):
            content_length = len(item.content)

        return KnowledgeFile(
            id=item.id,
            data_source_id=item.data_source_id,
            file_name=file_name,
            mime_type=metadata.get("mime_type") if isinstance(metadata.get("mime_type"), str) else None,
            size_bytes=metadata.get("size_bytes") if isinstance(metadata.get("size_bytes"), int) else None,
            title=item.title,
            source_name=item.source_name,
            content_length=content_length,
            lifecycle_status=item.lifecycle_status,
            index_status=item.index_status,
            created_at=item.created_at,
            updated_at=item.updated_at,
            metadata=metadata,
        )

    def _find_structured_schema_note(
        self,
        data_source_id: str,
        *,
        schema_name: str,
        table_name: str,
        column_name: str | None,
    ) -> KnowledgeItem | None:
        for item in self.list_structured_schema_notes(data_source_id):
            metadata = dict(item.metadata)
            if metadata.get("schema_name") != schema_name:
                continue
            if metadata.get("table_name") != table_name:
                continue
            existing_column_name = metadata.get("column_name")
            if column_name is None:
                if existing_column_name not in {None, ""}:
                    continue
            elif existing_column_name != column_name:
                continue
            return item
        return None

    @staticmethod
    def _clear_schema_cache_best_effort(data_source_id: str) -> None:
        try:
            from deerflow.nlp2sql.service import get_database_service

            get_database_service().clear_schema_cache(data_source_id)
        except Exception:
            pass


_knowledge_service: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


def _reset_knowledge_service() -> None:
    global _knowledge_service
    _knowledge_service = None
