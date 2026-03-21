from __future__ import annotations

import re
from collections.abc import Iterable

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_search_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.strip().lower().replace("_", " ")
    return _WHITESPACE_RE.sub(" ", lowered)


def tokenize_search_text(value: str | None) -> list[str]:
    normalized = normalize_search_text(value)
    return [token for token in normalized.split(" ") if token]


def flatten_schema_document(schema_doc: dict) -> list[dict]:
    items: list[dict] = []
    for schema_item in schema_doc.get("schemas", []):
        schema_name = schema_item.get("name", "")
        for table in schema_item.get("tables", []):
            items.append(
                {
                    "schema_name": schema_name,
                    "table_name": table.get("name", ""),
                    "table_comment": table.get("comment", ""),
                    "columns": table.get("columns", []),
                    "foreign_keys": table.get("foreign_keys", []),
                }
            )
    return items


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
