from __future__ import annotations

import importlib
from typing import Any

from deerflow.nlp2sql.errors import DatabaseConnectionError, DatabaseExecutionError
from deerflow.nlp2sql.types import DataSourceConfig

_SYSTEM_SCHEMAS = {
    "SYS",
    "SYSTEM",
    "SYSAUDITOR",
    "SYSSSO",
    "SYSDBA",
    "CTISYS",
}


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


class DMAdapter:
    dialect = "oracle"

    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self._driver = None
        self._conn = None
        self._current_schema: str | None = None

    def _load_driver(self):
        try:
            return importlib.import_module("dmPython")
        except ModuleNotFoundError as exc:
            raise DatabaseConnectionError(
                "DM driver is not installed. Add the 'dmPython' package to enable DM nlp2sql support."
            ) from exc

    def connect(self) -> None:
        if self._conn is not None:
            return
        driver = self._load_driver()
        self._driver = driver
        try:
            self._conn = driver.connect(
                self.config.username,
                self.config.get_password(),
                f"{self.config.host}:{self.config.port or 5236}/{self.config.database}",
            )
            if hasattr(self._conn, "autocommit"):
                self._conn.autocommit = True
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
            raise DatabaseConnectionError("DM connection is not initialized")
        return self._conn.cursor()

    def _rows_to_dicts(self, cursor, rows: list[Any]) -> tuple[list[str], list[dict[str, Any]]]:
        columns = [item[0] for item in cursor.description] if cursor.description else []
        if not columns:
            return [], []
        return columns, [dict(zip(columns, row, strict=False)) for row in rows]

    def _fetch_all(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        cursor = self._cursor()
        try:
            cursor.execute(sql, params or [])
            rows = list(cursor.fetchall())
            _, payload = self._rows_to_dicts(cursor, rows)
        finally:
            cursor.close()
        return payload

    def _current_owner(self) -> str:
        if self._current_schema is not None:
            return self._current_schema
        rows = self._fetch_all("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS CURRENT_SCHEMA FROM DUAL")
        self._current_schema = str(rows[0]["CURRENT_SCHEMA"]) if rows else self.config.username.upper()
        return self._current_schema

    def execute_query(
        self,
        sql: str,
        params: list[Any] | None = None,
        max_rows: int | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        try:
            cursor = self._cursor()
            try:
                cursor.execute(sql, params or [])
                if max_rows is None:
                    rows = list(cursor.fetchall())
                else:
                    rows = list(cursor.fetchmany(max_rows + 1))
                columns, payload = self._rows_to_dicts(cursor, rows)
            finally:
                cursor.close()
            if not columns and payload:
                columns = list(payload[0].keys())
            return columns, payload
        except Exception as exc:
            raise DatabaseExecutionError(str(exc)) from exc

    def explain_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
        _ = params
        try:
            cursor = self._cursor()
            try:
                cursor.execute(f"EXPLAIN {sql}")
                rows = list(cursor.fetchall())
                _, payload = self._rows_to_dicts(cursor, rows)
            finally:
                cursor.close()
            return {"database": self.config.database, "plan": payload}
        except Exception as exc:
            raise DatabaseExecutionError(str(exc)) from exc

    def get_schema(
        self,
        schema_whitelist: list[str] | None = None,
        table_whitelist: list[str] | None = None,
    ) -> dict[str, Any]:
        current_owner = self._current_owner()
        allowed_schemas = {item.lower() for item in (schema_whitelist or [current_owner])}
        allowed_tables = {item.lower() for item in (table_whitelist or [])}

        tables = self._fetch_all(
            """
            SELECT t.OWNER, t.TABLE_NAME, COALESCE(c.COMMENTS, '') AS TABLE_COMMENT
            FROM ALL_TABLES t
            LEFT JOIN ALL_TAB_COMMENTS c
              ON c.OWNER = t.OWNER
             AND c.TABLE_NAME = t.TABLE_NAME
            WHERE t.OWNER NOT IN ({system_schemas})
            ORDER BY t.OWNER, t.TABLE_NAME
            """.format(system_schemas=", ".join(f"'{name}'" for name in sorted(_SYSTEM_SCHEMAS)))
        )
        filtered_tables = [
            row
            for row in tables
            if row["OWNER"].lower() in allowed_schemas
            and (not allowed_tables or row["TABLE_NAME"].lower() in allowed_tables)
        ]
        allowed_pairs = {(row["OWNER"], row["TABLE_NAME"]) for row in filtered_tables}

        columns = self._fetch_all(
            """
            SELECT OWNER, TABLE_NAME, COLUMN_NAME, COLUMN_ID, DATA_TYPE, DATA_LENGTH,
                   DATA_PRECISION, DATA_SCALE, NULLABLE, DATA_DEFAULT
            FROM ALL_TAB_COLUMNS
            WHERE OWNER NOT IN ({system_schemas})
            ORDER BY OWNER, TABLE_NAME, COLUMN_ID
            """.format(system_schemas=", ".join(f"'{name}'" for name in sorted(_SYSTEM_SCHEMAS)))
        )
        comments = self._fetch_all(
            """
            SELECT OWNER, TABLE_NAME, COLUMN_NAME, COALESCE(COMMENTS, '') AS COLUMN_COMMENT
            FROM ALL_COL_COMMENTS
            WHERE OWNER NOT IN ({system_schemas})
            ORDER BY OWNER, TABLE_NAME, COLUMN_NAME
            """.format(system_schemas=", ".join(f"'{name}'" for name in sorted(_SYSTEM_SCHEMAS)))
        )
        primary_keys = self._fetch_all(
            """
            SELECT cons.OWNER, cons.TABLE_NAME, cols.COLUMN_NAME, cols.POSITION
            FROM ALL_CONSTRAINTS cons
            JOIN ALL_CONS_COLUMNS cols
              ON cons.CONSTRAINT_NAME = cols.CONSTRAINT_NAME
             AND cons.OWNER = cols.OWNER
            WHERE cons.CONSTRAINT_TYPE = 'P'
              AND cons.OWNER NOT IN ({system_schemas})
            ORDER BY cons.OWNER, cons.TABLE_NAME, cols.POSITION
            """.format(system_schemas=", ".join(f"'{name}'" for name in sorted(_SYSTEM_SCHEMAS)))
        )
        foreign_keys = self._fetch_all(
            """
            SELECT c.OWNER, c.TABLE_NAME, cc.COLUMN_NAME,
                   rc.OWNER AS REFERENCED_OWNER,
                   rc.TABLE_NAME AS REFERENCED_TABLE,
                   rcc.COLUMN_NAME AS REFERENCED_COLUMN,
                   cc.POSITION
            FROM ALL_CONSTRAINTS c
            JOIN ALL_CONS_COLUMNS cc
              ON c.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
             AND c.OWNER = cc.OWNER
            JOIN ALL_CONSTRAINTS rc
              ON c.R_CONSTRAINT_NAME = rc.CONSTRAINT_NAME
             AND c.R_OWNER = rc.OWNER
            JOIN ALL_CONS_COLUMNS rcc
              ON rc.CONSTRAINT_NAME = rcc.CONSTRAINT_NAME
             AND rc.OWNER = rcc.OWNER
             AND cc.POSITION = rcc.POSITION
            WHERE c.CONSTRAINT_TYPE = 'R'
              AND c.OWNER NOT IN ({system_schemas})
            ORDER BY c.OWNER, c.TABLE_NAME, cc.POSITION
            """.format(system_schemas=", ".join(f"'{name}'" for name in sorted(_SYSTEM_SCHEMAS)))
        )

        comment_map = {
            (row["OWNER"], row["TABLE_NAME"], row["COLUMN_NAME"]): row["COLUMN_COMMENT"]
            for row in comments
        }
        columns_by_table: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in columns:
            key = (row["OWNER"], row["TABLE_NAME"])
            if key not in allowed_pairs:
                continue
            default_value = row["DATA_DEFAULT"]
            columns_by_table.setdefault(key, []).append(
                {
                    "name": row["COLUMN_NAME"],
                    "data_type": row["DATA_TYPE"],
                    "column_type": _format_dm_type(row),
                    "nullable": row["NULLABLE"] == "Y",
                    "default": default_value.strip() if isinstance(default_value, str) else default_value,
                    "comment": comment_map.get((row["OWNER"], row["TABLE_NAME"], row["COLUMN_NAME"]), ""),
                    "ordinal_position": row["COLUMN_ID"],
                    "enum_values": [],
                }
            )

        primary_key_map: dict[tuple[str, str], list[str]] = {}
        for row in primary_keys:
            key = (row["OWNER"], row["TABLE_NAME"])
            if key not in allowed_pairs:
                continue
            primary_key_map.setdefault(key, []).append(row["COLUMN_NAME"])

        foreign_key_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in foreign_keys:
            key = (row["OWNER"], row["TABLE_NAME"])
            if key not in allowed_pairs:
                continue
            foreign_key_map.setdefault(key, []).append(
                {
                    "column": row["COLUMN_NAME"],
                    "referred_schema": row["REFERENCED_OWNER"],
                    "referred_table": row["REFERENCED_TABLE"],
                    "referred_column": row["REFERENCED_COLUMN"],
                }
            )

        schema_doc = {"database": self.config.database, "db_type": self.config.db_type.value, "schemas": []}
        schemas: dict[str, list[dict[str, Any]]] = {}
        for row in filtered_tables:
            key = (row["OWNER"], row["TABLE_NAME"])
            schemas.setdefault(row["OWNER"], []).append(
                {
                    "name": row["TABLE_NAME"],
                    "comment": row["TABLE_COMMENT"],
                    "columns": columns_by_table.get(key, []),
                    "primary_key": primary_key_map.get(key, []),
                    "foreign_keys": foreign_key_map.get(key, []),
                }
            )

        for schema_name in sorted(schemas):
            schema_doc["schemas"].append({"name": schema_name, "tables": sorted(schemas[schema_name], key=lambda item: item["name"])})
        return schema_doc

    def get_table_info(self, table_name: str, schema: str | None = None) -> dict[str, Any] | None:
        target_schema = schema or self._current_owner()
        schema_doc = self.get_schema(schema_whitelist=[target_schema], table_whitelist=[table_name])
        target_table = table_name.lower()
        for schema_item in schema_doc["schemas"]:
            if schema_item["name"].lower() != target_schema.lower():
                continue
            for table in schema_item["tables"]:
                if table["name"].lower() == target_table:
                    return {"schema": schema_item["name"], **table}
        return None

    def get_enum_values(
        self,
        table_name: str,
        column_name: str,
        schema: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        safe_schema = _quote_identifier(schema or self._current_owner())
        safe_table = _quote_identifier(table_name)
        safe_column = _quote_identifier(column_name)
        query = (
            f"SELECT value FROM ("
            f"SELECT DISTINCT {safe_column} AS value "
            f"FROM {safe_schema}.{safe_table} "
            f"WHERE {safe_column} IS NOT NULL"
            f") WHERE ROWNUM <= {int(limit)}"
        )
        _, rows = self.execute_query(query)
        return rows

    def get_sample_rows(
        self,
        table_name: str,
        schema: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        safe_schema = _quote_identifier(schema or self._current_owner())
        safe_table = _quote_identifier(table_name)
        query = f"SELECT * FROM (SELECT * FROM {safe_schema}.{safe_table}) WHERE ROWNUM <= {int(limit)}"
        _, rows = self.execute_query(query)
        return rows


def _format_dm_type(row: dict[str, Any]) -> str:
    data_type = str(row["DATA_TYPE"])
    data_length = row.get("DATA_LENGTH")
    precision = row.get("DATA_PRECISION")
    scale = row.get("DATA_SCALE")
    if data_type in {"DECIMAL", "NUMBER", "NUMERIC"}:
        if precision is not None and scale not in (None, 0):
            return f"{data_type}({precision},{scale})"
        if precision is not None:
            return f"{data_type}({precision})"
        return data_type
    if data_type in {"VARCHAR", "VARCHAR2", "CHAR"} and data_length:
        return f"{data_type}({data_length})"
    return data_type
