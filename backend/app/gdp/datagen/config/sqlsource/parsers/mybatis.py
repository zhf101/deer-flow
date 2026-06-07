"""MyBatis XML 动态 SQL 分析 Provider。

处理流水线::

    MyBatis XML 文本
        ↓  mybatis_parser.parse_mybatis_xml()
    MyBatis AST（StatementNode / MapperNode）
        ↓  mybatis_renderer.render()
    SQL 文本（含 #{param} 占位符）
        ↓  PlainSqlAnalysisProvider.parse()
    SqlSourceParseResponse（表、字段、参数等）

AST 中间表示便于未来扩展：
- ``all_branches=True`` 渲染，用于全量数据血缘分析
- AI Provider 检查 AST 结构进行语义理解
- 多语句 Mapper 文件支持
"""

from __future__ import annotations

from app.gdp.datagen.config.sqlsource.models import SqlSourceParseResponse
from app.gdp.datagen.config.sqlsource.parsers.base import SqlAnalysisProvider, SqlParseContext
from app.gdp.datagen.config.sqlsource.parsers.common import (
    merge_parameters,
    normalize_sql,
    ordered_parameter_names,
    replace_parameters_with_named,
)
from app.gdp.datagen.config.sqlsource.parsers.mybatis_parser import parse_mybatis_xml
from app.gdp.datagen.config.sqlsource.parsers.mybatis_renderer import render
from app.gdp.datagen.config.sqlsource.parsers.plain_sql import PlainSqlAnalysisProvider

STATEMENT_TAGS = frozenset({"select", "insert", "update", "delete"})


class MyBatisSqlAnalysisProvider(SqlAnalysisProvider):
    """将 MyBatis XML 渲染为可执行 SQL 后通过 sqlglot 进行分析。"""

    def supports(self, context: SqlParseContext) -> bool:
        text = context.sql_text.lstrip()
        return text.startswith("<") and any(f"<{tag}" in text.lower() for tag in STATEMENT_TAGS)

    def parse(self, context: SqlParseContext) -> SqlSourceParseResponse:
        # 第 1 步：XML → MyBatis AST
        ast = parse_mybatis_xml(context.sql_text)

        # 第 2 步：AST → SQL。元数据分析使用全分支，规范 SQL 使用确定性分支。
        values = {p.name: p.defaultValue for p in context.parameters}
        analysis_render_result = render(ast, values=values, all_branches=True)
        normalized_render_result = render(ast, values=values, all_branches=False)

        # 第 3 步：将分析 SQL 和规范 SQL 都转为命名参数，避免保存阶段退化成 ?。
        analysis_named_sql = normalize_sql(
            replace_parameters_with_named(
                analysis_render_result.sql,
                analysis_render_result.parameter_aliases,
            )
        )
        named_sql = normalize_sql(
            replace_parameters_with_named(
                normalized_render_result.sql,
                normalized_render_result.parameter_aliases,
            )
        )
        analysis_param_names = ordered_parameter_names(analysis_named_sql)
        if not analysis_param_names:
            analysis_param_names = sorted(analysis_render_result.referenced_params)

        # 第 4 步：通过 PlainSqlAnalysisProvider 进行 sqlglot 分析
        plain_context = SqlParseContext(
            sql_text=analysis_named_sql,
            parameters=merge_parameters(analysis_param_names, context.parameters),
        )
        response = PlainSqlAnalysisProvider().parse(plain_context)

        # 用 AST 渲染得到的正确参数列表覆盖结果
        return response.model_copy(
            update={
                "normalizedSql": named_sql,
                "parameters": merge_parameters(analysis_param_names, context.parameters),
            }
        )
