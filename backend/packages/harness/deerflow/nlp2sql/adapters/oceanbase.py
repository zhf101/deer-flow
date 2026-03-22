from deerflow.nlp2sql.adapters.mysql import MySQLAdapter


class OceanBaseAdapter(MySQLAdapter):
    explain_prefix = "EXPLAIN"
