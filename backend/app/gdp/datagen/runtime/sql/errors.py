"""SQL 运行时领域异常。"""

from __future__ import annotations


class SqlExecutionError(Exception):
    """SQL 运行时异常基类。"""


class SqlExecutionRequestError(SqlExecutionError):
    """执行请求不合法。"""


class SqlParameterError(SqlExecutionRequestError):
    """SQL 参数缺失或不合法。"""


class SqlSafetyError(SqlExecutionError):
    """SQL 安全策略拒绝执行语句。"""


class UnsupportedDatabaseError(SqlExecutionError):
    """请求的数据库类型还没有可执行实现。"""


class SqlDatabaseError(SqlExecutionError):
    """数据库驱动抛出了执行异常。"""
