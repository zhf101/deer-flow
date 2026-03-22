from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.gateway.routers.nlp2sql as nlp2sql_router
from deerflow.nlp2sql.errors import DataSourceAlreadyExistsError, DataSourceNotFoundError
from deerflow.nlp2sql.knowledge_types import (
    EmbeddingProfile,
    IndexJob,
    KnowledgeFile,
    KnowledgeItem,
    KnowledgeItemType,
    RetrievalPreviewResponse,
)
from deerflow.nlp2sql.types import DataSourceConfig


def _build_config(**overrides) -> DataSourceConfig:
    payload = {
        "id": "sales-db",
        "name": "Sales DB",
        "db_type": "postgres",
        "host": "localhost",
        "port": 5432,
        "database": "sales",
        "username": "readonly",
        "password_env": "SALES_DB_PASSWORD",
        "readonly": True,
        "enabled": True,
        "description": "Test database",
        "schema_whitelist": ["public"],
        "table_whitelist": ["orders"],
        "connect_timeout_seconds": 10,
        "query_timeout_seconds": 60,
        "max_rows": 200,
        "default_validation_mode": "relaxed",
    }
    payload.update(overrides)
    return DataSourceConfig.model_validate(payload)


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(nlp2sql_router.router)
    return TestClient(app)


def _build_knowledge_item(**overrides) -> KnowledgeItem:
    payload = {
        "id": "knowledge-1",
        "data_source_id": "sales-db",
        "item_type": "documentation",
        "title": "GMV definition",
        "content": "GMV excludes cancelled orders.",
        "metadata": {},
        "content_checksum": "abc123",
        "lifecycle_status": "active",
        "index_status": "ready",
    }
    payload.update(overrides)
    return KnowledgeItem.model_validate(payload)


def _build_embedding_profile(**overrides) -> EmbeddingProfile:
    payload = {
        "id": "profile-1",
        "name": "deterministic:hash-v1",
        "provider": "deterministic",
        "model": "hash-v1",
        "dimensions": 64,
        "distance_metric": "cosine",
        "is_active": True,
        "config": {},
    }
    payload.update(overrides)
    return EmbeddingProfile.model_validate(payload)


def _build_knowledge_file(**overrides) -> KnowledgeFile:
    payload = {
        "id": "knowledge-file-1",
        "data_source_id": "sales-db",
        "file_name": "metrics.md",
        "mime_type": "text/markdown",
        "size_bytes": 128,
        "title": "metrics.md",
        "source_name": "metrics.md",
        "content_length": 64,
        "lifecycle_status": "active",
        "index_status": "ready",
        "metadata": {"file_name": "metrics.md"},
    }
    payload.update(overrides)
    return KnowledgeFile.model_validate(payload)


def _build_index_job(**overrides) -> IndexJob:
    payload = {
        "id": "index-job-1",
        "data_source_id": "sales-db",
        "job_type": "file_import",
        "target_scope": {"files": [{"file_name": "metrics.md"}]},
        "status": "queued",
        "progress_total": 1,
        "progress_done": 0,
    }
    payload.update(overrides)
    return IndexJob.model_validate(payload)


def test_list_data_sources_passes_enabled_only(monkeypatch):
    config = _build_config()
    calls: list[bool] = []

    class StubRegistry:
        def list(self, *, enabled_only: bool = True):
            calls.append(enabled_only)
            return [config]

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())

    with _make_client() as client:
        response = client.get("/api/nlp2sql/data-sources", params={"enabled_only": "true"})

    assert response.status_code == 200
    assert calls == [True]
    assert response.json()["data_sources"][0]["id"] == "sales-db"


def test_get_data_source_returns_404_when_missing(monkeypatch):
    class StubRegistry:
        def get(self, _data_source_id: str):
            raise DataSourceNotFoundError("missing source")

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())

    with _make_client() as client:
        response = client.get("/api/nlp2sql/data-sources/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "missing source"


def test_create_data_source_returns_409_when_id_exists(monkeypatch):
    config = _build_config()

    class StubRegistry:
        def create(self, _config: DataSourceConfig):
            raise DataSourceAlreadyExistsError("already exists")

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())

    with _make_client() as client:
        response = client.post("/api/nlp2sql/data-sources", json=config.model_dump(mode="json"))

    assert response.status_code == 409
    assert response.json()["detail"] == "already exists"


def test_update_data_source_rejects_path_and_body_mismatch():
    config = _build_config(id="body-id")

    with _make_client() as client:
        response = client.put("/api/nlp2sql/data-sources/path-id", json=config.model_dump(mode="json"))

    assert response.status_code == 422
    assert response.json()["detail"] == "Path data_source_id must match request.id"


def test_test_data_source_returns_registry_payload(monkeypatch):
    class StubRegistry:
        def test_connection(self, data_source_id: str):
            return {
                "ok": True,
                "data_source_id": data_source_id,
                "message": f"connected to {data_source_id}",
            }

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())

    with _make_client() as client:
        response = client.post("/api/nlp2sql/data-sources/sales-db/test")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data_source_id": "sales-db",
        "message": "connected to sales-db",
    }


def test_clear_schema_cache_calls_service(monkeypatch):
    config = _build_config()
    cleared: list[str] = []

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubService:
        def clear_schema_cache(self, data_source_id: str):
            cleared.append(data_source_id)

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_database_service", lambda: StubService())

    with _make_client() as client:
        response = client.delete(f"/api/nlp2sql/data-sources/{config.id}/schema-cache")

    assert response.status_code == 200
    assert cleared == [config.id]
    assert response.json() == {
        "ok": True,
        "data_source_id": config.id,
        "message": f"Cleared schema cache for '{config.id}'",
    }


def test_list_knowledge_items_returns_items(monkeypatch):
    config = _build_config()
    item = _build_knowledge_item()
    calls: list[tuple[str, KnowledgeItemType | None, str | None]] = []

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def list_items(self, data_source_id: str, *, item_type=None, query=None):
            calls.append((data_source_id, item_type, query))
            return [item]

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.get(
            f"/api/nlp2sql/data-sources/{config.id}/knowledge-items",
            params={"item_type": "documentation", "query": "GMV"},
        )

    assert response.status_code == 200
    assert calls == [(config.id, KnowledgeItemType.DOCUMENTATION, "GMV")]
    assert response.json()["knowledge_items"][0]["id"] == item.id


def test_create_knowledge_item_returns_created_item(monkeypatch):
    config = _build_config()
    item = _build_knowledge_item(item_type="example_sql", question="GMV?", sql="SELECT 1")

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def create_item(self, data_source_id: str, request):
            assert data_source_id == config.id
            assert request.item_type == KnowledgeItemType.EXAMPLE_SQL
            return item

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.post(
            f"/api/nlp2sql/data-sources/{config.id}/knowledge-items",
            json={
                "item_type": "example_sql",
                "title": "GMV query",
                "question": "What is GMV?",
                "sql": "SELECT 1",
            },
        )

    assert response.status_code == 201
    assert response.json()["item_type"] == "example_sql"
    assert response.json()["question"] == "GMV?"


def test_delete_knowledge_item_returns_404_when_missing(monkeypatch):
    config = _build_config()

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def delete_item(self, data_source_id: str, item_id: str):
            assert data_source_id == config.id
            assert item_id == "missing"
            return False

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.delete(f"/api/nlp2sql/data-sources/{config.id}/knowledge-items/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Knowledge item 'missing' not found"


def test_list_knowledge_files_returns_payload(monkeypatch):
    config = _build_config()
    file_record = _build_knowledge_file()

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def list_files(self, data_source_id: str):
            assert data_source_id == config.id
            return [file_record]

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.get(f"/api/nlp2sql/data-sources/{config.id}/knowledge-files")

    assert response.status_code == 200
    assert response.json()["knowledge_files"][0]["file_name"] == file_record.file_name


def test_list_index_jobs_returns_payload(monkeypatch):
    config = _build_config()
    job = _build_index_job()

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def list_index_jobs(self, data_source_id: str):
            assert data_source_id == config.id
            return [job]

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.get(f"/api/nlp2sql/data-sources/{config.id}/index-jobs")

    assert response.status_code == 200
    assert response.json()["index_jobs"][0]["id"] == job.id


def test_upload_knowledge_files_returns_created_job(monkeypatch):
    config = _build_config()
    job = _build_index_job()

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def submit_file_import_job(self, data_source_id: str, *, files):
            assert data_source_id == config.id
            assert len(files) == 1
            assert files[0]["file_name"] == "metrics.md"
            assert files[0]["content"] == b"GMV"
            assert files[0]["mime_type"] == "text/markdown"
            return job

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.post(
            f"/api/nlp2sql/data-sources/{config.id}/knowledge-files",
            files=[("files", ("metrics.md", b"GMV", "text/markdown"))],
        )

    assert response.status_code == 201
    assert response.json()["index_jobs"][0]["id"] == job.id


def test_delete_knowledge_file_returns_404_when_missing(monkeypatch):
    config = _build_config()

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def delete_item(self, data_source_id: str, item_id: str):
            assert data_source_id == config.id
            assert item_id == "missing-file"
            return False

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.delete(
            f"/api/nlp2sql/data-sources/{config.id}/knowledge-files/missing-file"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Knowledge file 'missing-file' not found"


def test_import_historical_sql_returns_imported_items(monkeypatch):
    config = _build_config()
    job = _build_index_job(job_type="historical_sql_import", target_scope={"statement_count": 1})

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def submit_historical_sql_job(self, data_source_id: str, *, sql_text: str, source_name: str | None):
            assert data_source_id == config.id
            assert sql_text == "SELECT 1;"
            assert source_name == "warehouse-history"
            return job

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.post(
            f"/api/nlp2sql/data-sources/{config.id}/historical-sql/import",
            json={"sql_text": "SELECT 1;", "source_name": "warehouse-history"},
        )

    assert response.status_code == 201
    assert response.json()["index_jobs"][0]["job_type"] == "historical_sql_import"


def test_activate_embedding_profile_returns_payload(monkeypatch):
    profile = _build_embedding_profile()

    class StubKnowledgeService:
        def activate_embedding_profile(self, profile_id: str):
            assert profile_id == profile.id
            return profile

    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.post(f"/api/nlp2sql/embedding-profiles/{profile.id}/activate")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "embedding_profile": profile.model_dump(mode="json"),
    }


def test_rebuild_embedding_profile_for_one_data_source_returns_job(monkeypatch):
    config = _build_config()
    profile = _build_embedding_profile()
    job = _build_index_job(job_type="embedding_rebuild", embedding_profile_id=profile.id)

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubKnowledgeService:
        def submit_embedding_rebuild_job(self, profile_id: str, *, data_source_id: str):
            assert profile_id == profile.id
            assert data_source_id == config.id
            return job

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.post(
            f"/api/nlp2sql/embedding-profiles/{profile.id}/rebuild",
            json={"data_source_id": config.id},
        )

    assert response.status_code == 201
    assert response.json()["index_jobs"][0]["job_type"] == "embedding_rebuild"


def test_rebuild_embedding_profile_for_all_data_sources_returns_jobs(monkeypatch):
    config_a = _build_config(id="sales-db-a", name="Sales A")
    config_b = _build_config(id="sales-db-b", name="Sales B")
    profile = _build_embedding_profile()
    jobs = [
        _build_index_job(
            id="index-job-a",
            data_source_id=config_a.id,
            job_type="embedding_rebuild",
            embedding_profile_id=profile.id,
        ),
        _build_index_job(
            id="index-job-b",
            data_source_id=config_b.id,
            job_type="embedding_rebuild",
            embedding_profile_id=profile.id,
        ),
    ]
    submitted = []

    class StubRegistry:
        def list(self, *, enabled_only: bool = False):
            assert enabled_only is False
            return [config_a, config_b]

    class StubKnowledgeService:
        def submit_embedding_rebuild_job(self, profile_id: str, *, data_source_id: str):
            submitted.append((profile_id, data_source_id))
            return next(job for job in jobs if job.data_source_id == data_source_id)

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_knowledge_service", lambda: StubKnowledgeService())

    with _make_client() as client:
        response = client.post(
            f"/api/nlp2sql/embedding-profiles/{profile.id}/rebuild",
            json={"all_data_sources": True},
        )

    assert response.status_code == 201
    assert submitted == [
        (profile.id, config_a.id),
        (profile.id, config_b.id),
    ]
    assert len(response.json()["index_jobs"]) == 2


def test_retrieve_preview_returns_payload(monkeypatch):
    config = _build_config()
    preview = RetrievalPreviewResponse.model_validate(
        {
            "query": "gmv",
            "data_source_id": config.id,
            "active_embedding_profile_id": "profile-1",
            "buckets": [
                {
                    "bucket": "documentation",
                    "hits": [
                        {
                            "bucket": "documentation",
                            "item_id": "knowledge-1",
                            "chunk_id": "chunk-1",
                            "title": "GMV definition",
                            "snippet": "GMV excludes cancelled orders.",
                            "score": 0.91,
                            "match_sources": ["semantic"],
                        }
                    ],
                }
            ],
            "warnings": [],
        }
    )

    class StubRegistry:
        def get(self, data_source_id: str):
            assert data_source_id == config.id
            return config

    class StubRetrievalService:
        def preview(self, *, data_source_id: str, query: str, limit_per_bucket: int):
            assert data_source_id == config.id
            assert query == "gmv"
            assert limit_per_bucket == 4
            return preview

    monkeypatch.setattr(nlp2sql_router, "get_data_source_registry", lambda: StubRegistry())
    monkeypatch.setattr(nlp2sql_router, "get_retrieval_service", lambda: StubRetrievalService())

    with _make_client() as client:
        response = client.post(
            f"/api/nlp2sql/data-sources/{config.id}/retrieve-preview",
            json={"query": "gmv", "limit_per_bucket": 4},
        )

    assert response.status_code == 200
    assert response.json()["query"] == "gmv"
    assert response.json()["buckets"][0]["bucket"] == "documentation"
