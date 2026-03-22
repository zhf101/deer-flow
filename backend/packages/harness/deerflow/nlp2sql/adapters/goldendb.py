from deerflow.nlp2sql.adapters.mysql import MySQLAdapter


class GoldenDBAdapter(MySQLAdapter):
    explain_prefix = "EXPLAIN"
