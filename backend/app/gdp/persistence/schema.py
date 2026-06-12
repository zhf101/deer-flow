"""GDP SQLite 开发库结构补齐。"""

from __future__ import annotations

import logging
from importlib import import_module

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.sqltypes import Boolean, DateTime, Float, Integer, Text

from deerflow.persistence.base import Base

logger = logging.getLogger(__name__)


def ensure_sqlite_gdp_schema(conn: Connection) -> None:
    """补齐 SQLite 旧表缺失的 GDP 字段。

    SQLAlchemy 的 create_all 只会创建不存在的表，不会为已存在表新增字段。
    当前处于开发阶段，旧数据只需要保持可读，因此缺失的非空字段使用保守默认值。
    """

    if conn.dialect.name != "sqlite":
        return

    import_module("deerflow.persistence.models")

    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if not table.name.startswith("df_") or table.name not in existing_tables:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            ddl = _add_column_sql(table.name, column, conn)
            logger.warning("补齐 GDP SQLite 字段: %s.%s", table.name, column.name)
            conn.execute(text(ddl))


def _add_column_sql(table_name: str, column: Column, conn: Connection) -> str:
    column_type = column.type.compile(dialect=conn.dialect)
    parts = [
        f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}"',
        column_type,
    ]

    default_sql = _default_sql(column)
    if not column.nullable:
        parts.append("NOT NULL")
        if default_sql is not None:
            parts.append(f"DEFAULT {default_sql}")
    elif default_sql is not None and _should_default_nullable_column(column):
        parts.append(f"DEFAULT {default_sql}")

    return " ".join(parts)


def _default_sql(column: Column) -> str | None:
    name = column.name
    if isinstance(column.type, Boolean):
        return "0"
    if isinstance(column.type, Integer):
        return "0"
    if isinstance(column.type, Float):
        return "0"
    if isinstance(column.type, DateTime):
        return "'1970-01-01 00:00:00'"
    if isinstance(column.type, Text):
        if name.endswith("_json") or name in {"tags_json", "side_effects_json", "preconditions_json"}:
            return f"'{_json_default(name)}'"
        return "''"
    if name == "capability_type":
        return "'QUERY'"
    if name == "status":
        return "'ENABLED'"
    if name == "version_status":
        return "'DRAFT'"
    return "''"


def _json_default(name: str) -> str:
    if name == "success_criteria_json":
        return "null"
    if name in {
        "value_json",
        "input_snapshot_json",
        "result_summary_json",
        "result_payload_json",
        "result_ref_json",
        "token_usage_json",
        "request_mapping_json",
        "request_snapshot_json",
        "output_mapping_json",
        "safety_json",
        "batch_config_json",
        "error_policy_json",
        "timeout_config_json",
        "response_handling_json",
    }:
        return "{}"
    return "[]"


def _should_default_nullable_column(column: Column) -> bool:
    return column.name.endswith("_json")
