from __future__ import annotations

import logging
import time

import sqlglot

from deerflow.nlp2sql.adapters.factory import create_adapter
from deerflow.nlp2sql.errors import QuerySafetyError
from deerflow.nlp2sql.registry import DataSourceRegistry, get_data_source_registry
from deerflow.nlp2sql.safety.sql_validator import SqlValidator
from deerflow.nlp2sql.schema.service import SchemaService
from deerflow.nlp2sql.types import QueryExecutionResult, SchemaSearchHit, SqlValidationResult, ValidationMode

logger = logging.getLogger(__name__)


class DatabaseService:
    def __init__(
        self,
        registry: DataSourceRegistry | None = None,
        schema_service: SchemaService | None = None,
        validator: SqlValidator | None = None,
    ) -> None:
        self._registry = registry or get_data_source_registry()
        self._schema_service = schema_service or SchemaService()
        self._validator = validator or SqlValidator()

    def _dialect_name(self, adapter) -> str | None:
        dialect = getattr(adapter, "dialect", None)
        return dialect if isinstance(dialect, str) else None

    def with_adapter(self, data_source_id: str, fn):
        data_source = self._registry.get(data_source_id)
        adapter = create_adapter(data_source)
        primary_exc: Exception | None = None
        try:
            adapter.connect()
            return fn(adapter, data_source)
        except Exception as exc:
            primary_exc = exc
            raise
        finally:
            try:
                adapter.disconnect()
            except Exception:
                if primary_exc is None:
                    raise
                logger.warning("Failed to disconnect adapter for %s", data_source_id, exc_info=True)

    def get_schema(self, data_source_id: str, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = self._schema_service.get_cached_schema(data_source_id)
            if cached is not None:
                return cached
        return self.with_adapter(
            data_source_id,
            lambda adapter, data_source: self._schema_service.get_schema(adapter, data_source, force_refresh=force_refresh),
        )

    def search_schema(self, data_source_id: str, query: str, limit: int = 10) -> list[SchemaSearchHit]:
        schema_doc = self.get_schema(data_source_id)
        return self._schema_service.search_schema(schema_doc, query, limit=limit)

    def get_table_info(self, data_source_id: str, table_name: str, schema_name: str | None = None) -> dict:
        schema_doc = self.get_schema(data_source_id)
        return self._schema_service.get_table_info(schema_doc, table_name, schema=schema_name)

    def get_relationships(self, data_source_id: str, table_names: list[str]) -> list[dict]:
        schema_doc = self.get_schema(data_source_id)
        return self._schema_service.get_relationships(schema_doc, table_names)

    def get_enum_values(
        self,
        data_source_id: str,
        table_name: str,
        column_name: str,
        schema_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return self.with_adapter(
            data_source_id,
            lambda adapter, _data_source: adapter.get_enum_values(
                table_name,
                column_name,
                schema=schema_name,
                limit=limit,
            ),
        )

    def get_sample_rows(
        self,
        data_source_id: str,
        table_name: str,
        schema_name: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        return self.with_adapter(
            data_source_id,
            lambda adapter, _data_source: adapter.get_sample_rows(table_name, schema=schema_name, limit=limit),
        )

    def validate_sql(
        self,
        data_source_id: str,
        sql: str,
        mode: ValidationMode = ValidationMode.RELAXED,
    ) -> SqlValidationResult:
        data_source = self._registry.get(data_source_id)
        if mode == ValidationMode.STRICT:
            return self.with_adapter(
                data_source_id,
                lambda adapter, _data_source: self._validator.validate(
                    sql,
                    mode=mode,
                    readonly=data_source.readonly,
                    force_limit=data_source.max_rows,
                    allowed_schemas=data_source.schema_whitelist,
                    allowed_tables=data_source.table_whitelist,
                    adapter=adapter,
                ),
            )
        return self._validator.validate(
            sql,
            mode=mode,
            readonly=data_source.readonly,
            force_limit=data_source.max_rows,
            allowed_schemas=data_source.schema_whitelist,
            allowed_tables=data_source.table_whitelist,
            adapter=None,
        )

    def execute_sql(self, data_source_id: str, sql: str, params: list | None = None) -> QueryExecutionResult:
        def _run(adapter, data_source):
            validation = self._validator.validate(
                sql,
                mode=ValidationMode.STRICT,
                readonly=data_source.readonly,
                force_limit=data_source.max_rows,
                allowed_schemas=data_source.schema_whitelist,
                allowed_tables=data_source.table_whitelist,
                adapter=adapter,
            )
            if not validation.ok:
                details = validation.errors + validation.warnings
                raise QuerySafetyError("; ".join(details))

            execution_sql = validation.normalized_sql
            if validation.row_cap_applied:
                dialect = self._dialect_name(adapter)
                expression = sqlglot.parse_one(validation.normalized_sql, read=dialect)
                execution_sql = expression.limit(data_source.max_rows + 1, copy=True).sql(dialect=dialect)

            start = time.perf_counter()
            columns, rows = adapter.execute_query(
                execution_sql,
                params,
                max_rows=data_source.max_rows,
            )
            execution_ms = int((time.perf_counter() - start) * 1000)
            truncated = len(rows) > data_source.max_rows
            limited_rows = rows[: data_source.max_rows]
            if not columns and limited_rows:
                columns = list(limited_rows[0].keys())
            return QueryExecutionResult(
                sql=validation.normalized_sql,
                columns=columns,
                rows=limited_rows,
                row_count=len(limited_rows),
                fetched_row_count=len(rows),
                truncated=truncated,
                execution_ms=execution_ms,
                data_source_id=data_source.id,
            )

        return self.with_adapter(data_source_id, _run)

    def clear_schema_cache(self, data_source_id: str) -> None:
        self._schema_service.clear_cache(data_source_id)


_database_service: DatabaseService | None = None


def get_database_service() -> DatabaseService:
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service


def _reset_database_service() -> None:
    global _database_service
    _database_service = None
