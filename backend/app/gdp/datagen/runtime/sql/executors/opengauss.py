"""openGauss SQL 执行器。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.runtime.sql.executors.dbapi import ConnectionFactory, execute_dbapi, to_pyformat_sql
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult


class OpenGaussSqlExecutor:
    """使用 psycopg 同步数据库驱动执行 openGauss SQL。"""

    db_type = "openGauss"

    def __init__(self, connector: ConnectionFactory | None = None) -> None:
        self._connector = connector

    async def execute(
        self,
        *,
        datasource: DatasourceConfig,
        request: SqlExecutionRequest,
    ) -> SqlExecutionResult:
        return await execute_dbapi(
            datasource=datasource,
            request=request,
            connect=self._connect,
            prepare_sql=to_pyformat_sql,
            generated_key_strategy="none",
        )

    def _connect(self, datasource: DatasourceConfig, timeout: int) -> Any:
        if self._connector is not None:
            return self._connector(datasource, timeout)
        import psycopg

        return psycopg.connect(
            host=datasource.host,
            port=datasource.port,
            dbname=datasource.databaseName,
            user=datasource.username or "",
            password=datasource.password or "",
            connect_timeout=timeout,
        )
