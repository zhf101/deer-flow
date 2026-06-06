"""Lightweight SQL source parser for configuration metadata."""

from __future__ import annotations

import re

from app.gdp.datagen.config.common.models import InputFieldType, SqlOperation
from app.gdp.datagen.config.sqlsource.models import (
    SqlSourceParameter,
    SqlSourceParseResponse,
)

PLACEHOLDER_RE = re.compile(r"([#\$])\{\s*([\w.]+)\s*(?:,[^}]*)?\}")
NAMED_PARAM_RE = re.compile(r"(^|[^:]):([a-zA-Z_]\w*)")


def parse_sql_source(
    sql_text: str,
    parameters: list[SqlSourceParameter] | None = None,
) -> SqlSourceParseResponse:
    normalized_sql = _normalize_sql(sql_text)
    current_by_name = {item.name: item for item in parameters or []}
    parsed = [
        current_by_name.get(name)
        or SqlSourceParameter(
            name=name,
            type=InputFieldType.STRING,
            required=True,
        )
        for name in sorted(_parameter_names(sql_text))
    ]
    return SqlSourceParseResponse(
        normalizedSql=normalized_sql,
        operation=_detect_operation(normalized_sql),
        tables=[],
        resultFields=[],
        conditionFields=[],
        parameters=parsed,
    )


def _normalize_sql(sql_text: str) -> str:
    return re.sub(r"\s+", " ", sql_text.strip())


def _parameter_names(sql_text: str) -> set[str]:
    names: set[str] = set()
    for match in PLACEHOLDER_RE.finditer(sql_text):
        names.add(match.group(2).split(".")[-1])
    for match in NAMED_PARAM_RE.finditer(sql_text):
        names.add(match.group(2))
    return names


def _detect_operation(sql_text: str) -> SqlOperation:
    first = (sql_text.strip().split() or [""])[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return SqlOperation(first)
    return SqlOperation.SELECT
