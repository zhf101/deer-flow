"""SQLite SQL 执行器。"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from time import perf_counter
from typing import Any

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.config.common.models import SqlOperation
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult, SqlResultColumn
from app.gdp.datagen.runtime.sql.result import jsonable

# 创建模块日志记录器
logger = logging.getLogger(__name__)


class SQLiteSqlExecutor:
    """在本地 SQLite 数据库上执行统一命名参数 SQL。"""

    db_type = "SQLite"

    async def execute(
        self,
        *,
        datasource: DatasourceConfig,
        request: SqlExecutionRequest,
    ) -> SqlExecutionResult:
        logger.info("=" * 60)
        logger.info("【SQL 执行器 - SQLite】开始执行")
        logger.info("数据源编码: %s", datasource.datasourceCode)
        logger.info("数据源名称: %s", datasource.datasourceName)
        logger.info("数据库文件: %s", datasource.databaseName)
        logger.info("操作类型: %s", request.operation.value)
        logger.info("-" * 40)
        logger.info("【SQL 文本】")
        logger.info("%s", request.sqlText)
        logger.info("【SQL 参数】")
        if request.parameters:
            for param_name, param_value in request.parameters.items():
                logger.info("  :%s = %s (类型: %s)", param_name, param_value, type(param_value).__name__)
        else:
            logger.info("  无参数")
        logger.info("【执行选项】")
        logger.info("  超时时间: %d 秒", request.options.timeoutSeconds)
        logger.info("  最大返回行数: %d", request.options.maxRows)
        logger.info("  试运行模式: %s", "是" if request.options.dryRun else "否")
        logger.info("-" * 40)

        started = perf_counter()
        try:
            result = await asyncio.to_thread(self._execute_sync, datasource, request)
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            result = result.model_copy(update={"elapsedMs": elapsed_ms})

            # 记录执行结果
            logger.info("【执行结果】")
            logger.info("  是否成功: %s", "成功" if result.success else "失败")
            logger.info("  执行耗时: %.3f 毫秒", elapsed_ms)
            if request.operation == SqlOperation.SELECT:
                logger.info("  返回列数: %d", len(result.columns))
                logger.info("  返回行数: %d", len(result.rows))
                if result.columns:
                    col_names = [c.name for c in result.columns]
                    logger.info("  列名列表: %s", col_names)
                if result.rows:
                    for i, row in enumerate(result.rows[:3]):
                        logger.info("  第 %d 行: %s", i + 1, json.dumps(row, ensure_ascii=False, default=str))
                    if len(result.rows) > 3:
                        logger.info("  ... 共 %d 行", len(result.rows))
                if result.warnings:
                    for warning in result.warnings:
                        logger.warning("  警告: %s", warning)
            else:
                logger.info("  影响行数: %d", result.affectedRows)
                if result.lastInsertId is not None:
                    logger.info("  最后插入 ID: %s", result.lastInsertId)
            if result.extractedOutputs:
                logger.info("【输出变量提取】")
                for var_name, var_value in result.extractedOutputs.items():
                    logger.info("  %s = %s", var_name, var_value)
            if result.error:
                logger.error("【执行错误】")
                logger.error("  错误类型: %s", result.error.type)
                logger.error("  错误信息: %s", result.error.message)
            logger.info("=" * 60)

            return result
        except sqlite3.Error as exc:
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            raw_type = type(exc).__name__
            raw_message = str(exc)
            logger.error("【SQL 执行失败】SQLite 原始错误: %s: %s", raw_type, raw_message)
            logger.info("=" * 60)
            from app.gdp.datagen.runtime.sql.executors.dbapi import friendly_sql_error
            friendly_type, friendly_msg = friendly_sql_error(raw_type, raw_message)
            return SqlExecutionResult.failed(
                db_type=datasource.dbType,
                operation=request.operation,
                error_type=friendly_type,
                message=friendly_msg,
                elapsed_ms=elapsed_ms,
            )
        except OSError as exc:
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            raw_type = type(exc).__name__
            raw_message = str(exc)
            logger.error("【SQL 执行失败】文件系统原始错误: %s: %s", raw_type, raw_message)
            logger.info("=" * 60)
            from app.gdp.datagen.runtime.sql.executors.dbapi import friendly_sql_error
            friendly_type, friendly_msg = friendly_sql_error(raw_type, raw_message)
            return SqlExecutionResult.failed(
                db_type=datasource.dbType,
                operation=request.operation,
                error_type=friendly_type,
                message=friendly_msg,
                elapsed_ms=elapsed_ms,
            )

    def _execute_sync(
        self,
        datasource: DatasourceConfig,
        request: SqlExecutionRequest,
    ) -> SqlExecutionResult:
        db_path = _resolve_sqlite_path(datasource.databaseName)
        if request.options.dryRun:
            return SqlExecutionResult(
                success=True,
                dbType=datasource.dbType,
                operation=request.operation,
                warnings=["已启用 dryRun：SQL 已完成校验但未执行。"],
            )

        with sqlite3.connect(db_path, timeout=request.options.timeoutSeconds) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            if request.operation == SqlOperation.SELECT:
                return _execute_select(conn, datasource.dbType, request)
            return _execute_dml(conn, datasource.dbType, request)


def _resolve_sqlite_path(database_name: str) -> str:
    if database_name == ":memory:" or database_name.startswith("file:"):
        return database_name
    path = Path(database_name).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"SQLite database file not found: {database_name}")
    return str(path)


def _execute_select(
    conn: sqlite3.Connection,
    db_type: str,
    request: SqlExecutionRequest,
) -> SqlExecutionResult:
    cursor = conn.execute(request.sqlText, request.parameters)
    raw_rows = cursor.fetchmany(request.options.maxRows + 1)
    limited = raw_rows[: request.options.maxRows]
    columns = [SqlResultColumn(name=description[0], type=None) for description in (cursor.description or [])]
    rows = [_row_to_dict(row) for row in limited]
    warnings = []
    if len(raw_rows) > request.options.maxRows:
        warnings.append(f"查询结果已按 maxRows={request.options.maxRows} 截断。")
    return SqlExecutionResult(
        success=True,
        dbType=db_type,
        operation=request.operation,
        columns=columns,
        rows=rows,
        row=rows[0] if rows else None,
        affectedRows=0,
        warnings=warnings,
    )


def _execute_dml(
    conn: sqlite3.Connection,
    db_type: str,
    request: SqlExecutionRequest,
) -> SqlExecutionResult:
    try:
        cursor = conn.execute(request.sqlText, request.parameters)
        affected_rows = max(cursor.rowcount, 0)
        if request.safety.maxAffectedRows is not None and affected_rows > request.safety.maxAffectedRows:
            conn.rollback()
            return SqlExecutionResult.failed(
                db_type=db_type,
                operation=request.operation,
                error_type="SqlSafetyError",
                message=(f"实际影响行数 {affected_rows} 超过最大允许影响行数 {request.safety.maxAffectedRows}。"),
            )
        conn.commit()
        return SqlExecutionResult(
            success=True,
            dbType=db_type,
            operation=request.operation,
            affectedRows=affected_rows,
            lastInsertId=cursor.lastrowid if request.operation == SqlOperation.INSERT else None,
            generatedKeys=[cursor.lastrowid] if request.operation == SqlOperation.INSERT and cursor.lastrowid else [],
        )
    except Exception:
        conn.rollback()
        raise


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: jsonable(row[key]) for key in row.keys()}
