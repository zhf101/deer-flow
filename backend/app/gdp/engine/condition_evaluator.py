"""GDP 条件规则评估器——根据 ConditionRule 对响应数据进行判定。

用于评估 HTTP 步骤的：
- ``responseHandling.businessSuccess.allOf``（全部满足才算业务成功）
- ``responseHandling.businessFailure.anyOf``（任一满足即算业务失败）

支持全部 14 种操作符：EQ、NE、GT、GTE、LT、LTE、IN、NOT_IN、
EXISTS、NOT_EXISTS、EMPTY、NOT_EMPTY、CONTAINS、REGEX。
"""

from __future__ import annotations

import re
from typing import Any

from app.gdp.engine.jsonpath_utils import jsonpath_extract
from app.gdp.models import ConditionOperator, ConditionRule


def evaluate_condition(rule: ConditionRule, data: Any) -> bool:
    """评估单条条件规则。

    Args:
        rule: 条件规则（包含 path、op、value）
        data: 被评估的数据（通常是 HTTP 响应结构化后的 dict）

    Returns:
        条件是否满足。
    """
    actual = jsonpath_extract(data, rule.path)
    op = rule.op
    expected = rule.value

    if op == ConditionOperator.EQ:
        return _safe_eq(actual, expected)
    if op == ConditionOperator.NE:
        return not _safe_eq(actual, expected)
    if op == ConditionOperator.GT:
        return _to_float(actual) > _to_float(expected)
    if op == ConditionOperator.GTE:
        return _to_float(actual) >= _to_float(expected)
    if op == ConditionOperator.LT:
        return _to_float(actual) < _to_float(expected)
    if op == ConditionOperator.LTE:
        return _to_float(actual) <= _to_float(expected)
    if op == ConditionOperator.IN:
        items = expected if isinstance(expected, list) else [expected]
        return actual in items or str(actual) in [str(i) for i in items]
    if op == ConditionOperator.NOT_IN:
        items = expected if isinstance(expected, list) else [expected]
        return actual not in items and str(actual) not in [str(i) for i in items]
    if op == ConditionOperator.EXISTS:
        return actual is not None
    if op == ConditionOperator.NOT_EXISTS:
        return actual is None
    if op == ConditionOperator.EMPTY:
        return actual is None or actual == "" or actual == [] or actual == {}
    if op == ConditionOperator.NOT_EMPTY:
        return actual is not None and actual != "" and actual != [] and actual != {}
    if op == ConditionOperator.CONTAINS:
        if actual is None:
            return False
        if isinstance(actual, (str, list)):
            return expected in actual
        return False
    if op == ConditionOperator.REGEX:
        if actual is None:
            return False
        try:
            return bool(re.search(str(expected), str(actual)))
        except re.error:
            return False

    return False


def evaluate_all_of(rules: list[ConditionRule], data: Any) -> bool:
    """全部条件满足则返回 True（对应 businessSuccess.allOf）。"""
    if not rules:
        return True
    return all(evaluate_condition(r, data) for r in rules)


def evaluate_any_of(rules: list[ConditionRule], data: Any) -> bool:
    """任一条件满足则返回 True（对应 businessFailure.anyOf）。"""
    if not rules:
        return False
    return any(evaluate_condition(r, data) for r in rules)


def _safe_eq(actual: Any, expected: Any) -> bool:
    """安全比较——优先用原始类型比较，失败时转为字符串比较。"""
    if actual == expected:
        return True
    return str(actual) == str(expected)


def _to_float(value: Any) -> float:
    """尝试将值转为浮点数，失败时返回 0.0。"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
