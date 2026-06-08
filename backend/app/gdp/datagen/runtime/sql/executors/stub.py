"""第一阶段未实现数据库的独立占位执行器。"""

from __future__ import annotations

from time import perf_counter

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult


class NotImplementedSqlExecutor:
    """驱动接入尚未实现的数据库执行器边界。"""

    db_type: str

    def __init__(self, db_type: str) -> None:
        self.db_type = db_type

    async def execute(
        self,
        *,
        datasource: DatasourceConfig,
        request: SqlExecutionRequest,
    ) -> SqlExecutionResult:
        started = perf_counter()
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        return SqlExecutionResult.failed(
            db_type=datasource.dbType,
            operation=request.operation,
            error_type="UnsupportedDatabaseError",
            message=f"{self.db_type} SQL executor is declared but not implemented yet",
            elapsed_ms=elapsed_ms,
        )
