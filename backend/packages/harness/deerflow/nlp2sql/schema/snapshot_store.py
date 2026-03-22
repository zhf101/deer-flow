from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier

from deerflow.nlp2sql.knowledge_config import KnowledgeConfig, get_knowledge_config

logger = logging.getLogger(__name__)

_SAFE_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _schema_checksum(schema_doc: dict[str, Any]) -> str:
    payload = json.dumps(schema_doc, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SchemaSnapshotStore:
    def __init__(self, config: KnowledgeConfig) -> None:
        self._config = config
        self._bootstrap_lock = threading.Lock()
        self._bootstrapped = False
        if not _SAFE_SCHEMA_RE.match(config.db_schema):
            raise ValueError(f"Invalid NLP2SQL knowledge schema name: {config.db_schema!r}")

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._config.dsn, row_factory=dict_row)

    def ensure_bootstrap(self) -> None:
        if self._bootstrapped:
            return
        with self._bootstrap_lock:
            if self._bootstrapped:
                return
            schema = Identifier(self._config.db_schema)
            with self._connect() as conn:
                conn.execute(SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
                conn.execute(
                    SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {}.schema_snapshots (
                            data_source_id TEXT PRIMARY KEY,
                            schema_doc JSONB NOT NULL,
                            schema_checksum TEXT NOT NULL,
                            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    ).format(schema)
                )
                conn.execute(
                    SQL(
                        """
                        CREATE INDEX IF NOT EXISTS schema_snapshots_refreshed_at_idx
                        ON {}.schema_snapshots (refreshed_at DESC)
                        """
                    ).format(schema)
                )
            self._bootstrapped = True

    def get_snapshot(self, data_source_id: str) -> dict[str, Any] | None:
        self.ensure_bootstrap()
        sql = SQL(
            """
            SELECT schema_doc
            FROM {}.schema_snapshots
            WHERE data_source_id = %s
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            row = conn.execute(sql, [data_source_id]).fetchone()
        if row is None:
            return None
        schema_doc = row.get("schema_doc")
        if isinstance(schema_doc, str):
            schema_doc = json.loads(schema_doc)
        if not isinstance(schema_doc, dict):
            raise ValueError(f"Invalid schema snapshot payload for data source '{data_source_id}'")
        return schema_doc

    def upsert_snapshot(self, data_source_id: str, schema_doc: dict[str, Any]) -> None:
        self.ensure_bootstrap()
        sql = SQL(
            """
            INSERT INTO {}.schema_snapshots (
                data_source_id,
                schema_doc,
                schema_checksum,
                refreshed_at
            ) VALUES (
                %s, %s::jsonb, %s, NOW()
            )
            ON CONFLICT (data_source_id)
            DO UPDATE SET
                schema_doc = EXCLUDED.schema_doc,
                schema_checksum = EXCLUDED.schema_checksum,
                refreshed_at = NOW()
            """
        ).format(Identifier(self._config.db_schema))
        with self._connect() as conn:
            conn.execute(
                sql,
                [
                    data_source_id,
                    json.dumps(schema_doc, ensure_ascii=False),
                    _schema_checksum(schema_doc),
                ],
            )
            conn.commit()

    def clear_snapshot(self, data_source_id: str) -> None:
        self.ensure_bootstrap()
        sql = SQL("DELETE FROM {}.schema_snapshots WHERE data_source_id = %s").format(
            Identifier(self._config.db_schema)
        )
        with self._connect() as conn:
            conn.execute(sql, [data_source_id])
            conn.commit()


def build_default_schema_snapshot_store() -> SchemaSnapshotStore | None:
    try:
        return SchemaSnapshotStore(get_knowledge_config())
    except RuntimeError:
        logger.info("NLP2SQL knowledge database is not configured; schema snapshot persistence is disabled")
        return None
