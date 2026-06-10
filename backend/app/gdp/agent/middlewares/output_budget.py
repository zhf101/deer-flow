"""GDP Agent 工具输出预算工具。"""

from __future__ import annotations

import json
from typing import Any

PREVIEW_ITEM_LIMIT = 2
PREVIEW_FIELD_LIMIT = 8
PREVIEW_STRING_LIMIT = 256


def summarize_gdp_output(value: Any) -> dict[str, Any]:
    """把工具大输出压缩成适合进入 state/checkpoint 的摘要。"""

    return {
        "valueSchema": _summarize_schema(value),
        "valuePreview": _preview_value(value),
        "valueSize": {
            "charCount": len(_json_text(value)),
            "itemCount": _item_count(value),
        },
    }


def output_keys(value: Any) -> list[str]:
    """提取顶层输出键，便于反思节点和审计摘要使用。"""

    if isinstance(value, dict):
        return sorted(str(key) for key in value)
    return []


def _summarize_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "fields": {
                str(key): _summarize_schema(item)
                for key, item in list(value.items())[:PREVIEW_FIELD_LIMIT]
            },
        }
    if isinstance(value, list):
        first = value[0] if value else None
        return {
            "type": "array",
            "itemSchema": _summarize_schema(first) if first is not None else None,
        }
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"}


def _preview_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _preview_value(item)
            for key, item in list(value.items())[:PREVIEW_FIELD_LIMIT]
        }
    if isinstance(value, list):
        return [_preview_value(item) for item in value[:PREVIEW_ITEM_LIMIT]]
    if isinstance(value, str):
        return value[:PREVIEW_STRING_LIMIT]
    return value


def _item_count(value: Any) -> int | None:
    if isinstance(value, (list, dict)):
        return len(value)
    return None


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
