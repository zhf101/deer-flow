from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

import deerflow.nlp2sql.service as nlp2sql_service
from deerflow.nlp2sql.errors import QuerySafetyError
from deerflow.nlp2sql.service import DatabaseService
from deerflow.nlp2sql.types import DataSourceConfig, SqlValidationResult, ValidationMode


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
        "max_rows": 2,
        "default_validation_mode": "relaxed",
    }
    payload.update(overrides)
    return DataSourceConfig.model_validate(payload)


def test_with_adapter_preserves_primary_error_when_disconnect_fails(monkeypatch, caplog):
    config = _build_config()
    registry = MagicMock()
    registry.get.return_value = config

    adapter = MagicMock()
    adapter.disconnect.side_effect = RuntimeError("disconnect failed")
    monkeypatch.setattr(nlp2sql_service, "create_adapter", lambda _config: adapter)

    service = DatabaseService(registry=registry)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="query failed"):
            service.with_adapter(config.id, lambda _adapter, _data_source: (_ for _ in ()).throw(RuntimeError("query failed")))

    assert "Failed to disconnect adapter" in caplog.text
    adapter.connect.assert_called_once()
    adapter.disconnect.assert_called_once()


def test_validate_sql_strict_uses_adapter(monkeypatch):
    config = _build_config(max_rows=200)
    registry = MagicMock()
    registry.get.return_value = config

    adapter = MagicMock()
    monkeypatch.setattr(nlp2sql_service, "create_adapter", lambda _config: adapter)

    validator = MagicMock()
    expected = SqlValidationResult(
        ok=True,
        mode=ValidationMode.STRICT,
        normalized_sql="SELECT id FROM orders LIMIT 200",
        readonly=True,
        has_limit=True,
    )
    validator.validate.return_value = expected

    service = DatabaseService(registry=registry, validator=validator)

    result = service.validate_sql(config.id, "SELECT id FROM orders", mode=ValidationMode.STRICT)

    assert result == expected
    validator.validate.assert_called_once_with(
        "SELECT id FROM orders",
        mode=ValidationMode.STRICT,
        readonly=True,
        force_limit=200,
        allowed_schemas=["public"],
        allowed_tables=["orders"],
        adapter=adapter,
    )
    adapter.connect.assert_called_once()
    adapter.disconnect.assert_called_once()


def test_get_schema_returns_cached_schema_without_creating_adapter(monkeypatch):
    config = _build_config()
    registry = MagicMock()
    registry.get.return_value = config
    schema_service = MagicMock()
    schema_service.get_cached_schema.return_value = {"schemas": [{"name": "public", "tables": []}]}
    create_adapter = MagicMock()
    monkeypatch.setattr(nlp2sql_service, "create_adapter", create_adapter)

    service = DatabaseService(registry=registry, schema_service=schema_service)

    assert service.get_schema(config.id) == {"schemas": [{"name": "public", "tables": []}]}
    create_adapter.assert_not_called()


def test_execute_sql_truncates_rows_and_derives_columns(monkeypatch):
    config = _build_config(max_rows=2)
    registry = MagicMock()
    registry.get.return_value = config

    adapter = MagicMock()
    adapter.execute_query.return_value = (
        [],
        [{"id": 1, "status": "paid"}, {"id": 2, "status": "pending"}, {"id": 3, "status": "void"}],
    )
    monkeypatch.setattr(nlp2sql_service, "create_adapter", lambda _config: adapter)

    validator = MagicMock()
    validator.validate.return_value = SqlValidationResult(
        ok=True,
        mode=ValidationMode.STRICT,
        normalized_sql="SELECT id, status FROM orders LIMIT 2",
        readonly=True,
        has_limit=True,
        row_cap_applied=True,
    )

    service = DatabaseService(registry=registry, validator=validator)

    result = service.execute_sql(config.id, "SELECT id, status FROM orders")

    assert result.sql == "SELECT id, status FROM orders LIMIT 2"
    assert result.columns == ["id", "status"]
    assert result.row_count == 2
    assert result.fetched_row_count == 3
    assert result.truncated is True
    assert result.rows == [{"id": 1, "status": "paid"}, {"id": 2, "status": "pending"}]
    assert result.data_source_id == config.id
    assert result.execution_ms >= 0
    adapter.execute_query.assert_called_once_with(
        "SELECT id, status FROM orders LIMIT 3",
        None,
        max_rows=2,
    )


def test_execute_sql_raises_query_safety_error_when_validation_fails(monkeypatch):
    config = _build_config()
    registry = MagicMock()
    registry.get.return_value = config

    adapter = MagicMock()
    monkeypatch.setattr(nlp2sql_service, "create_adapter", lambda _config: adapter)

    validator = MagicMock()
    validator.validate.return_value = SqlValidationResult(
        ok=False,
        mode=ValidationMode.STRICT,
        normalized_sql="SELECT * FROM orders",
        errors=["Missing LIMIT"],
        warnings=["Large scan risk"],
        readonly=True,
        has_limit=False,
    )

    service = DatabaseService(registry=registry, validator=validator)

    with pytest.raises(QuerySafetyError, match="Missing LIMIT; Large scan risk"):
        service.execute_sql(config.id, "SELECT * FROM orders")


def test_clear_schema_cache_delegates_to_schema_service():
    registry = MagicMock()
    schema_service = MagicMock()
    service = DatabaseService(registry=registry, schema_service=schema_service, validator=MagicMock())

    service.clear_schema_cache("sales-db")

    schema_service.clear_cache.assert_called_once_with("sales-db")
