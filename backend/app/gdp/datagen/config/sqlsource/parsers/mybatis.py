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
    replace_parameters_with_question_marks,
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

        # 第 2 步：AST → SQL（分析模式：包含所有分支以发现全部表和参数）
        values = {p.name: p.defaultValue for p in context.parameters}
        render_result = render(ast, values=values, all_branches=True)

        # 第 3 步：将 #{param} 替换为 ? 以便 sqlglot 解析
        executable_sql = normalize_sql(replace_parameters_with_question_marks(render_result.sql))

        # 第 4 步：通过 PlainSqlAnalysisProvider 进行 sqlglot 分析
        plain_context = SqlParseContext(
            sql_text=executable_sql,
            parameters=merge_parameters(render_result.referenced_params, context.parameters),
        )
        response = PlainSqlAnalysisProvider().parse(plain_context)

        # 用 AST 渲染得到的正确参数列表覆盖结果
        return response.model_copy(
            update={
                "normalizedSql": executable_sql,
                "parameters": merge_parameters(render_result.referenced_params, context.parameters),
            }
        )
