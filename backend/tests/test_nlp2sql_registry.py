import json
import threading

import pytest

from deerflow.nlp2sql.errors import DataSourceAlreadyExistsError
from deerflow.nlp2sql.registry import DataSourceRegistry
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


def test_registry_round_trip(tmp_path):
    storage_path = tmp_path / "data_sources.json"
    registry = DataSourceRegistry(storage_path=storage_path)
    config = _build_config()

    registry.upsert(config)

    listed = registry.list(enabled_only=False)
    assert [item.id for item in listed] == ["sales-db"]
    assert registry.get("sales-db").name == "Sales DB"

    updated = _build_config(name="Revenue DB", enabled=False)
    registry.upsert(updated)

    assert registry.get("sales-db").name == "Revenue DB"
    assert registry.list(enabled_only=True) == []

    registry.delete("sales-db")
    assert registry.list(enabled_only=False) == []


def test_registry_create_rejects_duplicate_ids(tmp_path):
    storage_path = tmp_path / "data_sources.json"
    registry = DataSourceRegistry(storage_path=storage_path)
    config = _build_config()

    registry.create(config)

    with pytest.raises(DataSourceAlreadyExistsError, match="already exists"):
        registry.create(config)


def test_registry_concurrent_upserts_keep_json_valid(tmp_path):
    storage_path = tmp_path / "data_sources.json"
    registry = DataSourceRegistry(storage_path=storage_path)
    start = threading.Event()

    def worker(config: DataSourceConfig) -> None:
        start.wait()
        registry.upsert(config)

    config_a = _build_config(id="sales-db-a", name="Sales A")
    config_b = _build_config(id="sales-db-b", name="Sales B")
    threads = [
        threading.Thread(target=worker, args=(config_a,)),
        threading.Thread(target=worker, args=(config_b,)),
    ]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join()

    payload = json.loads(storage_path.read_text(encoding="utf-8"))
    assert sorted(item["id"] for item in payload["data_sources"]) == ["sales-db-a", "sales-db-b"]
