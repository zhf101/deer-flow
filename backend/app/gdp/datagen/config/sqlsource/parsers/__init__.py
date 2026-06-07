"""SQL 源解析器实现。

公共 API::

    from app.gdp.datagen.config.sqlsource.parsers import (
        parse_sql_source,           # 主入口
        parse_mybatis_xml,          # XML → AST
        render_mybatis_ast,         # AST → SQL
        SqlAnalysisProvider,        # 自定义 Provider 抽象基类
        SqlParseContext,            # 输入上下文
        AiSqlAnalysisProvider,      # 未来 AI Provider 占位
    )
"""

from app.gdp.datagen.config.sqlsource.parsers.ast import (
    ChooseNode,
    ForeachNode,
    IfNode,
    MapperNode,
    MyBatisNode,
    OtherwiseNode,
    RenderResult,
    SetNode,
    StatementNode,
    TextNode,
    TrimNode,
    WhenNode,
    WhereNode,
)
from app.gdp.datagen.config.sqlsource.parsers.base import SqlAnalysisProvider, SqlParseContext
from app.gdp.datagen.config.sqlsource.parsers.ai import AiSqlAnalysisProvider
from app.gdp.datagen.config.sqlsource.parsers.mybatis_parser import parse_mybatis_xml
from app.gdp.datagen.config.sqlsource.parsers.mybatis_renderer import render as render_mybatis_ast

__all__ = [
    # AST 节点
    "MyBatisNode",
    "TextNode",
    "IfNode",
    "WhereNode",
    "SetNode",
    "ForeachNode",
    "ChooseNode",
    "WhenNode",
    "OtherwiseNode",
    "TrimNode",
    "StatementNode",
    "MapperNode",
    "RenderResult",
    # Provider 契约
    "SqlAnalysisProvider",
    "SqlParseContext",
    "AiSqlAnalysisProvider",
    # 流水线函数
    "parse_mybatis_xml",
    "render_mybatis_ast",
]
