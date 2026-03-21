from __future__ import annotations

from difflib import SequenceMatcher

from deerflow.nlp2sql.errors import SchemaLookupError
from deerflow.nlp2sql.schema.cache import SchemaCache
from deerflow.nlp2sql.schema.enhancer import flatten_schema_document, normalize_search_text, tokenize_search_text
from deerflow.nlp2sql.types import DataSourceConfig, SchemaSearchHit


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
    def __init__(self, cache: SchemaCache | None = None) -> None:
        self._cache = cache or SchemaCache()

    def get_cached_schema(self, data_source_id: str) -> dict | None:
        return self._cache.get(data_source_id)

    def get_schema(self, adapter, data_source: DataSourceConfig, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = self._cache.get(data_source.id)
            if cached is not None:
                return cached
        schema_doc = adapter.get_schema(
            schema_whitelist=data_source.schema_whitelist,
            table_whitelist=data_source.table_whitelist,
        )
        self._cache.set(data_source.id, schema_doc)
        return schema_doc

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
        for schema_item in schema_doc.get("schemas", []):
            if schema is not None and schema_item.get("name") != schema:
                continue
            for table in schema_item.get("tables", []):
                if table.get("name") == table_name:
                    return {"schema": schema_item.get("name"), **table}
        raise SchemaLookupError(f"Table '{table_name}' not found")

    def get_relationships(self, schema_doc: dict, table_names: list[str]) -> list[dict]:
        selected = set(table_names)
        relationships: list[dict] = []
        for schema_item in schema_doc.get("schemas", []):
            schema_name = schema_item.get("name")
            for table in schema_item.get("tables", []):
                table_name = table.get("name")
                if table_name not in selected:
                    continue
                for fk in table.get("foreign_keys", []):
                    relationships.append(
                        {
                            "schema": schema_name,
                            "table": table_name,
                            "column": fk.get("column"),
                            "referred_schema": fk.get("referred_schema"),
                            "referred_table": fk.get("referred_table"),
                            "referred_column": fk.get("referred_column"),
                            "in_selection": fk.get("referred_table") in selected,
                        }
                    )
        return relationships

    def clear_cache(self, data_source_id: str) -> None:
        self._cache.clear(data_source_id)
