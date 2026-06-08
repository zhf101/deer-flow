"""场景执行运行时表达式解析。"""

from __future__ import annotations

import re
from typing import Any

_EXPRESSION_RE = re.compile(r"\$\{(?P<path>[^}]+)\}")


def resolve_value(value: Any, context: dict[str, Any]) -> Any:
    """解析值内部的运行时表达式。

    如果整个值正好是一个表达式，则返回原始对象值。
    如果表达式嵌在更长字符串中，则将解析值转为字符串后插值。
    """

    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    exact = _EXPRESSION_RE.fullmatch(stripped)
    if exact:
        return resolve_path(context, exact.group("path"))

    def replace(match: re.Match[str]) -> str:
        resolved = resolve_path(context, match.group("path"))
        return "" if resolved is None else str(resolved)

    return _EXPRESSION_RE.sub(replace, value)


def resolve_mapping(mapping: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {key: resolve_value(value, context) for key, value in mapping.items()}


def resolve_path(obj: Any, path: str) -> Any:
    """从运行时上下文解析点号和下标路径。"""

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
