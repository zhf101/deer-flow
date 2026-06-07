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

    names: set[str] = set()
    for match in PLACEHOLDER_RE.finditer(sql_text):
        names.add(match.group(2).split(".")[-1])
    for match in NAMED_PARAM_RE.finditer(sql_text):
        names.add(match.group(2))
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
