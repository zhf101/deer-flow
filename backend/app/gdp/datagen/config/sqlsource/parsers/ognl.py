"""MyBatis 动态 SQL 的 OGNL 安全求值器。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OgnlEvaluation:
    """OGNL 表达式求值结果。"""

    known: bool
    value: bool


def evaluate_ognl(expression: str, values: dict[str, Any]) -> OgnlEvaluation:
    """对保守的 OGNL 子集进行安全求值。

    不支持的表达式返回 ``known=False``，调用方可保留该 SQL 分支，
    避免遗漏可能的数据血缘或审计元数据。
    """

    python_expression = _to_python_expression(expression)
    try:
        node = ast.parse(python_expression, mode="eval")
        value = _eval_node(node.body, values)
    except Exception:
        return OgnlEvaluation(known=False, value=True)
    return OgnlEvaluation(known=True, value=bool(value))


def _to_python_expression(expression: str) -> str:
    """将 OGNL 表达式转换为等价的 Python 表达式。"""

    expression = expression.strip()
    expression = re.sub(r"\bnull\b", "None", expression)
    expression = re.sub(r"\btrue\b", "True", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bfalse\b", "False", expression, flags=re.IGNORECASE)
    expression = re.sub(r"(?<![=!<>])!(?!=)", " not ", expression)
    return expression


def _eval_node(node: ast.AST, values: dict[str, Any]) -> Any:
    """递归求值 AST 节点。"""

    if isinstance(node, ast.BoolOp):
        items = [_eval_node(value, values) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(items)
        if isinstance(node.op, ast.Or):
            return any(items)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, values)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, values)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval_node(comparator, values)
            if not _compare(left, op, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError(f"OGNL 变量未提供: {node.id}")
        return values.get(node.id)
    if isinstance(node, ast.Attribute):
        owner = _eval_node(node.value, values)
        if isinstance(owner, dict):
            return owner.get(node.attr)
        return getattr(owner, node.attr, None)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Call):
        return _eval_call(node, values)
    if isinstance(node, ast.Subscript):
        owner = _eval_node(node.value, values)
        key = _eval_node(node.slice, values)
        return owner[key]
    raise ValueError(f"不支持的 OGNL 节点类型: {type(node).__name__}")


def _eval_call(node: ast.Call, values: dict[str, Any]) -> Any:
    """处理 OGNL 方法调用（仅支持 isEmpty、size）。"""

    if not isinstance(node.func, ast.Attribute) or node.args or node.keywords:
        raise ValueError("不支持的 OGNL 调用")
    owner = _eval_node(node.func.value, values)
    if node.func.attr in {"isEmpty", "is_empty"}:
        return len(owner or []) == 0
    if node.func.attr == "size":
        return len(owner or [])
    raise ValueError("不支持的 OGNL 方法")


def _compare(left: Any, op: ast.cmpop, right: Any) -> bool:
    """执行比较运算。"""

    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.In):
        return left in right
    if isinstance(op, ast.NotIn):
        return left not in right
    raise ValueError(f"不支持的比较运算: {type(op).__name__}")
