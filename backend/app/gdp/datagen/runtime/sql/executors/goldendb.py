"""GoldenDB SQL 执行器。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.runtime.sql.executors.dbapi import ConnectionFactory, execute_dbapi, to_pyformat_sql
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult


class GoldenDbSqlExecutor:
    """通过 GoldenDB 独立执行边界执行 SQL。"""

    db_type = "GoldenDB"

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
            generated_key_strategy="lastrowid",
        )

    def _connect(self, datasource: DatasourceConfig, timeout: int) -> Any:
        if self._connector is not None:
            return self._connector(datasource, timeout)
        import pymysql

        return pymysql.connect(
            host=datasource.host,
            port=datasource.port,
            user=datasource.username or "",
            password=datasource.password or "",
            database=datasource.databaseName,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=timeout,
            read_timeout=timeout,
            write_timeout=timeout,
        )
