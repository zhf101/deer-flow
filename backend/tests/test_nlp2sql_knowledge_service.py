from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import deerflow.nlp2sql.knowledge_service as knowledge_service_module
from deerflow.nlp2sql.knowledge_service import KnowledgeService
from deerflow.nlp2sql.knowledge_types import EmbeddingProfileCreate, KnowledgeItemCreate


class StubRepository:
    def __init__(self):
        self.items = {}
        self.profiles = []
        self.active_profile = None
        self.index_calls = []
        self.index_jobs = {}
        self.embedding_rows = {}

    def get_active_embedding_profile(self):
        return self.active_profile

    def list_embedding_profiles(self):
        return list(self.profiles)

    def get_embedding_profile(self, profile_id: str):
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        return None

    def create_embedding_profile(self, profile):
        self.profiles.append(profile)
        if profile.is_active:
            self.active_profile = profile
        return profile

    def activate_embedding_profile(self, profile_id: str):
        for profile in self.profiles:
            profile.is_active = profile.id == profile_id
            if profile.is_active:
                self.active_profile = profile
                return profile
        raise KeyError(profile_id)

    def list_items(self, data_source_id: str, *, item_type=None, query=None):
        values = [item for item in self.items.values() if item.data_source_id == data_source_id]
        if item_type is not None:
            values = [item for item in values if item.item_type == item_type]
        if query:
            values = [item for item in values if query.lower() in item.content.lower()]
        return values

    def get_item(self, data_source_id: str, item_id: str):
        item = self.items.get(item_id)
        if item and item.data_source_id == data_source_id:
            return item
        return None

    def create_item(self, item):
        self.items[item.id] = item
        return item

    def update_item(self, item):
        self.items[item.id] = item
        return item

    def soft_delete_item(self, data_source_id: str, item_id: str):
        item = self.get_item(data_source_id, item_id)
        if item is None:
            return False
        del self.items[item_id]
        for key in list(self.embedding_rows):
            if key[0].startswith(f"{item_id}:chunk:"):
                del self.embedding_rows[key]
        return True

    def replace_chunks_and_embeddings(
        self,
        *,
        item_id: str,
        data_source_id: str,
        chunks,
        embedding_profile,
        vectors,
        embedding_hashes,
    ):
        self.index_calls.append(
            {
                "item_id": item_id,
                "data_source_id": data_source_id,
                "chunks": chunks,
                "embedding_profile": embedding_profile,
                "vectors": vectors,
                "embedding_hashes": embedding_hashes,
            }
        )
        for chunk, vector, embedding_hash in zip(chunks, vectors, embedding_hashes, strict=True):
            chunk_id = f"{item_id}:chunk:{chunk.chunk_index}"
            self.embedding_rows[(chunk_id, embedding_profile.id)] = {
                "chunk_id": chunk_id,
                "data_source_id": data_source_id,
                "chunk_text": chunk.chunk_text,
                "vector": vector,
                "embedding_hash": embedding_hash,
            }

    def create_index_job(self, job):
        self.index_jobs[job.id] = job.model_copy(deep=True)
        return job

    def update_index_job(self, job):
        self.index_jobs[job.id] = job.model_copy(deep=True)
        return job

    def list_index_jobs(self, data_source_id: str):
        return [
            job
            for job in self.index_jobs.values()
            if job.data_source_id == data_source_id
        ]

    def get_index_job(self, data_source_id: str, job_id: str):
        job = self.index_jobs.get(job_id)
        if job and job.data_source_id == data_source_id:
            return job
        return None

    def list_chunks_for_embedding_rebuild(self, data_source_id: str):
        chunks = []
        for item in self.items.values():
            if item.data_source_id != data_source_id:
                continue
            chunks.append(
                {
                    "chunk_id": f"{item.id}:chunk:0",
                    "data_source_id": data_source_id,
                    "chunk_text": item.content,
                }
            )
        chunks.sort(key=lambda row: row["chunk_id"])
        return chunks

    def upsert_chunk_embeddings(self, *, data_source_id: str, embedding_profile, rows):
        for row in rows:
            self.embedding_rows[(row["chunk_id"], embedding_profile.id)] = {
                "chunk_id": row["chunk_id"],
                "data_source_id": data_source_id,
                "vector": row["vector"],
                "embedding_hash": row["embedding_hash"],
            }


class StubEmbedder:
    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


def _build_service(monkeypatch) -> tuple[KnowledgeService, StubRepository]:
    repository = StubRepository()
    monkeypatch.setattr(
        knowledge_service_module,
        "get_knowledge_config",
        lambda: SimpleNamespace(
            embedding_provider="deterministic",
            embedding_model="hash-v1",
            embedding_dimensions=2,
            distance_metric="cosine",
        ),
    )
    service = KnowledgeService(repository=repository, embedder=StubEmbedder())
    return service, repository


def test_create_item_indexes_example_sql(monkeypatch):
    service, repository = _build_service(monkeypatch)

    item = service.create_item(
        "sales-db",
        KnowledgeItemCreate(
            item_type="example_sql",
            question="What is GMV?",
            sql="SELECT SUM(amount) FROM orders",
        ),
    )

    assert item.item_type == "example_sql"
    assert item.question == "What is GMV?"
    assert item.sql == "SELECT SUM(amount) FROM orders"
    assert repository.active_profile is not None
    assert len(repository.index_calls) == 1
    assert repository.index_calls[0]["chunks"][0].chunk_text.startswith("Question: What is GMV?")


def test_create_item_requires_content_for_documentation(monkeypatch):
    service, _repository = _build_service(monkeypatch)

    try:
        service.create_item(
            "sales-db",
            KnowledgeItemCreate(
                item_type="documentation",
                title="empty doc",
                content="",
            ),
        )
    except ValueError as exc:
        assert str(exc) == "content is required for non-example_sql knowledge items"
    else:
        raise AssertionError("Expected ValueError")


def test_create_embedding_profile_is_inactive_by_default(monkeypatch):
    service, repository = _build_service(monkeypatch)
    service.ensure_default_embedding_profile()

    profile = service.create_embedding_profile(
        EmbeddingProfileCreate(
            name="openai:text-embedding-3-large",
            provider="openai",
            model="text-embedding-3-large",
            dimensions=3072,
            distance_metric="cosine",
        )
    )

    assert profile.is_active is False
    assert repository.active_profile is not None
    assert repository.active_profile.id != profile.id


def test_import_uploaded_text_file_creates_file_knowledge(monkeypatch):
    service, repository = _build_service(monkeypatch)

    file_record = asyncio.run(
        service.import_uploaded_file(
            "sales-db",
            file_name="metrics.md",
            content=b"GMV excludes cancelled orders.",
            mime_type="text/markdown",
        )
    )

    assert file_record.file_name == "metrics.md"
    assert file_record.mime_type == "text/markdown"
    assert file_record.size_bytes == len(b"GMV excludes cancelled orders.")
    assert len(repository.index_calls) == 1
    assert repository.index_calls[0]["chunks"][0].chunk_text == "GMV excludes cancelled orders."


def test_import_uploaded_convertible_file_uses_markdown_conversion(monkeypatch, tmp_path):
    service, repository = _build_service(monkeypatch)

    async def fake_convert(file_path: Path) -> Path:
        md_path = file_path.with_suffix(".md")
        md_path.write_text("# Revenue\nGMV excludes refunds.", encoding="utf-8")
        return md_path

    monkeypatch.setattr(
        knowledge_service_module,
        "convert_file_to_markdown",
        AsyncMock(side_effect=fake_convert),
    )

    file_record = asyncio.run(
        service.import_uploaded_file(
            "sales-db",
            file_name="metrics.pdf",
            content=b"pdf-bytes",
            mime_type="application/pdf",
        )
    )

    assert file_record.file_name == "metrics.pdf"
    assert len(repository.index_calls) == 1
    assert repository.index_calls[0]["chunks"][0].chunk_text == "# Revenue\nGMV excludes refunds."


def test_import_historical_sql_creates_one_item_per_statement(monkeypatch):
    service, repository = _build_service(monkeypatch)

    items = service.import_historical_sql(
        "sales-db",
        sql_text="SELECT * FROM orders; SELECT id FROM customers;",
        source_name="warehouse-history",
    )

    assert len(items) == 2
    assert items[0].item_type == "historical_sql"
    assert items[0].source_name == "warehouse-history"
    assert items[0].content == "SELECT * FROM orders"
    assert items[1].content == "SELECT id FROM customers"
    assert len(repository.index_calls) == 2


def test_submit_embedding_rebuild_job_queues_background_work(monkeypatch):
    service, repository = _build_service(monkeypatch)
    service.create_item(
        "sales-db",
        KnowledgeItemCreate(
            item_type="documentation",
            title="GMV",
            content="GMV excludes cancelled orders.",
        ),
    )
    profile = service.create_embedding_profile(
        EmbeddingProfileCreate(
            name="deterministic:hash-v2",
            provider="deterministic",
            model="hash-v2",
            dimensions=64,
            distance_metric="cosine",
        )
    )
    submitted = []

    class StubExecutor:
        def submit(self, fn, *args):
            submitted.append((fn.__name__, args))
            return None

    monkeypatch.setattr(knowledge_service_module, "_index_job_executor", StubExecutor())

    job = service.submit_embedding_rebuild_job(profile.id, data_source_id="sales-db")

    assert job.job_type == "embedding_rebuild"
    assert job.embedding_profile_id == profile.id
    assert job.progress_total == 1
    assert repository.get_index_job("sales-db", job.id) is not None
    assert submitted == [("_run_embedding_rebuild_job", (job.id, "sales-db", profile.id))]


def test_embedding_rebuild_job_writes_vectors_for_target_profile(monkeypatch):
    service, repository = _build_service(monkeypatch)
    item = service.create_item(
        "sales-db",
        KnowledgeItemCreate(
            item_type="documentation",
            title="GMV",
            content="GMV excludes cancelled orders.",
        ),
    )
    active_profile = repository.active_profile
    assert active_profile is not None

    rebuild_profile = service.create_embedding_profile(
        EmbeddingProfileCreate(
            name="deterministic:hash-v2",
            provider="deterministic",
            model="hash-v2",
            dimensions=64,
            distance_metric="cosine",
        )
    )
    job = repository.create_index_job(
        knowledge_service_module.IndexJob(
            id="index-job-rebuild-1",
            data_source_id="sales-db",
            job_type="embedding_rebuild",
            target_scope={"rebuild_scope": "data_source"},
            embedding_profile_id=rebuild_profile.id,
            status="queued",
            progress_total=0,
            progress_done=0,
        )
    )

    service._run_embedding_rebuild_job(job.id, "sales-db", rebuild_profile.id)

    rebuilt = repository.embedding_rows[(f"{item.id}:chunk:0", rebuild_profile.id)]
    original = repository.embedding_rows[(f"{item.id}:chunk:0", active_profile.id)]
    stored_job = repository.get_index_job("sales-db", job.id)

    assert rebuilt["vector"] == [float(len(item.content)), 1.0]
    assert original["vector"] == [float(len(item.content)), 1.0]
    assert stored_job is not None
    assert stored_job.status == "completed"
    assert stored_job.progress_done == 1
    assert stored_job.progress_total == 1
