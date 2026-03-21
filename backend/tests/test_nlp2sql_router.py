from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.gateway.routers.nlp2sql as nlp2sql_router
from deerflow.nlp2sql.errors import DataSourceAlreadyExistsError, DataSourceNotFoundError
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
