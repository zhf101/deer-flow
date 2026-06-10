"""具体 SQL 执行器共用的数据库接口执行辅助函数。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.config.common.models import SqlOperation
from app.gdp.datagen.runtime.sql.models import SqlExecutionRequest, SqlExecutionResult, SqlResultColumn
from app.gdp.datagen.runtime.sql.result import jsonable

# 创建模块日志记录器
logger = logging.getLogger(__name__)

ConnectionFactory = Callable[[DatasourceConfig, int], Any]
SqlPreparer = Callable[[str], str]

_NAMED_PARAM_RE = re.compile(r"(^|[^:]):([a-zA-Z_]\w*)")


async def execute_dbapi(
    *,
    datasource: DatasourceConfig,
    request: SqlExecutionRequest,
    connect: ConnectionFactory,
    prepare_sql: SqlPreparer,
    generated_key_strategy: str = "lastrowid",
) -> SqlExecutionResult:
    """通过同步数据库接口风格驱动执行请求。"""

    logger.info("=" * 60)
    logger.info("【SQL 执行器 - %s】开始执行", datasource.dbType)
    logger.info("数据源编码: %s", datasource.datasourceCode)
    logger.info("数据源名称: %s", datasource.datasourceName)
    logger.info("数据库类型: %s", datasource.dbType)
    logger.info("数据库地址: %s:%d", datasource.host, datasource.port)
    logger.info("数据库名称: %s", datasource.databaseName)
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
        result = await asyncio.to_thread(
            _execute_sync,
            datasource,
            request,
            connect,
            prepare_sql,
            generated_key_strategy,
        )
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
                # 只打印前 3 行数据作为示例
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
            if result.error.detail:
                logger.error("  详细信息: %s", result.error.detail)
        logger.info("=" * 60)

        return result
    except ModuleNotFoundError as exc:
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        logger.error("【SQL 执行失败】数据库驱动未安装: %s", exc.name)
        logger.info("=" * 60)
        driver_name = exc.name or str(exc)
        friendly_type, friendly_msg = friendly_sql_error("MissingDriverError", f"数据库驱动未安装：{driver_name}")
        return SqlExecutionResult.failed(
            db_type=datasource.dbType,
            operation=request.operation,
            error_type=friendly_type,
            message=friendly_msg,
            elapsed_ms=elapsed_ms,
        )
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        raw_type = type(exc).__name__
        raw_message = str(exc)
        # 服务端记录原始异常详情用于排查，不暴露给前端
        logger.error("【SQL 执行失败】")
        logger.error("  原始异常类型: %s", raw_type)
        logger.error("  原始异常信息: %s", raw_message)
        logger.info("=" * 60)
        friendly_type, friendly_msg = friendly_sql_error(raw_type, raw_message)
        return SqlExecutionResult.failed(
            db_type=datasource.dbType,
            operation=request.operation,
            error_type=friendly_type,
            message=friendly_msg,
            elapsed_ms=elapsed_ms,
        )


def to_pyformat_sql(sql_text: str) -> str:
    """将统一的 ``:name`` 参数转换为百分号命名占位符格式。"""

    return _NAMED_PARAM_RE.sub(lambda match: f"{match.group(1)}%({match.group(2)})s", sql_text)


def keep_named_sql(sql_text: str) -> str:
    """保持统一命名参数不变。"""

    return sql_text


def _execute_sync(
    datasource: DatasourceConfig,
    request: SqlExecutionRequest,
    connect: ConnectionFactory,
    prepare_sql: SqlPreparer,
    generated_key_strategy: str,
) -> SqlExecutionResult:
    if request.options.dryRun:
        return SqlExecutionResult(
            success=True,
            dbType=datasource.dbType,
            operation=request.operation,
            warnings=["已启用 dryRun：SQL 已完成校验但未执行。"],
        )

    connection = connect(datasource, request.options.timeoutSeconds)
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(prepare_sql(request.sqlText), request.parameters)
        if request.operation == SqlOperation.SELECT:
            return _select_result(cursor, datasource.dbType, request)
        return _dml_result(connection, cursor, datasource.dbType, request, generated_key_strategy)
    except Exception:
        _rollback_quietly(connection)
        raise
    finally:
        _close_quietly(cursor)
        _close_quietly(connection)


def _select_result(cursor: Any, db_type: str, request: SqlExecutionRequest) -> SqlExecutionResult:
    raw_rows = list(cursor.fetchmany(request.options.maxRows + 1))
    limited = raw_rows[: request.options.maxRows]
    columns = _columns(cursor)
    rows = [_row_to_dict(row, columns) for row in limited]
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


def _dml_result(
    connection: Any,
    cursor: Any,
    db_type: str,
    request: SqlExecutionRequest,
    generated_key_strategy: str,
) -> SqlExecutionResult:
    affected_rows = max(int(getattr(cursor, "rowcount", 0) or 0), 0)
    if request.safety.maxAffectedRows is not None and affected_rows > request.safety.maxAffectedRows:
        _rollback_quietly(connection)
        return SqlExecutionResult.failed(
            db_type=db_type,
            operation=request.operation,
            error_type="SqlSafetyError",
            message=(f"实际影响行数 {affected_rows} 超过最大允许影响行数 {request.safety.maxAffectedRows}。"),
        )
    _commit_quietly(connection)
    last_insert_id = _last_insert_id(cursor, generated_key_strategy, request.operation)
    return SqlExecutionResult(
        success=True,
        dbType=db_type,
        operation=request.operation,
        affectedRows=affected_rows,
        lastInsertId=last_insert_id,
        generatedKeys=[last_insert_id] if last_insert_id is not None else [],
    )


def _columns(cursor: Any) -> list[SqlResultColumn]:
    columns: list[SqlResultColumn] = []
    for description in getattr(cursor, "description", None) or []:
        name = str(description[0])
        type_code = description[1] if len(description) > 1 else None
        columns.append(SqlResultColumn(name=name, type=None if type_code is None else str(type_code)))
    return columns


def _row_to_dict(row: Any, columns: list[SqlResultColumn]) -> dict[str, Any]:
    if isinstance(row, dict):
        return {str(key): jsonable(value) for key, value in row.items()}
    return {column.name: jsonable(row[index] if index < len(row) else None) for index, column in enumerate(columns)}


def _last_insert_id(cursor: Any, strategy: str, operation: SqlOperation) -> Any:
    if operation != SqlOperation.INSERT or strategy == "none":
        return None
    return getattr(cursor, "lastrowid", None)


def _commit_quietly(connection: Any) -> None:
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()


def _rollback_quietly(connection: Any) -> None:
    rollback = getattr(connection, "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception:
            pass


def _close_quietly(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def friendly_sql_error(error_type: str, raw_message: str) -> tuple[str, str]:
    """将数据库驱动原始异常转换为面向用户的友好中文消息。

    返回 (稳定 error_type, 友好的 message)，不暴露内部 IP、端口、
    驱动类名和源代码路径。

    Args:
        error_type: 原始 Python 异常类名，如 ``OperationalError``。
        raw_message: 原始异常消息 ``str(exc)``。

    Returns:
        (stable_type, friendly_message) 元组。
    """
    msg_lower = raw_message.lower()

    # 连接类错误
    if any(kw in msg_lower for kw in (
        "can't connect", "connection refused", "connect_timeout",
        "no route to host", "name or service not known",
        "getaddrinfo failed", "network is unreachable",
        "connection reset", "broken pipe",
    )):
        return ("连接失败", "无法连接到数据库服务器，请检查数据库地址、端口是否正确，以及数据库服务是否正常运行。")

    # 超时类错误
    if any(kw in msg_lower for kw in (
        "timeout", "timed out", "lock wait timeout",
        "statement timeout", "deadlock",
    )):
        if "lock wait" in msg_lower or "deadlock" in msg_lower:
            return ("执行超时", "SQL 执行超时（锁等待或死锁），请检查是否存在长时间事务或适当增加超时时间。")
        return ("连接超时", "连接数据库超时，请检查网络连通性或适当增加超时时间。")

    # 认证类错误
    if any(kw in msg_lower for kw in (
        "access denied", "authentication failed",
        "password authentication", "invalid password",
        "logon denied", "ora-01017",
    )):
        return ("认证失败", "数据库用户名或密码错误，请检查数据源配置中的凭据信息。")

    # 数据库不存在
    if any(kw in msg_lower for kw in (
        "unknown database", "database does not exist",
        "ora-12514", "no such file or directory",
    )):
        return ("数据库不存在", "指定的数据库不存在，请检查数据库名称配置。")

    # 驱动未安装
    if error_type == "MissingDriverError":
        return ("MissingDriverError", raw_message)

    # SQL 语法错误
    if any(kw in msg_lower for kw in (
        "syntax error", "sql syntax", "ora-00900",
        "ora-00936", "you have an error in your sql",
    )):
        return ("SQL 语法错误", "SQL 语句存在语法错误，请检查 SQL 文本。")

    # 表/列不存在
    if any(kw in msg_lower for kw in (
        "doesn't exist", "does not exist", "no such table",
        "no such column", "ora-00942", "ora-00904",
        "undefined table", "undefined column",
    )):
        return ("对象不存在", "SQL 引用的表或列不存在，请检查 SQL 文本和数据库结构。")

    # 约束违反
    if any(kw in msg_lower for kw in (
        "integrity constraint", "duplicate entry",
        "unique constraint", "foreign key constraint",
        "ora-00001", "ora-02291", "ora-02292",
    )):
        return ("数据约束冲突", "数据操作违反约束条件（如唯一性、外键等），请检查数据。")

    # 文件类错误（SQLite）
    if error_type in ("FileNotFoundError", "OSError", "PermissionError"):
        return ("文件错误", "数据库文件不存在或无访问权限，请检查文件路径和权限。")

    # 兜底：返回类型泛化后的消息
    return ("执行异常", raw_message or "SQL 执行过程中发生未知错误。")
