from types import SimpleNamespace

from deerflow.nlp2sql.session import get_session_store
from deerflow.nlp2sql.tools import export_query_result_tool
from deerflow.nlp2sql.types import QueryExecutionResult, ThreadDatabaseSession


def _make_runtime(outputs_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        state={"thread_data": {"outputs_path": outputs_path}},
        context={"thread_id": "thread-1"},
    )


def test_export_query_result_tool_updates_artifacts(tmp_path):
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()

    session_store = get_session_store()
    session_store.clear("thread-1")
    session = ThreadDatabaseSession(
        thread_id="thread-1",
        data_source_id="sales-db",
        last_result=QueryExecutionResult(
            sql="SELECT id FROM orders LIMIT 1",
            columns=["id"],
            rows=[{"id": 1}],
            row_count=1,
            fetched_row_count=1,
            truncated=False,
            execution_ms=12,
            data_source_id="sales-db",
        ),
    )
    session_store._sessions["thread-1"] = session

    result = export_query_result_tool.func(
        runtime=_make_runtime(str(outputs_dir)),
        tool_call_id="tc-1",
        format="json",
        filename="orders-export",
    )

    assert result.update["artifacts"] == ["/mnt/user-data/outputs/orders-export.json"]
    assert "Successfully exported query result" in result.update["messages"][0].content
