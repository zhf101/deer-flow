"""Oracle SQL 执行器。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.runtime.sql.executors.dbapi import ConnectionFactory, execute_dbapi, keep_named_sql
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult


class OracleSqlExecutor:
    """使用 python-oracledb 轻量模式驱动执行 Oracle SQL。"""

    db_type = "Oracle"

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
            prepare_sql=keep_named_sql,
            generated_key_strategy="none",
        )

    def _connect(self, datasource: DatasourceConfig, timeout: int) -> Any:
        if self._connector is not None:
            return self._connector(datasource, timeout)
        import oracledb

        dsn = oracledb.makedsn(
            datasource.host,
            datasource.port,
            service_name=datasource.databaseName,
        )
        return oracledb.connect(
            user=datasource.username or "",
            password=datasource.password or "",
            dsn=dsn,
            tcp_connect_timeout=timeout,
        )
