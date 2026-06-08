"""SQL 结果标准化和输出抽取。"""

from __future__ import annotations

import base64
import re
from typing import Any

from app.gdp.datagen.runtime.sql.models import SqlExecutionResult

_EXTRACTOR_RE = re.compile(r"^\$\{SQL_RESULT\((?P<path>.*)\)\}$")


def jsonable(value: Any) -> Any:
    """将常见数据库驱动返回值转换为 JSON 安全数据。"""

    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    return value


def apply_output_mapping(
    result: SqlExecutionResult,
    output_mapping: dict[str, str],
) -> SqlExecutionResult:
    """根据 ``${SQL_RESULT(...)}`` 表达式填充提取输出。"""

    if not output_mapping:
        return result

    context = {
        "columns": [item.model_dump(mode="json") for item in result.columns],
        "rows": result.rows,
        "row": result.row,
        "affectedRows": result.affectedRows,
        "lastInsertId": result.lastInsertId,
        "generatedKeys": result.generatedKeys,
    }
    extracted: dict[str, Any] = {}
    for name, expression in output_mapping.items():
        path = _extract_path(expression)
        extracted[name] = resolve_path(context, path) if path is not None else None
    return result.model_copy(update={"extractedOutputs": extracted})


def _extract_path(expression: str) -> str | None:
    match = _EXTRACTOR_RE.match((expression or "").strip())
    if match:
        return match.group("path").strip()
    if expression and not expression.startswith("${"):
        return expression.strip()
    return None


def resolve_path(obj: Any, path: str) -> Any:
    """从结果对象中解析 ``rows[0].id`` 这类点号和下标路径。"""

    if not path:
        return obj
    parts = re.split(r"\.|\[|\]", path.lstrip("$").lstrip("."))
    current = obj
    for part in parts:
        if not part:
            continue
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current
