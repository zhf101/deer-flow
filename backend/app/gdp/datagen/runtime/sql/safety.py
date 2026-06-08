"""数据库无关的 SQL 安全检查。"""

from __future__ import annotations

import re

from sqlglot import exp, parse, parse_one

from app.gdp.datagen.config.common.models import SqlOperation, SqlSourceSafety
from app.gdp.datagen.runtime.sql.errors import SqlExecutionRequestError, SqlSafetyError


def validate_sql_request(
    *,
    sql_text: str,
    expected_operation: SqlOperation,
    safety: SqlSourceSafety,
) -> SqlOperation:
    """分派到具体执行器前执行数据库无关校验。"""

    ensure_single_statement(sql_text)
    actual_operation = detect_operation(sql_text)
    if actual_operation != expected_operation:
        raise SqlExecutionRequestError(f"SQL operation mismatch: request={expected_operation.value}, actual={actual_operation.value}")
    if actual_operation in {SqlOperation.UPDATE, SqlOperation.DELETE} and safety.requireWhere:
        ensure_has_where(sql_text)
    return actual_operation


def ensure_single_statement(sql_text: str) -> None:
    """拒绝多个顶层 SQL 语句。"""

    try:
        statements = [statement for statement in parse(sql_text) if statement is not None]
    except Exception:
        # sqlglot 无法解析方言时，退回到保守的分号检查。
        # 允许末尾分号，但分号后不能有其他有效内容。
        stripped = sql_text.strip()
        if ";" in stripped.rstrip(";"):
            raise SqlExecutionRequestError("only one SQL statement is allowed")
        return

    if len(statements) > 1:
        raise SqlExecutionRequestError("only one SQL statement is allowed")


def detect_operation(sql_text: str) -> SqlOperation:
    """从 SQL 文本中识别增删改查操作类型。"""

    try:
        expression = parse_one(sql_text)
        if isinstance(expression, exp.Insert):
            return SqlOperation.INSERT
        if isinstance(expression, exp.Update):
            return SqlOperation.UPDATE
        if isinstance(expression, exp.Delete):
            return SqlOperation.DELETE
        if isinstance(expression, (exp.Select, exp.Union)) or expression.find(exp.Select):
            return SqlOperation.SELECT
    except Exception:
        pass

    first = (re.sub(r"^\s*/\*.*?\*/", "", sql_text, flags=re.S).strip().split() or [""])[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return SqlOperation(first)
    raise SqlExecutionRequestError(f"unsupported SQL operation: {first or '<empty>'}")


def ensure_has_where(sql_text: str) -> None:
    """要求 UPDATE 和 DELETE 语句必须包含顶层 WHERE 条件。"""

    try:
        expression = parse_one(sql_text)
        if expression.args.get("where") is not None:
            return
    except Exception:
        if _has_top_level_where(sql_text):
            return
    raise SqlSafetyError("UPDATE/DELETE 必须包含顶层 WHERE 条件。")


def _has_top_level_where(sql_text: str) -> bool:
    """在解析失败时保守识别顶层 WHERE，避免子查询条件绕过安全校验。"""

    depth = 0
    quote: str | None = None
    index = 0
    while index < len(sql_text):
        char = sql_text[index]
        if quote is not None:
            if char == quote:
                if index + 1 < len(sql_text) and sql_text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            elif char == "\\" and quote in {"'", '"'}:
                index += 2
                continue
            index += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if sql_text[index : index + 2] == "--":
            newline_index = sql_text.find("\n", index + 2)
            index = len(sql_text) if newline_index == -1 else newline_index + 1
            continue
        if sql_text[index : index + 2] == "/*":
            comment_end = sql_text.find("*/", index + 2)
            index = len(sql_text) if comment_end == -1 else comment_end + 2
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(depth - 1, 0)
            index += 1
            continue
        if depth == 0 and sql_text[index : index + 5].lower() == "where" and _is_word_boundary(sql_text, index - 1) and _is_word_boundary(sql_text, index + 5):
            return True
        index += 1
    return False


def _is_word_boundary(sql_text: str, index: int) -> bool:
    if index < 0 or index >= len(sql_text):
        return True
    return not (sql_text[index].isalnum() or sql_text[index] == "_")
