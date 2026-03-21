from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row

from deerflow.nlp2sql.errors import DatabaseConnectionError, DatabaseExecutionError
from deerflow.nlp2sql.types import DataSourceConfig


def _require_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError(f"Unsafe identifier: {value!r}")
    if "." in value:
        raise ValueError(f"Unsafe identifier: {value!r}")
    return value


def _quote_identifier(value: str) -> str:
    safe = _require_identifier(value)
    escaped = safe.replace('"', '""')
    return f'"{escaped}"'


class PostgresAdapter:
    dialect = "postgres"

    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self._conn: psycopg.Connection | None = None

    def connect(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = psycopg.connect(
                host=self.config.host,
                port=self.config.port or 5432,
                user=self.config.username,
                password=self.config.get_password(),
                dbname=self.config.database,
                connect_timeout=self.config.connect_timeout_seconds,
                autocommit=True,
                row_factory=dict_row,
            )
        except Exception as exc:
            raise DatabaseConnectionError(str(exc)) from exc

    def disconnect(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.close()
        finally:
            self._conn = None

    def _cursor(self):
        if self._conn is None:
            raise DatabaseConnectionError("PostgreSQL connection is not initialized")
        return self._conn.cursor()

    def execute_query(
        self,
        sql: str,
        params: list[Any] | None = None,
        max_rows: int | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        try:
            with self._cursor() as cursor:
                cursor.execute(sql, params or [])
                if max_rows is None:
                    rows = list(cursor.fetchall())
                else:
                    rows = list(cursor.fetchmany(max_rows + 1))
                columns = [item.name for item in cursor.description] if cursor.description else []
            if not columns and rows:
                columns = list(rows[0].keys())
            return columns, rows
        except Exception as exc:
            raise DatabaseExecutionError(str(exc)) from exc

    def explain_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        try:
            with self._cursor() as cursor:
                cursor.execute(f"EXPLAIN (FORMAT JSON) {sql}", params or [])
                row = cursor.fetchone() or {}
            explain_payload = row.get("QUERY PLAN")
            if isinstance(explain_payload, str):
                try:
                    explain_payload = json.loads(explain_payload)
                except json.JSONDecodeError:
                    pass
            return {"database": self.config.database, "plan": explain_payload or row}
        except Exception as exc:
            raise DatabaseExecutionError(str(exc)) from exc

    def get_schema(
        self,
        schema_whitelist: list[str] | None = None,
        table_whitelist: list[str] | None = None,
    ) -> dict[str, Any]:
        allowed_schemas = set(schema_whitelist or ["public"])
        allowed_tables = set(table_whitelist or [])
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT t.table_schema, t.table_name,
                       COALESCE(obj_description((quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass), '') AS table_comment
                FROM information_schema.tables t
                WHERE t.table_type = 'BASE TABLE'
                  AND t.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY t.table_schema, t.table_name
                """
            )
            tables = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position, c.data_type, c.udt_name,
                       c.is_nullable, c.column_default,
                       COALESCE(col_description((quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass, c.ordinal_position), '') AS column_comment
                FROM information_schema.columns c
                WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
                """
            )
            columns = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT k.table_schema, k.table_name, k.column_name
                FROM information_schema.table_constraints t
                JOIN information_schema.key_column_usage k
                  ON t.constraint_name = k.constraint_name
                 AND t.table_schema = k.table_schema
                 AND t.table_name = k.table_name
                WHERE t.constraint_type = 'PRIMARY KEY'
                  AND t.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY k.table_schema, k.table_name, k.ordinal_position
                """
            )
            primary_keys = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT tc.table_schema, tc.table_name, kcu.column_name,
                       ccu.table_schema AS referenced_table_schema,
                       ccu.table_name AS referenced_table_name,
                       ccu.column_name AS referenced_column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.constraint_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
                """
            )
            foreign_keys = list(cursor.fetchall())

        filtered_tables = [
            table
            for table in tables
            if (not allowed_schemas or table["table_schema"] in allowed_schemas)
            and (not allowed_tables or table["table_name"] in allowed_tables)
        ]
        allowed_pairs = {(table["table_schema"], table["table_name"]) for table in filtered_tables}

        columns_by_table: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for column in columns:
            key = (column["table_schema"], column["table_name"])
            if key not in allowed_pairs:
                continue
            columns_by_table.setdefault(key, []).append(
                {
                    "name": column["column_name"],
                    "data_type": column["data_type"],
                    "column_type": column["udt_name"],
                    "nullable": column["is_nullable"] == "YES",
                    "default": column["column_default"],
                    "comment": column["column_comment"],
                    "ordinal_position": column["ordinal_position"],
                    "enum_values": [],
                }
            )

        primary_key_map: dict[tuple[str, str], list[str]] = {}
        for item in primary_keys:
            key = (item["table_schema"], item["table_name"])
            if key not in allowed_pairs:
                continue
            primary_key_map.setdefault(key, []).append(item["column_name"])

        foreign_key_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in foreign_keys:
            key = (item["table_schema"], item["table_name"])
            if key not in allowed_pairs:
                continue
            foreign_key_map.setdefault(key, []).append(
                {
                    "column": item["column_name"],
                    "referred_schema": item["referenced_table_schema"],
                    "referred_table": item["referenced_table_name"],
                    "referred_column": item["referenced_column_name"],
                }
            )

        schema_doc = {"database": self.config.database, "db_type": self.config.db_type.value, "schemas": []}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for table in filtered_tables:
            key = (table["table_schema"], table["table_name"])
            grouped.setdefault(table["table_schema"], []).append(
                {
                    "name": table["table_name"],
                    "comment": table["table_comment"],
                    "columns": columns_by_table.get(key, []),
                    "primary_key": primary_key_map.get(key, []),
                    "foreign_keys": foreign_key_map.get(key, []),
                }
            )

        for schema_name in sorted(grouped):
            schema_doc["schemas"].append({"name": schema_name, "tables": sorted(grouped[schema_name], key=lambda item: item["name"])})
        return schema_doc

    def get_table_info(self, table_name: str, schema: str | None = None) -> dict[str, Any] | None:
        target_schema = schema or "public"
        schema_doc = self.get_schema(schema_whitelist=[target_schema], table_whitelist=[table_name])
        for schema_item in schema_doc["schemas"]:
            if schema_item["name"] != target_schema:
                continue
            for table in schema_item["tables"]:
                if table["name"] == table_name:
                    return {"schema": schema_item["name"], **table}
        return None

    def get_enum_values(
        self,
        table_name: str,
        column_name: str,
        schema: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        target_schema = schema or "public"
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT e.enumlabel AS value
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                JOIN pg_attribute a ON a.atttypid = t.oid
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s
                ORDER BY e.enumsortorder
                """,
                [target_schema, table_name, column_name],
            )
            enum_rows = list(cursor.fetchall())
        if enum_rows:
            return enum_rows[:limit]

        safe_schema = _quote_identifier(target_schema)
        safe_table = _quote_identifier(table_name)
        safe_column = _quote_identifier(column_name)
        query = (
            f"SELECT DISTINCT {safe_column} AS value "
            f"FROM {safe_schema}.{safe_table} "
            f"WHERE {safe_column} IS NOT NULL "
            f"LIMIT {int(limit)}"
        )
        _, rows = self.execute_query(query)
        return rows

    def get_sample_rows(
        self,
        table_name: str,
        schema: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        safe_schema = _quote_identifier(schema or "public")
        safe_table = _quote_identifier(table_name)
        query = f"SELECT * FROM {safe_schema}.{safe_table} LIMIT {int(limit)}"
        _, rows = self.execute_query(query)
        return rows
