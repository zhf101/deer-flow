"""ASSERT 步骤执行器。

逐条评估断言表达式，任一断言失败则整个步骤标记为 FAILED。
断言表达式是包含变量引用的字符串，解析后支持简单比较运算。

示例断言：
- ``${steps.createOrder.outputs.orderNo} NOT_EMPTY``
- ``${steps.checkStatus.outputs.status} == ACTIVE``
- ``${input.amount} > 0``
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.gdp.engine.context import ExecutionContext
from app.gdp.engine.models import StepResult
from app.gdp.engine.variable_resolver import resolve_value
from app.gdp.models import AssertionDefinition, StepDefinition, StepType


async def execute_assert_step(step: StepDefinition, ctx: ExecutionContext) -> StepResult:
    """执行断言步骤——逐条评估表达式，任一失败则步骤失败。"""
    started_at = datetime.now(UTC)

    if not step.assertions:
        finished_at = datetime.now(UTC)
        return StepResult(
            stepId=step.stepId,
            stepName=step.stepName,
            type=StepType.ASSERT,
            status="SUCCESS",
            startedAt=started_at,
            finishedAt=finished_at,
            durationMs=0,
        )

    for assertion in step.assertions:
        passed = _evaluate_assertion(assertion, ctx)
        if not passed:
            finished_at = datetime.now(UTC)
            return StepResult(
                stepId=step.stepId,
                stepName=step.stepName,
                type=StepType.ASSERT,
                status="FAILED",
                startedAt=started_at,
                finishedAt=finished_at,
                durationMs=int((finished_at - started_at).total_seconds() * 1000),
                error=assertion.message or f"断言失败: {assertion.expression}",
            )

    finished_at = datetime.now(UTC)
    return StepResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=StepType.ASSERT,
        status="SUCCESS",
        startedAt=started_at,
        finishedAt=finished_at,
        durationMs=int((finished_at - started_at).total_seconds() * 1000),
    )


def _evaluate_assertion(assertion: AssertionDefinition, ctx: ExecutionContext) -> bool:
    """评估单条断言表达式。

    解析策略：
    1. 先对表达式中的变量引用做替换
    2. 尝试匹配 "值 操作符 值" 模式（==、!=、>、<、>=、<=）
    3. 尝试匹配 "值 KEYWORD" 模式（NOT_EMPTY、EMPTY）
    4. 兜底：检查解析后值的 truthiness
    """
    expr = assertion.expression

    # ── 处理 "后缀操作符" 模式：${var} NOT_EMPTY / EMPTY ──
    if expr.strip().endswith("NOT_EMPTY"):
        var_part = expr.strip().rsplit("NOT_EMPTY", 1)[0].strip()
        resolved = resolve_value(var_part, ctx)
        return _is_not_empty(resolved)

    if expr.strip().endswith("EMPTY"):
        var_part = expr.strip().rsplit("EMPTY", 1)[0].strip()
        resolved = resolve_value(var_part, ctx)
        return _is_empty(resolved)

    # ── 先做变量替换 ──
    resolved = resolve_value(expr, ctx)

    # 如果替换后是布尔值，直接返回
    if isinstance(resolved, bool):
        return resolved

    expr_str = str(resolved)

    # ── 尝试匹配比较运算 ──
    for op_str, op_fn in [
        ("==", lambda a, b: str(a) == str(b)),
        ("!=", lambda a, b: str(a) != str(b)),
        (">=", lambda a, b: _safe_float(a) >= _safe_float(b)),
        ("<=", lambda a, b: _safe_float(a) <= _safe_float(b)),
        (">", lambda a, b: _safe_float(a) > _safe_float(b)),
        ("<", lambda a, b: _safe_float(a) < _safe_float(b)),
    ]:
        if f" {op_str} " in expr_str:
            lhs, rhs = expr_str.split(f" {op_str} ", 1)
            return op_fn(lhs.strip(), rhs.strip())

    # ── 兜底：truthiness 检查 ──
    lower = expr_str.lower().strip()
    return lower not in ("false", "0", "none", "null", "")


def _is_not_empty(value: Any) -> bool:
    """判断值是否非空。"""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def _is_empty(value: Any) -> bool:
    """判断值是否为空。"""
    return not _is_not_empty(value)


def _safe_float(value: Any) -> float:
    """安全转浮点数。"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
