import json

from deerflow.nlp2sql.export import export_last_result
from deerflow.nlp2sql.types import QueryExecutionResult


def _result() -> QueryExecutionResult:
    return QueryExecutionResult(
        sql="SELECT id, status FROM orders LIMIT 2",
        columns=["id", "status"],
        rows=[{"id": 1, "status": "paid"}, {"id": 2, "status": "pending"}],
        row_count=2,
        fetched_row_count=2,
        truncated=False,
        execution_ms=10,
        data_source_id="sales-db",
    )


def test_export_last_result_writes_csv_json_and_markdown(tmp_path):
    csv_path = export_last_result(tmp_path, _result(), format="csv", filename="orders")
    json_path = export_last_result(tmp_path, _result(), format="json", filename="orders")
    md_path = export_last_result(tmp_path, _result(), format="markdown", filename="orders")

    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "id,status",
        "1,paid",
        "2,pending",
    ]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["fetched_row_count"] == 2
    assert md_path.read_text(encoding="utf-8").splitlines() == [
        "| id | status |",
        "|---|---|",
        "| 1 | paid |",
        "| 2 | pending |",
    ]
