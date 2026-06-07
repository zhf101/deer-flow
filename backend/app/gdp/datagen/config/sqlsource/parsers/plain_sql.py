"""基于 sqlglot 的普通 SQL 解析器。"""

from __future__ import annotations

from sqlglot import exp, parse_one

from app.gdp.datagen.config.sqlsource.models import (
    SqlSourceConditionMeta,
    SqlSourceFieldMeta,
    SqlSourceParseResponse,
    SqlSourceTableMeta,
)
from app.gdp.datagen.config.sqlsource.parsers.base import SqlAnalysisProvider, SqlParseContext
from app.gdp.datagen.config.sqlsource.parsers.common import (
    detect_operation,
    merge_parameters,
    normalize_sql,
    ordered_parameter_names,
    replace_parameters_with_named,
    replace_parameters_with_question_marks,
)


class PlainSqlAnalysisProvider(SqlAnalysisProvider):
    """解析可执行 SQL 或带参数占位符的 SQL 模板。"""

    def supports(self, context: SqlParseContext) -> bool:
        return True

    def parse(self, context: SqlParseContext) -> SqlSourceParseResponse:
        normalized_sql = normalize_sql(replace_parameters_with_named(context.sql_text))
        executable_sql = normalize_sql(replace_parameters_with_question_marks(context.sql_text))
        names = ordered_parameter_names(normalized_sql)
        if not names and "?" in executable_sql:
            names = [param.name for param in context.parameters]
        params = merge_parameters(names, context.parameters)

        tables: list[SqlSourceTableMeta] = []
        result_fields: list[SqlSourceFieldMeta] = []
        condition_fields: list[SqlSourceConditionMeta] = []
        try:
            expression = parse_one(executable_sql)
            tables = _extract_tables(expression)
            result_fields = _extract_result_fields(expression)
            condition_fields = _extract_condition_fields(expression, names)
        except Exception:
            pass

        return SqlSourceParseResponse(
            normalizedSql=normalized_sql,
            operation=detect_operation(normalized_sql),
            tables=tables,
            resultFields=result_fields,
            conditionFields=condition_fields,
            parameters=params,
        )


def _extract_tables(expression: exp.Expression) -> list[SqlSourceTableMeta]:
    """从 SQL AST 中提取所有涉及的表名和别名。"""

    tables: list[SqlSourceTableMeta] = []
    seen: set[tuple[str, str]] = set()
    for table in expression.find_all(exp.Table):
        name = table.name
        alias = table.alias_or_name if table.alias else ""
        key = (name, alias)
        if name and key not in seen:
            seen.add(key)
            tables.append(
                SqlSourceTableMeta(
                    id=_stable_id("table", len(tables), alias or name),
                    tableName=name,
                    alias=alias,
                )
            )
    return tables


def _extract_result_fields(expression: exp.Expression) -> list[SqlSourceFieldMeta]:
    """从 SELECT 语句中提取查询结果字段。"""

    if not isinstance(expression, exp.Select):
        return []

    fields: list[SqlSourceFieldMeta] = []
    for projection in expression.expressions:
        alias = projection.alias_or_name if projection.alias else ""
        source = projection.this if isinstance(projection, exp.Alias) else projection
        if isinstance(source, exp.Column):
            field_name = source.name
            source_table = source.table
        else:
            field_name = source.sql()
            source_table = ""
        fields.append(
            SqlSourceFieldMeta(
                id=_stable_id("field", len(fields), alias or field_name),
                fieldName=field_name,
                sourceTable=source_table,
                alias=alias,
            )
        )
    return fields


def _extract_condition_fields(
    expression: exp.Expression,
    param_names: list[str],
) -> list[SqlSourceConditionMeta]:
    """从 WHERE / JOIN ON 中提取条件字段及其绑定的参数名。"""

    fields: list[SqlSourceConditionMeta] = []
    seen: set[tuple[str, str, str]] = set()
    param_index = 0

    for predicate in _predicate_expressions(expression):
        columns = list(predicate.find_all(exp.Column))
        has_placeholder = any(isinstance(node, exp.Placeholder) for node in predicate.walk())
        for column in columns:
            param_name = param_names[param_index] if has_placeholder and param_index < len(param_names) else ""
            key = (column.name, column.table, param_name)
            if key not in seen:
                seen.add(key)
                fields.append(
                    SqlSourceConditionMeta(
                        id=_stable_id("condition", len(fields), column.name),
                        fieldName=column.name,
                        sourceTable=column.table,
                        paramName=param_name,
                    )
                )
        if has_placeholder:
            param_index += 1
    return fields


def _predicate_expressions(expression: exp.Expression) -> list[exp.Expression]:
    """收集 WHERE 和 JOIN ON 中的所有谓词表达式。"""

    predicates: list[exp.Expression] = []
    for where in expression.find_all(exp.Where):
        predicates.extend(_split_boolean_predicates(where.this))
    for join in expression.find_all(exp.Join):
        on_expression = join.args.get("on")
        if on_expression is not None:
            predicates.extend(_split_boolean_predicates(on_expression))
    return predicates


def _split_boolean_predicates(expression: exp.Expression) -> list[exp.Expression]:
    """将 AND / OR 连接的复合条件拆分为独立谓词列表。"""

    if isinstance(expression, (exp.And, exp.Or)):
        return _split_boolean_predicates(expression.left) + _split_boolean_predicates(expression.right)
    return [expression]


def _stable_id(prefix: str, index: int, value: str) -> str:
    """生成稳定的前端行 ID。"""

    safe = "".join(char if char.isalnum() else "_" for char in value)[:40] or str(index)
    return f"{prefix}_{index}_{safe}"
