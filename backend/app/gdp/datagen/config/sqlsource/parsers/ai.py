"""AI 驱动的 SQL 分析扩展点。"""

from __future__ import annotations

from app.gdp.datagen.config.sqlsource.models import SqlSourceParseResponse
from app.gdp.datagen.config.sqlsource.parsers.base import SqlAnalysisProvider, SqlParseContext


class AiSqlAnalysisProvider(SqlAnalysisProvider):
    """未来 LLM 辅助 SQL 分析的预留 Provider。

    确定性解析器作为默认方案，因为它可审计且稳定。该 Provider 当前处于
    禁用状态，待应用层接入模型凭证、Prompt 模板、护栏和结果校验后启用。
    """

    def supports(self, context: SqlParseContext) -> bool:
        return False

    def parse(self, context: SqlParseContext) -> SqlSourceParseResponse:
        raise NotImplementedError("AI SQL 分析 Provider 尚未配置")
