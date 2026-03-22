from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any, Callable

from deerflow.nlp2sql.errors import SchemaLookupError
from deerflow.nlp2sql.schema.cache import SchemaCache
from deerflow.nlp2sql.schema.enhancer import flatten_schema_document, normalize_search_text, tokenize_search_text
from deerflow.nlp2sql.schema.snapshot_store import SchemaSnapshotStore, build_default_schema_snapshot_store
from deerflow.nlp2sql.types import DataSourceConfig, SchemaSearchHit

logger = logging.getLogger(__name__)
_DEFAULT_SNAPSHOT_STORE = object()


def _score_match(query: str, target: str) -> float:
    query_norm = normalize_search_text(query)
    target_norm = normalize_search_text(target)
    if not query_norm or not target_norm:
        return 0.0
    if query_norm == target_norm:
        return 1.0
    if query_norm in target_norm:
        return 0.95
    query_tokens = tokenize_search_text(query)
    target_tokens = tokenize_search_text(target)
    if query_tokens and any(token in target_tokens for token in query_tokens):
        return 0.82
    return SequenceMatcher(None, query_norm, target_norm).ratio()


class SchemaService:
    def __init__(
        self,
        cache: SchemaCache | None = None,
        snapshot_store: SchemaSnapshotStore | None | object = _DEFAULT_SNAPSHOT_STORE,
        schema_note_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._cache = cache or SchemaCache()
        if snapshot_store is _DEFAULT_SNAPSHOT_STORE:
            snapshot_store = build_default_schema_snapshot_store()
        self._snapshot_store: SchemaSnapshotStore | None = snapshot_store
        self._schema_note_provider = schema_note_provider

    def get_cached_schema(self, data_source_id: str) -> dict | None:
        cached = self._cache.get(data_source_id)
        if cached is not None:
            return cached
        if self._snapshot_store is None:
            return None
        try:
            snapshot = self._snapshot_store.get_snapshot(data_source_id)
        except Exception:
            logger.warning("Failed to load persisted schema snapshot for %s", data_source_id, exc_info=True)
            return None
        if snapshot is None:
            return None
        merged = self._apply_schema_notes(snapshot, data_source_id)
        self._cache.set(data_source_id, merged)
        return merged

    def get_schema(self, adapter, data_source: DataSourceConfig, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = self.get_cached_schema(data_source.id)
            if cached is not None:
                return cached
        schema_doc = adapter.get_schema(
            schema_whitelist=data_source.schema_whitelist,
            table_whitelist=data_source.table_whitelist,
        )
        self._cache.set(data_source.id, schema_doc)
        if self._snapshot_store is not None:
            try:
                self._snapshot_store.upsert_snapshot(data_source.id, schema_doc)
            except Exception:
                logger.warning("Failed to persist schema snapshot for %s", data_source.id, exc_info=True)
        merged = self._apply_schema_notes(schema_doc, data_source.id)
        self._cache.set(data_source.id, merged)
        return merged

    def search_schema(self, schema_doc: dict, query: str, limit: int = 10) -> list[SchemaSearchHit]:
        hits: list[SchemaSearchHit] = []
        for table in flatten_schema_document(schema_doc):
            table_name = table["table_name"]
            schema_name = table["schema_name"]
            table_comment = table["table_comment"]

            table_score = max(_score_match(query, table_name), _score_match(query, table_comment))
            if table_score >= 0.45:
                hits.append(
                    SchemaSearchHit(
                        schema_name=schema_name,
                        table_name=table_name,
                        match_type="table",
                        score=table_score,
                        snippet=table_comment or table_name,
                    )
                )

            for column in table["columns"]:
                column_name = column.get("name", "")
                column_comment = column.get("comment", "")
                score = max(_score_match(query, column_name), _score_match(query, column_comment))
                if score < 0.45:
                    continue
                hits.append(
                    SchemaSearchHit(
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=column_name,
                        match_type="column",
                        score=score,
                        snippet=column_comment or column_name,
                    )
                )

        hits.sort(key=lambda hit: (-hit.score, hit.schema_name, hit.table_name, hit.column_name or ""))
        return hits[:limit]

    def get_table_info(self, schema_doc: dict, table_name: str, schema: str | None = None) -> dict:
        target_table = table_name.casefold()
        target_schema = schema.casefold() if schema is not None else None
        fallback_match: dict | None = None
        for schema_item in schema_doc.get("schemas", []):
            schema_name = schema_item.get("name")
            if schema is not None and schema_name != schema:
                if target_schema is None or not isinstance(schema_name, str) or schema_name.casefold() != target_schema:
                    continue
            for table in schema_item.get("tables", []):
                candidate_name = table.get("name")
                if candidate_name == table_name:
                    return {"schema": schema_name, **table}
                if (
                    fallback_match is None
                    and isinstance(candidate_name, str)
                    and candidate_name.casefold() == target_table
                ):
                    fallback_match = {"schema": schema_name, **table}
        if fallback_match is not None:
            return fallback_match
        raise SchemaLookupError(f"Table '{table_name}' not found")

    def get_relationships(self, schema_doc: dict, table_names: list[str]) -> list[dict]:
        selected = set(table_names)
        selected_folded = {name.casefold() for name in table_names}
        relationships: list[dict] = []
        for schema_item in schema_doc.get("schemas", []):
            schema_name = schema_item.get("name")
            for table in schema_item.get("tables", []):
                table_name = table.get("name")
                table_key = table_name.casefold() if isinstance(table_name, str) else ""
                if table_name not in selected and table_key not in selected_folded:
                    continue
                for fk in table.get("foreign_keys", []):
                    referred_table = fk.get("referred_table")
                    referred_key = referred_table.casefold() if isinstance(referred_table, str) else ""
                    relationships.append(
                        {
                            "schema": schema_name,
                            "table": table_name,
                            "column": fk.get("column"),
                            "referred_schema": fk.get("referred_schema"),
                            "referred_table": referred_table,
                            "referred_column": fk.get("referred_column"),
                            "in_selection": referred_table in selected or referred_key in selected_folded,
                        }
                    )
        return relationships

    def clear_cache(self, data_source_id: str) -> None:
        self._cache.clear(data_source_id)
        if self._snapshot_store is None:
            return
        self._snapshot_store.clear_snapshot(data_source_id)

    def _apply_schema_notes(self, schema_doc: dict, data_source_id: str) -> dict:
        notes = self._list_schema_notes(data_source_id)
        if not notes:
            return self._initialize_comment_metadata(schema_doc)

        merged = self._initialize_comment_metadata(schema_doc)
        table_notes = {
            (note["schema_name"], note["table_name"]): note
            for note in notes
            if not note.get("column_name")
        }
        column_notes = {
            (note["schema_name"], note["table_name"], note["column_name"]): note
            for note in notes
            if note.get("column_name")
        }

        for schema_item in merged.get("schemas", []):
            schema_name = schema_item.get("name")
            if not isinstance(schema_name, str):
                continue
            for table in schema_item.get("tables", []):
                table_name = table.get("name")
                if not isinstance(table_name, str):
                    continue

                table_note = table_notes.get((schema_name, table_name))
                if table_note is not None:
                    table["user_comment"] = table_note["comment"]
                    table["comment"] = table_note["comment"]
                    table["comment_source"] = "user"
                    table["note_item_id"] = table_note["item_id"]

                for column in table.get("columns", []):
                    column_name = column.get("name")
                    if not isinstance(column_name, str):
                        continue
                    column_note = column_notes.get((schema_name, table_name, column_name))
                    if column_note is None:
                        continue
                    column["user_comment"] = column_note["comment"]
                    column["comment"] = column_note["comment"]
                    column["comment_source"] = "user"
        return merged

    def _list_schema_notes(self, data_source_id: str) -> list[dict[str, Any]]:
        if self._schema_note_provider is None:
            return []
        try:
            notes = self._schema_note_provider(data_source_id)
        except Exception:
            logger.warning("Failed to load schema notes for %s", data_source_id, exc_info=True)
            return []

        normalized: list[dict[str, Any]] = []
        for note in notes:
            metadata = dict(note.get("metadata") or {})
            schema_name = metadata.get("schema_name")
            table_name = metadata.get("table_name")
            column_name = metadata.get("column_name")
            comment = note.get("content")
            item_id = note.get("id")
            if not isinstance(schema_name, str) or not schema_name:
                continue
            if not isinstance(table_name, str) or not table_name:
                continue
            if not isinstance(comment, str):
                continue
            normalized.append(
                {
                    "item_id": item_id if isinstance(item_id, str) else None,
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "column_name": column_name if isinstance(column_name, str) and column_name else None,
                    "comment": comment,
                }
            )
        return normalized

    @staticmethod
    def _initialize_comment_metadata(schema_doc: dict) -> dict:
        merged = {"database": schema_doc.get("database"), "db_type": schema_doc.get("db_type"), "schemas": []}
        for schema_item in schema_doc.get("schemas", []):
            schema_payload = {"name": schema_item.get("name", ""), "tables": []}
            for table in schema_item.get("tables", []):
                source_comment = str(table.get("comment") or "")
                table_payload = {
                    **table,
                    "comment": source_comment,
                    "source_comment": source_comment,
                    "user_comment": None,
                    "comment_source": "database" if source_comment else "none",
                    "note_item_id": None,
                    "columns": [],
                }
                for column in table.get("columns", []):
                    source_column_comment = str(column.get("comment") or "")
                    table_payload["columns"].append(
                        {
                            **column,
                            "comment": source_column_comment,
                            "source_comment": source_column_comment,
                            "user_comment": None,
                            "comment_source": "database" if source_column_comment else "none",
                        }
                    )
                schema_payload["tables"].append(table_payload)
            merged["schemas"].append(schema_payload)
        return merged
