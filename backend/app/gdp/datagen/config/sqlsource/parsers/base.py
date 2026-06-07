"""SQL 解析 Provider 共享契约。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.gdp.datagen.config.sqlsource.models import (
    SqlSourceParameter,
    SqlSourceParseResponse,
)


@dataclass(frozen=True)
class SqlParseContext:
    """解析 Provider 共享的输入上下文。"""

    sql_text: str
    parameters: list[SqlSourceParameter]


class SqlAnalysisProvider(ABC):
    """可插拔的 SQL 分析 Provider。

    确定性 Provider 应优先于 AI Provider 执行。未来的 AI Provider 可实现
    相同契约，作为兜底或增强分析器。
    """

    @abstractmethod
    def supports(self, context: SqlParseContext) -> bool:
        """判断当前 Provider 是否能解析该输入。"""

    @abstractmethod
    def parse(self, context: SqlParseContext) -> SqlSourceParseResponse:
        """将源文本解析为 SQL 配置解析响应。"""
