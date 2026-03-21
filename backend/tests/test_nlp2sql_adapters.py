from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deerflow.nlp2sql.adapters.factory import create_adapter
from deerflow.nlp2sql.adapters.mysql import MySQLAdapter, _parse_mysql_enum, _require_identifier as mysql_require_identifier
from deerflow.nlp2sql.adapters.postgres import PostgresAdapter, _require_identifier as postgres_require_identifier
from deerflow.nlp2sql.errors import DatabaseConnectionError
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


def test_create_adapter_returns_mysql_adapter():
    adapter = create_adapter(_build_config(db_type="mysql", port=3306))

    assert isinstance(adapter, MySQLAdapter)


def test_create_adapter_returns_postgres_adapter():
    adapter = create_adapter(_build_config(db_type="postgres", port=5432))

    assert isinstance(adapter, PostgresAdapter)


def test_mysql_connect_wraps_driver_errors(monkeypatch):
    config = _build_config(db_type="mysql", port=3306)
    adapter = MySQLAdapter(config)
    monkeypatch.setenv(config.password_env, "secret")
    monkeypatch.setattr("deerflow.nlp2sql.adapters.mysql.pymysql.connect", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("mysql boom")))

    with pytest.raises(DatabaseConnectionError, match="mysql boom"):
        adapter.connect()


def test_postgres_connect_wraps_driver_errors(monkeypatch):
    config = _build_config(db_type="postgres", port=5432)
    adapter = PostgresAdapter(config)
    monkeypatch.setenv(config.password_env, "secret")
    monkeypatch.setattr("deerflow.nlp2sql.adapters.postgres.psycopg.connect", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("pg boom")))

    with pytest.raises(DatabaseConnectionError, match="pg boom"):
        adapter.connect()


def test_disconnect_clears_connection_reference(monkeypatch):
    config = _build_config(db_type="mysql", port=3306)
    adapter = MySQLAdapter(config)
    adapter._conn = MagicMock()

    adapter.disconnect()

    assert adapter._conn is None


def test_mysql_enum_parser_and_identifier_guards():
    assert _parse_mysql_enum("enum('paid','pending')") == ["paid", "pending"]
    assert mysql_require_identifier("orders_2026") == "orders_2026"
    assert mysql_require_identifier("订单2026") == "订单2026"
    assert mysql_require_identifier("2026_orders") == "2026_orders"
    with pytest.raises(ValueError, match="Unsafe identifier"):
        mysql_require_identifier("analytics.orders")


def test_postgres_identifier_guard():
    assert postgres_require_identifier("public_orders") == "public_orders"
    assert postgres_require_identifier("订单统计") == "订单统计"
    assert postgres_require_identifier("2026_orders") == "2026_orders"
    with pytest.raises(ValueError, match="Unsafe identifier"):
        postgres_require_identifier("public.orders")


def test_postgres_get_schema_defaults_to_public_schema():
    config = _build_config(db_type="postgres", schema_whitelist=None, table_whitelist=None)
    adapter = PostgresAdapter(config)

    result_sets = iter(
        [
            [
                {"table_schema": "public", "table_name": "orders", "table_comment": ""},
                {"table_schema": "analytics", "table_name": "daily_orders", "table_comment": ""},
            ],
            [
                {
                    "table_schema": "public",
                    "table_name": "orders",
                    "column_name": "id",
                    "ordinal_position": 1,
                    "data_type": "integer",
                    "udt_name": "int4",
                    "is_nullable": "NO",
                    "column_default": None,
                    "column_comment": "",
                }
            ],
            [{"table_schema": "public", "table_name": "orders", "column_name": "id"}],
            [],
        ]
    )

    class FakeCursor:
        description = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _sql: str, _params=None):
            return None

        def fetchall(self):
            return next(result_sets)

    adapter._cursor = lambda: FakeCursor()

    schema_doc = adapter.get_schema()

    assert [item["name"] for item in schema_doc["schemas"]] == ["public"]
