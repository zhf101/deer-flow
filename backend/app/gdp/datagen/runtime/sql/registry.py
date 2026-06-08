"""按数据库类型分派的 SQL 执行器注册表。"""

from __future__ import annotations

from app.gdp.datagen.runtime.sql.base import SqlExecutor
from app.gdp.datagen.runtime.sql.errors import UnsupportedDatabaseError
from app.gdp.datagen.runtime.sql.executors.goldendb import GoldenDbSqlExecutor
from app.gdp.datagen.runtime.sql.executors.mysql import MySqlSqlExecutor
from app.gdp.datagen.runtime.sql.executors.opengauss import OpenGaussSqlExecutor
from app.gdp.datagen.runtime.sql.executors.oracle import OracleSqlExecutor
from app.gdp.datagen.runtime.sql.executors.sqlite import SQLiteSqlExecutor
from app.gdp.datagen.runtime.sql.executors.tidb import TiDbSqlExecutor


class SqlExecutorRegistry:
    """按数据库类型保持独立执行器边界的注册表。"""

    def __init__(self) -> None:
        self._executors: dict[str, SqlExecutor] = {
            "sqlite": SQLiteSqlExecutor(),
            "mysql": MySqlSqlExecutor(),
            "oracle": OracleSqlExecutor(),
            "tidb": TiDbSqlExecutor(),
            "opengauss": OpenGaussSqlExecutor(),
            "goldendb": GoldenDbSqlExecutor(),
        }

    def get(self, db_type: str) -> SqlExecutor:
        key = normalize_db_type(db_type)
        if key not in self._executors:
            raise UnsupportedDatabaseError(f"unsupported database type: {db_type}")
        return self._executors[key]


def normalize_db_type(db_type: str) -> str:
    text = (db_type or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "sqlite": "sqlite",
        "sqllite": "sqlite",
        "sqlite3": "sqlite",
        "mysql": "mysql",
        "oracle": "oracle",
        "tidb": "tidb",
        "opengauss": "opengauss",
        "goldendb": "goldendb",
    }
    return aliases.get(text, text)
