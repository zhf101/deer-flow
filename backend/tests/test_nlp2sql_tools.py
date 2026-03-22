from types import SimpleNamespace

import deerflow.nlp2sql.tools as nlp2sql_tools
from deerflow.nlp2sql.knowledge_types import RetrievalPreviewResponse
from deerflow.nlp2sql.session import get_session_store
from deerflow.nlp2sql.tools import export_query_result_tool, retrieve_knowledge_context_tool
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


def test_retrieve_knowledge_context_tool_uses_bound_data_source(monkeypatch, tmp_path):
    session_store = get_session_store()
    session_store.clear("thread-1")
    session_store.bind_data_source("thread-1", "sales-db")

    preview = RetrievalPreviewResponse.model_validate(
        {
            "query": "gmv",
            "data_source_id": "sales-db",
            "active_embedding_profile_id": "profile-1",
            "buckets": [
                {
                    "bucket": "documentation",
                    "hits": [
                        {
                            "bucket": "documentation",
                            "item_id": "knowledge-1",
                            "chunk_id": "chunk-1",
                            "title": "GMV definition",
                            "snippet": "GMV excludes cancelled orders.",
                            "score": 0.92,
                            "match_sources": ["semantic"],
                        }
                    ],
                }
            ],
            "warnings": [],
        }
    )

    class StubRetrievalService:
        def preview(self, *, data_source_id: str, query: str, limit_per_bucket: int):
            assert data_source_id == "sales-db"
            assert query == "gmv"
            assert limit_per_bucket == 5
            return preview

    monkeypatch.setattr(nlp2sql_tools, "get_retrieval_service", lambda: StubRetrievalService())

    result = retrieve_knowledge_context_tool.func(
        runtime=_make_runtime(str(tmp_path)),
        query="gmv",
        limit_per_bucket=5,
    )

    assert '"data_source_id": "sales-db"' in result
    assert '"active_embedding_profile_id": "profile-1"' in result
