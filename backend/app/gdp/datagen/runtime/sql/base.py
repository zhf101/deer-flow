"""独立 SQL 执行器的基础协议和辅助定义。"""

from __future__ import annotations

from typing import Protocol

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult


class SqlExecutor(Protocol):
    """所有数据库专属 SQL 执行器需要实现的协议。"""

    db_type: str

    async def execute(
        self,
        *,
        datasource: DatasourceConfig,
        request: SqlExecutionRequest,
    ) -> SqlExecutionResult:
        """面向一种具体数据库类型执行 SQL。"""
