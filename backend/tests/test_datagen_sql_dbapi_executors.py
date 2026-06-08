"""不依赖外部数据库的同步数据库接口执行器测试。"""

from __future__ import annotations

import time

import pytest

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.config.common.models import SqlOperation, SqlSourceSafety
from app.gdp.datagen.runtime.sql.executors.goldendb import GoldenDbSqlExecutor
from app.gdp.datagen.runtime.sql.executors.mysql import MySqlSqlExecutor
from app.gdp.datagen.runtime.sql.executors.opengauss import OpenGaussSqlExecutor
from app.gdp.datagen.runtime.sql.executors.oracle import OracleSqlExecutor
from app.gdp.datagen.runtime.sql.executors.tidb import TiDbSqlExecutor
from app.gdp.datagen.runtime.sql.models import SqlExecutionOptions, SqlExecutionRequest
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry


@pytest.mark.anyio
async def test_mysql_executor_converts_named_params_to_pyformat():
    connection = FakeConnection(
        cursor=FakeCursor(
            description=[("id", "INT"), ("name", "VARCHAR")],
            rows=[(1, "Alice")],
        )
    )
    executor = MySqlSqlExecutor(connector=lambda _datasource, _timeout: connection)

    result = await executor.execute(
        datasource=_datasource("MySQL"),
        request=_request(
            operation=SqlOperation.SELECT,
            sql_text="SELECT id, name FROM users WHERE id = :id AND name = :name",
            parameters={"id": 1, "name": "Alice"},
        ),
    )

    assert result.success is True
    assert connection.cursor_obj.executed_sql == ("SELECT id, name FROM users WHERE id = %(id)s AND name = %(name)s")
    assert connection.cursor_obj.executed_params == {"id": 1, "name": "Alice"}
    assert result.row == {"id": 1, "name": "Alice"}


@pytest.mark.anyio
async def test_tidb_and_goldendb_are_independent_executors():
    assert not issubclass(TiDbSqlExecutor, MySqlSqlExecutor)
    assert not issubclass(GoldenDbSqlExecutor, MySqlSqlExecutor)

    registry = SqlExecutorRegistry()
    assert type(registry.get("TiDB")) is TiDbSqlExecutor
    assert type(registry.get("GoldenDB")) is GoldenDbSqlExecutor


@pytest.mark.anyio
async def test_opengauss_executor_rolls_back_when_max_affected_rows_exceeded():
    connection = FakeConnection(cursor=FakeCursor(rowcount=3))
    executor = OpenGaussSqlExecutor(connector=lambda _datasource, _timeout: connection)

    result = await executor.execute(
        datasource=_datasource("openGauss"),
        request=_request(
            operation=SqlOperation.UPDATE,
            sql_text="UPDATE inventory SET stock_num = stock_num - :quantity WHERE stock_num >= :quantity",
            parameters={"quantity": 1},
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=1),
        ),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.type == "SqlSafetyError"
    assert connection.rolled_back is True
    assert connection.committed is False


@pytest.mark.anyio
async def test_dbapi_executor_waits_for_write_result_instead_of_async_timeout():
    connection = FakeConnection(cursor=FakeCursor(rowcount=1, execute_delay=0.05))
    executor = MySqlSqlExecutor(connector=lambda _datasource, _timeout: connection)

    result = await executor.execute(
        datasource=_datasource("MySQL"),
        request=_request(
            operation=SqlOperation.UPDATE,
            sql_text="UPDATE inventory SET stock_num = stock_num - :quantity WHERE sku_id = :skuId",
            parameters={"quantity": 1, "skuId": "SKU10001"},
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=1),
            options=SqlExecutionOptions.model_construct(
                timeoutSeconds=0.01,
                maxRows=200,
                dryRun=False,
                explain=False,
            ),
        ),
    )

    assert result.success is True
    assert result.error is None
    assert connection.committed is True
    assert connection.rolled_back is False


@pytest.mark.anyio
async def test_oracle_executor_keeps_named_params_and_omits_generic_generated_keys():
    connection = FakeConnection(cursor=FakeCursor(rowcount=1, lastrowid=42))
    executor = OracleSqlExecutor(connector=lambda _datasource, _timeout: connection)

    result = await executor.execute(
        datasource=_datasource("Oracle"),
        request=_request(
            operation=SqlOperation.INSERT,
            sql_text="INSERT INTO users(id, name) VALUES (:id, :name)",
            parameters={"id": 1, "name": "Alice"},
            safety=SqlSourceSafety(requireWhere=False, maxAffectedRows=1),
        ),
    )

    assert result.success is True
    assert connection.cursor_obj.executed_sql == "INSERT INTO users(id, name) VALUES (:id, :name)"
    assert result.affectedRows == 1
    assert result.lastInsertId is None
    assert result.generatedKeys == []


@pytest.mark.anyio
async def test_missing_optional_driver_returns_clear_execution_error():
    def missing_driver(_datasource: DatasourceConfig, _timeout: int):
        raise ModuleNotFoundError("No module named 'pymysql'")

    result = await MySqlSqlExecutor(connector=missing_driver).execute(
        datasource=_datasource("MySQL"),
        request=_request(
            operation=SqlOperation.SELECT,
            sql_text="SELECT id FROM users WHERE id = :id",
            parameters={"id": 1},
        ),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.type == "MissingDriverError"


def _datasource(db_type: str) -> DatasourceConfig:
    return DatasourceConfig(
        envCode="DEV",
        sysCode="ORDER",
        datasourceCode="tradeDb",
        datasourceName="Trade DB",
        dbType=db_type,
        host="127.0.0.1",
        port=3306,
        databaseName="trade",
        username="user",
        password="password",
    )


def _request(
    *,
    operation: SqlOperation,
    sql_text: str,
    parameters: dict,
    safety: SqlSourceSafety | None = None,
    options: SqlExecutionOptions | None = None,
) -> SqlExecutionRequest:
    return SqlExecutionRequest(
        envCode="DEV",
        sysCode="ORDER",
        datasourceCode="tradeDb",
        operation=operation,
        sqlText=sql_text,
        parameters=parameters,
        safety=safety or SqlSourceSafety(),
        options=options or SqlExecutionOptions(),
    )


class FakeCursor:
    def __init__(
        self,
        *,
        description=None,
        rows=None,
        rowcount=0,
        lastrowid=None,
        execute_delay=0.0,
    ) -> None:
        self.description = description or []
        self.rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.execute_delay = execute_delay
        self.executed_sql = ""
        self.executed_params = None
        self.closed = False

    def execute(self, sql: str, params):
        if self.execute_delay > 0:
            time.sleep(self.execute_delay)
        self.executed_sql = sql
        self.executed_params = params

    def fetchmany(self, size: int):
        return self.rows[:size]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, *, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True
