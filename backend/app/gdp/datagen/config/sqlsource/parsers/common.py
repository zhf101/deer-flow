"""SQL 解析器公共工具函数。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.gdp.datagen.config.common.models import InputFieldType, SqlOperation
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter

PLACEHOLDER_RE = re.compile(r"([#\$])\{\s*([\w.]+)\s*(?:,[^}]*)?\}")
NAMED_PARAM_RE = re.compile(r"(^|[^:]):([a-zA-Z_]\w*)")


def normalize_sql(sql_text: str) -> str:
    """标准化 SQL 文本：合并多余空白、去除标点前的空格。"""

    text = re.sub(r"\s+", " ", sql_text.strip())
    text = re.sub(r"\s+([,;)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    return text


def parameter_names(sql_text: str) -> set[str]:
    """提取 SQL 文本中所有参数占位符的名称。

    支持 ``#{name}``、``${name}``、``:name`` 三种格式。
    """

    return set(ordered_parameter_names(sql_text))


def ordered_parameter_names(sql_text: str) -> list[str]:
    """按 SQL 出现顺序提取参数名，并去除重复参数。"""

    matches: list[tuple[int, str]] = []
    for match in PLACEHOLDER_RE.finditer(sql_text):
        matches.append((match.start(), match.group(2).split(".")[-1]))
    for match in NAMED_PARAM_RE.finditer(sql_text):
        matches.append((match.start(2), match.group(2)))

    names: list[str] = []
    seen: set[str] = set()
    for _, name in sorted(matches, key=lambda item: item[0]):
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def merge_parameters(
    names: Iterable[str],
    current_parameters: list[SqlSourceParameter],
) -> list[SqlSourceParameter]:
    """将解析出的参数名与已有参数定义合并，保留已有元数据。"""

    current_by_name = {item.name: item for item in current_parameters}
    return [
        current_by_name.get(name)
        or SqlSourceParameter(
            name=name,
            type=InputFieldType.STRING,
            required=True,
        )
        for name in sorted(set(names))
    ]


def detect_operation(sql_text: str) -> SqlOperation:
    """根据 SQL 首关键词检测操作类型。"""

    first = (sql_text.strip().split() or [""])[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return SqlOperation(first)
    return SqlOperation.SELECT


def replace_parameters_with_question_marks(sql_text: str) -> str:
    """将 ``#{name}``、``${name}``、``:name`` 占位符统一替换为 ``?``。"""

    sql_text = PLACEHOLDER_RE.sub("?", sql_text)
    return NAMED_PARAM_RE.sub(lambda match: f"{match.group(1)}?", sql_text)


def replace_parameters_with_named(sql_text: str, aliases: dict[str, str] | None = None) -> str:
    """将 MyBatis 占位符统一替换为 ``:name`` 命名参数。

    该函数只负责输出可保存、可读、可绑定的 SQL 模板，不做 SQL 结构解析。
    ``aliases`` 用于把 foreach 中的局部变量映射回真实集合参数名。
    """

    alias_map = aliases or {}

    def replace_placeholder(match: re.Match[str]) -> str:
        raw_name = match.group(2).strip()
        root_name = raw_name.split(".", 1)[0]
        param_name = alias_map.get(root_name) or raw_name.split(".")[-1]
        return f":{param_name}"

    return PLACEHOLDER_RE.sub(replace_placeholder, sql_text)
