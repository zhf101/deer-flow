from __future__ import annotations

import ast
import json
from typing import Any

import pymysql

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
    return f"`{safe.replace('`', '``')}`"


def _parse_mysql_enum(column_type: str) -> list[str]:
    if not column_type.lower().startswith("enum("):
        return []
    inner = column_type[len("enum("):-1]
    try:
        parsed = ast.literal_eval("[" + inner + "]")
    except Exception:
        return []
    return [str(item) for item in parsed]


class MySQLAdapter:
    dialect = "mysql"
    explain_prefix = "EXPLAIN FORMAT=JSON"

    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self._conn: pymysql.Connection | None = None

    def connect(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = pymysql.connect(
                host=self.config.host,
                port=self.config.port or 3306,
                user=self.config.username,
                password=self.config.get_password(),
                database=self.config.database,
                connect_timeout=self.config.connect_timeout_seconds,
                read_timeout=self.config.query_timeout_seconds,
                write_timeout=self.config.query_timeout_seconds,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
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
            raise DatabaseConnectionError("MySQL connection is not initialized")
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
                columns = [item[0] for item in cursor.description] if cursor.description else []
            if not columns and rows:
                columns = list(rows[0].keys())
            return columns, rows
        except Exception as exc:
            raise DatabaseExecutionError(str(exc)) from exc

    def explain_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        try:
            with self._cursor() as cursor:
                cursor.execute(f"{self.explain_prefix} {sql}", params or [])
                rows = list(cursor.fetchall())
            if self.explain_prefix.upper() == "EXPLAIN FORMAT=JSON":
                row = rows[0] if rows else {}
                explain_payload = row.get("EXPLAIN")
                if isinstance(explain_payload, str):
                    try:
                        explain_payload = json.loads(explain_payload)
                    except json.JSONDecodeError:
                        pass
                return {"database": self.config.database, "plan": explain_payload or row}
            return {"database": self.config.database, "plan": rows}
        except Exception as exc:
            raise DatabaseExecutionError(str(exc)) from exc

    def get_schema(
        self,
        schema_whitelist: list[str] | None = None,
        table_whitelist: list[str] | None = None,
    ) -> dict[str, Any]:
        allowed_schemas = set(schema_whitelist or [self.config.database])
        allowed_tables = set(table_whitelist or [])

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT table_schema, table_name, COALESCE(table_comment, '') AS table_comment
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE' AND table_schema = %s
                ORDER BY table_name
                """,
                [self.config.database],
            )
            tables = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT table_schema, table_name, column_name, ordinal_position, data_type, column_type,
                       is_nullable, column_default, COALESCE(column_comment, '') AS column_comment
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                [self.config.database],
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
                WHERE t.table_schema = %s AND t.constraint_type = 'PRIMARY KEY'
                ORDER BY k.table_name, k.ordinal_position
                """,
                [self.config.database],
            )
            primary_keys = list(cursor.fetchall())

            cursor.execute(
                """
                SELECT table_schema, table_name, column_name,
                       referenced_table_schema, referenced_table_name, referenced_column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = %s AND referenced_table_name IS NOT NULL
                ORDER BY table_name, ordinal_position
                """,
                [self.config.database],
            )
            foreign_keys = list(cursor.fetchall())

        filtered_tables = [
            table
            for table in tables
            if table["table_schema"] in allowed_schemas and (not allowed_tables or table["table_name"] in allowed_tables)
        ]
        allowed_table_names = {table["table_name"] for table in filtered_tables}

        columns_by_table: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for column in columns:
            key = (column["table_schema"], column["table_name"])
            if column["table_name"] not in allowed_table_names:
                continue
            columns_by_table.setdefault(key, []).append(
                {
                    "name": column["column_name"],
                    "data_type": column["data_type"],
                    "column_type": column["column_type"],
                    "nullable": column["is_nullable"] == "YES",
                    "default": column["column_default"],
                    "comment": column["column_comment"],
                    "ordinal_position": column["ordinal_position"],
                    "enum_values": _parse_mysql_enum(column["column_type"]),
                }
            )

        primary_key_map: dict[tuple[str, str], list[str]] = {}
        for item in primary_keys:
            key = (item["table_schema"], item["table_name"])
            if item["table_name"] not in allowed_table_names:
                continue
            primary_key_map.setdefault(key, []).append(item["column_name"])

        foreign_key_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in foreign_keys:
            key = (item["table_schema"], item["table_name"])
            if item["table_name"] not in allowed_table_names:
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
        schemas: dict[str, list[dict[str, Any]]] = {}
        for table in filtered_tables:
            key = (table["table_schema"], table["table_name"])
            schemas.setdefault(table["table_schema"], []).append(
                {
                    "name": table["table_name"],
                    "comment": table["table_comment"],
                    "columns": columns_by_table.get(key, []),
                    "primary_key": primary_key_map.get(key, []),
                    "foreign_keys": foreign_key_map.get(key, []),
                }
            )

        for schema_name in sorted(schemas):
            schema_doc["schemas"].append({"name": schema_name, "tables": sorted(schemas[schema_name], key=lambda item: item["name"])})
        return schema_doc

    def get_table_info(self, table_name: str, schema: str | None = None) -> dict[str, Any] | None:
        target_schema = schema or self.config.database
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
        target_schema = schema or self.config.database
        table_info = self.get_table_info(table_name, target_schema)
        if table_info is None:
            return []
        for column in table_info["columns"]:
            if column["name"] == column_name and column.get("enum_values"):
                return [{"value": value} for value in column["enum_values"][:limit]]

        safe_table = _quote_identifier(table_name)
        safe_column = _quote_identifier(column_name)
        safe_schema = _quote_identifier(target_schema)
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
        safe_table = _quote_identifier(table_name)
        safe_schema = _quote_identifier(schema or self.config.database)
        query = f"SELECT * FROM {safe_schema}.{safe_table} LIMIT {int(limit)}"
        _, rows = self.execute_query(query)
        return rows
