"""轻量 JSONPath 提取工具。

支持场景配置中常用的 JSONPath 子集：
- ``$``          → 返回整个数据
- ``$.key``      → 顶层字段访问
- ``$.a.b.c``    → 多层嵌套字段访问
- ``$.a[0].b``   → 数组索引 + 嵌套字段

不引入 jsonpath-ng 等第三方依赖，仅覆盖 GDP 配置中实际使用的路径格式。
"""

from __future__ import annotations

import re
from typing import Any

# 匹配数组索引部分，如 "[0]"、"[12]"
_INDEX_RE = re.compile(r"\[(\d+)]")


def jsonpath_extract(data: Any, path: str) -> Any:
    """从 JSON 数据中按 JSONPath 路径提取值。

    Args:
        data: 原始数据（通常是 dict 或 list）
        path: JSONPath 表达式，如 "$.body.data.orderNo"

    Returns:
        提取到的值，路径不存在时返回 None。
    """
    if data is None:
        return None

    # "$" 表示返回整个数据
    if path == "$":
        return data

    parts = _parse_path(path)
    current = data
    for part in parts:
        if isinstance(part, int):
            # 数组索引访问
            if isinstance(current, list) and 0 <= part < len(current):
                current = current[part]
            else:
                return None
        elif isinstance(current, dict):
            # 字典字段访问
            current = current.get(part)
        else:
            return None
    return current


def _parse_path(path: str) -> list[str | int]:
    """将 JSONPath 字符串解析为路径段列表。

    示例：
        "$.foo.bar[0].baz" → ["foo", "bar", 0, "baz"]
        "$.body.data"      → ["body", "data"]
    """
    # 去掉开头的 "$." 或 "$"
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    result: list[str | int] = []
    # 按 "." 分割后，每段可能还包含 "[n]" 索引
    for segment in path.split("."):
        if not segment:
            continue
        # 检查是否包含数组索引
        parts = _INDEX_RE.split(segment)
        # parts 格式: ["fieldName", "0", "", "1", ""] 或 ["fieldName"]
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # 字段名部分
                if part:
                    result.append(part)
            else:
                # 索引部分（奇数位）
                result.append(int(part))

    return result
