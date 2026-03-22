from deerflow.nlp2sql.adapters.mysql import MySQLAdapter


class PolarDBAdapter(MySQLAdapter):
    explain_prefix = "EXPLAIN"
