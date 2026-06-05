"""SQL 步骤执行器。

负责：
1. 根据 sqlTemplateCode 加载 SQL 模板文本
2. 从 paramMapping 解析参数值（支持变量引用）
3. 尝试连接数据源执行 SQL（支持 MySQL / PostgreSQL / SQLite）
4. 数据源不可用时降级——返回准备好的 SQL 和参数作为输出
5. 评估步骤自带的 assertions
6. 通过 outputMapping 提取输出
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.gdp.engine.context import ExecutionContext
from app.gdp.engine.models import StepResult
from app.gdp.engine.variable_resolver import resolve_value
from app.gdp.models import SqlOperation, SqlTemplateConfig, StepDefinition, StepType

logger = logging.getLogger(__name__)

# SQL 模板解析回调类型：templateCode -> SqlTemplateConfig | None
TemplateResolver = Callable[[str], SqlTemplateConfig | None]
# 数据源解析回调类型：datasourceCode, envCode -> 连接 URL 字符串 | None
DatasourceResolver = Callable[[str, str], str | None]


async def execute_sql_step(
    step: StepDefinition,
    ctx: ExecutionContext,
    *,
    template_resolver: TemplateResolver | None = None,
    datasource_resolver: DatasourceResolver | None = None,
) -> StepResult:
    """执行 SQL 步骤。"""
    started_at = datetime.now(UTC)

    # ── 1. 解析 SQL 模板 ──
    template_code = step.sqlTemplateCode
    if not template_code:
        return _fail(step, started_at, "SQL 步骤未指定 sqlTemplateCode")

    template: SqlTemplateConfig | None = None
    if template_resolver:
        template = template_resolver(template_code)

    if template is None:
        return _fail(step, started_at, f"SQL 模板不存在或已停用: {template_code}")

    # ── 2. 解析参数映射 ──
    resolved_params = resolve_value(step.paramMapping or {}, ctx)
    if not isinstance(resolved_params, dict):
        resolved_params = {}

    # 合并模板参数默认值
    bound_params: dict[str, Any] = {}
    for param in template.parameters:
        if param.name in resolved_params:
            bound_params[param.name] = resolved_params[param.name]
        elif param.defaultValue is not None:
            bound_params[param.name] = param.defaultValue

    sql_text = template.sqlText

    # ── 3. 尝试执行 SQL ──
    result_data: dict[str, Any] = {}
    executed = False

    if datasource_resolver:
        # 解析数据源引用（如 "${env.datasources.tradeDb}" → "tradeDb"）
        ds_ref = step.datasource or ""
        # 尝试从上下文获取数据源编码
        ds_code = _extract_datasource_code(ds_ref, ctx)

        conn_url = datasource_resolver(ds_code, ctx.env_code)
        if conn_url:
            try:
                result_data = await _execute_sql(conn_url, sql_text, bound_params, step.operation)
                executed = True
            except Exception as exc:
                logger.warning("SQL 执行失败 [%s]: %s", template_code, exc)
                result_data = {
                    "prepared_sql": sql_text,
                    "params": bound_params,
                    "error": str(exc),
                }
    
    if not executed:
        # 数据源不可用——降级返回准备好的 SQL
        result_data = {
            "prepared_sql": sql_text,
            "params": bound_params,
            "note": "数据源未配置或不可用，返回准备好的 SQL",
        }

    # ── 4. 评估 assertions ──
    for assertion in step.assertions:
        resolved_expr = resolve_value(assertion.expression, ctx)
        if not _eval_sql_assertion(resolved_expr, result_data):
            return _fail(step, started_at,
                          assertion.message or f"SQL 断言失败: {assertion.expression}",
                          raw=result_data)

    # ── 5. 提取 outputMapping ──
    outputs: dict[str, Any] = {}
    for key, mapping in step.outputMapping.items():
        outputs[key] = _extract_sql_output(mapping, result_data)

    # ── 6. 写入上下文 ──
    ctx.set_step_output(step.stepId, outputs)
    ctx.set_step_raw(step.stepId, result_data)

    finished_at = datetime.now(UTC)
    return StepResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=StepType.SQL,
        status="SUCCESS",
        startedAt=started_at,
        finishedAt=finished_at,
        durationMs=int((finished_at - started_at).total_seconds() * 1000),
        outputs=outputs,
        rawResponse=result_data,
    )


async def _execute_sql(
    conn_url: str,
    sql_text: str,
    params: dict[str, Any],
    operation: SqlOperation | None,
) -> dict[str, Any]:
    """通过 SQLAlchemy 异步引擎执行 SQL。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(conn_url, echo=False)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql_text), params)
            if operation == SqlOperation.SELECT:
                rows = result.mappings().all()
                return {
                    "rows": [dict(r) for r in rows],
                    "row_count": len(rows),
                }
            else:
                return {"affected_rows": result.rowcount}
    finally:
        await engine.dispose()


def _extract_datasource_code(ds_ref: str, ctx: ExecutionContext) -> str:
    """从数据源引用中提取编码。

    支持格式：
    - "tradeDb"                     → "tradeDb"
    - "${env.datasources.tradeDb}"  → "tradeDb"（已在上游解析）
    """
    # 如果 ds_ref 是 DatasourceConfig 对象（已解析），返回其 datasourceCode
    if hasattr(ds_ref, "datasourceCode"):
        return ds_ref.datasourceCode
    if hasattr(ds_ref, "datasource_code"):
        return ds_ref.datasource_code
    # 如果是字符串，直接作为编码使用
    return str(ds_ref) if ds_ref else ""


def _eval_sql_assertion(resolved_expr: Any, result_data: dict[str, Any]) -> bool:
    """评估 SQL 断言表达式。"""
    # 如果解析后是布尔值，直接返回
    if isinstance(resolved_expr, bool):
        return resolved_expr

    expr_str = str(resolved_expr)

    # 尝试匹配 "LHS op RHS" 模式
    for op_str, op_fn in [
        ("==", lambda a, b: str(a) == str(b)),
        ("!=", lambda a, b: str(a) != str(b)),
        (">=", lambda a, b: _safe_float(a) >= _safe_float(b)),
        ("<=", lambda a, b: _safe_float(a) <= _safe_float(b)),
    ]:
        if f" {op_str} " in expr_str:
            lhs, rhs = expr_str.split(f" {op_str} ", 1)
            return op_fn(lhs.strip(), rhs.strip())

    # 无比较运算符——检查 truthiness
    lower = expr_str.lower().strip()
    return lower not in ("false", "0", "none", "null", "")


def _extract_sql_output(mapping: str, result_data: dict[str, Any]) -> Any:
    """根据 outputMapping 提取 SQL 执行结果。

    支持：
    - "$.affectedRows" → result_data["affected_rows"]
    - "$.rows[0].field" → result_data["rows"][0]["field"]
    - "affectedRows" → result_data.get("affected_rows")
    """
    if mapping.startswith("$."):
        # 转换 JSONPath 风格到 result_data 的键
        from app.gdp.engine.jsonpath_utils import jsonpath_extract
        return jsonpath_extract(result_data, mapping)

    # 直接键名查找
    return result_data.get(mapping)


def _safe_float(value: Any) -> float:
    """安全转浮点数。"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _fail(step: StepDefinition, started_at: datetime, error: str, *, raw: Any = None) -> StepResult:
    """构造失败的 SQL 步骤结果。"""
    finished_at = datetime.now(UTC)
    return StepResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=StepType.SQL,
        status="FAILED",
        startedAt=started_at,
        finishedAt=finished_at,
        durationMs=int((finished_at - started_at).total_seconds() * 1000),
        error=error,
        rawResponse=raw,
    )
