from deerflow.nlp2sql.adapters.dm import DMAdapter
from deerflow.nlp2sql.adapters.gaussdb import GaussDBAdapter
from deerflow.nlp2sql.adapters.goldendb import GoldenDBAdapter
from deerflow.nlp2sql.adapters.kingbase import KingbaseAdapter
from deerflow.nlp2sql.adapters.mysql import MySQLAdapter
from deerflow.nlp2sql.adapters.oceanbase import OceanBaseAdapter
from deerflow.nlp2sql.adapters.opengauss import OpenGaussAdapter
from deerflow.nlp2sql.adapters.oracle import OracleAdapter
from deerflow.nlp2sql.adapters.polardb import PolarDBAdapter
from deerflow.nlp2sql.adapters.postgres import PostgresAdapter
from deerflow.nlp2sql.adapters.tidb import TiDBAdapter
from deerflow.nlp2sql.types import DatabaseType, DataSourceConfig


def create_adapter(config: DataSourceConfig):
    if config.db_type == DatabaseType.MYSQL:
        return MySQLAdapter(config)
    if config.db_type == DatabaseType.POSTGRES:
        return PostgresAdapter(config)
    if config.db_type == DatabaseType.ORACLE:
        return OracleAdapter(config)
    if config.db_type == DatabaseType.DM:
        return DMAdapter(config)
    if config.db_type == DatabaseType.KINGBASE:
        return KingbaseAdapter(config)
    if config.db_type == DatabaseType.GAUSSDB:
        return GaussDBAdapter(config)
    if config.db_type == DatabaseType.OPENGAUSS:
        return OpenGaussAdapter(config)
    if config.db_type == DatabaseType.OCEANBASE:
        return OceanBaseAdapter(config)
    if config.db_type == DatabaseType.TIDB:
        return TiDBAdapter(config)
    if config.db_type == DatabaseType.POLARDB:
        return PolarDBAdapter(config)
    if config.db_type == DatabaseType.GOLDENDB:
        return GoldenDBAdapter(config)
    raise ValueError(f"Unsupported database type: {config.db_type}")
