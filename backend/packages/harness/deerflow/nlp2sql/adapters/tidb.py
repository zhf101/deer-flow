from deerflow.nlp2sql.adapters.mysql import MySQLAdapter


class TiDBAdapter(MySQLAdapter):
    explain_prefix = "EXPLAIN"
