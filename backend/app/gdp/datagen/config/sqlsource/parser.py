"""SQL 源解析入口。

用法::

    from app.gdp.datagen.config.sqlsource.parser import parse_sql_source

    result = parse_sql_source(sql_text, parameters)

Provider 链可配置。默认运行确定性 Provider（MyBatis XML → 普通 SQL）。
将来如需启用 AI 分析，将 :class:`AiSqlAnalysisProvider` 加入链中并配置模型凭证即可。
"""

from __future__ import annotations

from collections.abc import Sequence

from app.gdp.datagen.config.sqlsource.models import (
    SqlSourceParameter,
    SqlSourceParseResponse,
)
from app.gdp.datagen.config.sqlsource.parsers.base import SqlAnalysisProvider, SqlParseContext
from app.gdp.datagen.config.sqlsource.parsers.mybatis import MyBatisSqlAnalysisProvider
from app.gdp.datagen.config.sqlsource.parsers.plain_sql import PlainSqlAnalysisProvider

# 默认 Provider 链：优先处理 MyBatis XML（检测 <select> 等标签），
# 普通 SQL 作为兜底。
DEFAULT_PROVIDERS: list[SqlAnalysisProvider] = [
    MyBatisSqlAnalysisProvider(),
    PlainSqlAnalysisProvider(),
]


def parse_sql_source(
    sql_text: str,
    parameters: list[SqlSourceParameter] | None = None,
    *,
    providers: Sequence[SqlAnalysisProvider] | None = None,
) -> SqlSourceParseResponse:
    """将 SQL 或 MyBatis XML 解析为配置元数据。

    Args:
        sql_text: 原始 SQL 文本或 MyBatis XML 片段。
        parameters: 已有的参数定义，用于保留。
        providers: 可选的自定义 Provider 链，默认为
            ``[MyBatisSqlAnalysisProvider, PlainSqlAnalysisProvider]``。
            如需添加 AI 分析，传入包含 :class:`AiSqlAnalysisProvider` 的列表。

    Returns:
        解析后的元数据，包括标准化 SQL、操作类型、表、字段、条件和参数。
    """

    context = SqlParseContext(sql_text=sql_text, parameters=parameters or [])
    chain = providers if providers is not None else DEFAULT_PROVIDERS

    for provider in chain:
        if provider.supports(context):
            return provider.parse(context)

    # 绝对兜底
    return PlainSqlAnalysisProvider().parse(context)
