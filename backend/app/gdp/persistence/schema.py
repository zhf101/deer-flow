"""SQLite compatibility migrations for GDP data-factory tables."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)


_SQLITE_COMPAT_COLUMNS: dict[str, dict[str, str]] = {
    "df_sql_template": {
        "datasource_code": "VARCHAR(128) NOT NULL DEFAULT ''",
        "datasource_type": "VARCHAR(64) NOT NULL DEFAULT ''",
    },
}


def ensure_sqlite_gdp_schema(conn: Connection) -> None:
    """Add GDP columns introduced after the initial SQLite tables existed.

    ``Base.metadata.create_all()`` creates missing tables but deliberately does
    not alter existing tables. Local SQLite installs therefore need small,
    idempotent compatibility migrations when ORM rows gain columns.
    """

    if conn.dialect.name != "sqlite":
        return

    table_names = set(conn.dialect.get_table_names(conn))
    for table_name, columns in _SQLITE_COMPAT_COLUMNS.items():
        if table_name not in table_names:
            continue

        existing_columns = {
            row[1]
            for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, column_ddl in columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}"))
            logger.info("Added missing SQLite column %s.%s", table_name, column_name)
