from deerflow.nlp2sql.adapters.mysql import MySQLAdapter
from deerflow.nlp2sql.adapters.postgres import PostgresAdapter
from deerflow.nlp2sql.types import DataSourceConfig, DatabaseType


def create_adapter(config: DataSourceConfig):
    if config.db_type == DatabaseType.MYSQL:
        return MySQLAdapter(config)
    if config.db_type == DatabaseType.POSTGRES:
        return PostgresAdapter(config)
    raise ValueError(f"Unsupported database type: {config.db_type}")
