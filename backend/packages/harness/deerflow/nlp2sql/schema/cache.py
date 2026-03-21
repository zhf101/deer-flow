from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _SchemaCacheEntry:
    schema_doc: dict
    expires_at: float


class SchemaCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, _SchemaCacheEntry] = {}

    def get(self, data_source_id: str) -> dict | None:
        with self._lock:
            entry = self._items.get(data_source_id)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                del self._items[data_source_id]
                return None
            return entry.schema_doc

    def set(self, data_source_id: str, schema_doc: dict, ttl_seconds: int = 300) -> None:
        with self._lock:
            self._items[data_source_id] = _SchemaCacheEntry(
                schema_doc=schema_doc,
                expires_at=time.time() + ttl_seconds,
            )

    def clear(self, data_source_id: str) -> None:
        with self._lock:
            self._items.pop(data_source_id, None)
