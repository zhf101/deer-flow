from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.nlp2sql.errors import NoDataSourceSelectedError
from deerflow.nlp2sql.export import export_last_result
from deerflow.nlp2sql.registry import get_data_source_registry
from deerflow.nlp2sql.retrieval_service import get_retrieval_service
from deerflow.nlp2sql.service import get_database_service
from deerflow.nlp2sql.session import get_session_store
from deerflow.nlp2sql.types import ValidationMode


def _json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _get_thread_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    thread_id = runtime.context.get("thread_id")
    if not thread_id:
        raise ValueError("Thread ID is not available in runtime context")
    return thread_id


def _get_data_source_id(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    session = get_session_store().get(_get_thread_id(runtime))
    if session is None or not session.data_source_id:
        raise NoDataSourceSelectedError("No data source selected for this thread. Call use_data_source first.")
    return session.data_source_id


@tool("list_data_sources", parse_docstring=True)
def list_data_sources_tool(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """List enabled database data sources that the agent can bind to the current thread."""
    _ = runtime
    registry = get_data_source_registry()
    data_sources = [
        {
            "id": item.id,
            "name": item.name,
            "db_type": item.db_type.value,
            "host": item.host,
            "port": item.port,
            "database": item.database,
            "readonly": item.readonly,
            "enabled": item.enabled,
            "description": item.description,
        }
        for item in registry.list(enabled_only=True)
    ]
    return _json_dump({"data_sources": data_sources})


@tool("use_data_source", parse_docstring=True)
def use_data_source_tool(runtime: ToolRuntime[ContextT, ThreadState], data_source_id: str) -> str:
    """Bind a database data source to the current thread.

    Args:
        data_source_id: The ID of the data source to bind to the current thread.
    """
    thread_id = _get_thread_id(runtime)
    registry = get_data_source_registry()
    config = registry.get(data_source_id)
    get_session_store().bind_data_source(thread_id, config.id)
    get_session_store().set_validation_mode(thread_id, config.default_validation_mode)
    return _json_dump(
        {
            "message": f"Bound thread to data source '{config.name}'",
            "data_source_id": config.id,
            "default_validation_mode": config.default_validation_mode.value,
        }
    )


@tool("get_current_data_source", parse_docstring=True)
def get_current_data_source_tool(runtime: ToolRuntime[ContextT, ThreadState]) -> str:
    """Return the data source currently bound to the thread."""
    try:
        data_source_id = _get_data_source_id(runtime)
    except NoDataSourceSelectedError:
        return _json_dump({"data_source": None})
    config = get_data_source_registry().get(data_source_id)
    return _json_dump({"data_source": config.model_dump(mode="json")})


@tool("search_schema", parse_docstring=True)
def search_schema_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    query: str,
    limit: int = 10,
) -> str:
    """Search the current data source schema by table names, column names, and comments.

    Args:
        query: Natural language schema search query.
        limit: Maximum number of hits to return.
    """
    service = get_database_service()
    hits = service.search_schema(_get_data_source_id(runtime), query=query, limit=limit)
    return _json_dump({"hits": [hit.model_dump(mode="json") for hit in hits]})


@tool("get_table_info", parse_docstring=True)
def get_table_info_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    table_name: str,
    schema_name: str | None = None,
) -> str:
    """Get detailed metadata for one table from the current data source.

    Args:
        table_name: The table name.
        schema_name: Optional schema name when the database supports multiple schemas.
    """
    service = get_database_service()
    table_info = service.get_table_info(_get_data_source_id(runtime), table_name=table_name, schema_name=schema_name)
    return _json_dump(table_info)


@tool("get_relationships", parse_docstring=True)
def get_relationships_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    table_names: list[str],
) -> str:
    """Get foreign-key relationships for the selected tables.

    Args:
        table_names: List of table names to inspect.
    """
    service = get_database_service()
    relationships = service.get_relationships(_get_data_source_id(runtime), table_names=table_names)
    return _json_dump({"relationships": relationships})


@tool("get_enum_values", parse_docstring=True)
def get_enum_values_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    table_name: str,
    column_name: str,
    schema_name: str | None = None,
    limit: int = 50,
) -> str:
    """Inspect likely enum values for a column.

    Args:
        table_name: The table to inspect.
        column_name: The column to inspect.
        schema_name: Optional schema name.
        limit: Maximum number of values to return.
    """
    service = get_database_service()
    values = service.get_enum_values(
        _get_data_source_id(runtime),
        table_name=table_name,
        column_name=column_name,
        schema_name=schema_name,
        limit=limit,
    )
    return _json_dump({"values": values})


@tool("get_sample_rows", parse_docstring=True)
def get_sample_rows_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    table_name: str,
    schema_name: str | None = None,
    limit: int = 5,
) -> str:
    """Fetch a few sample rows from a table.

    Args:
        table_name: The table to sample.
        schema_name: Optional schema name.
        limit: Maximum number of rows to return.
    """
    service = get_database_service()
    rows = service.get_sample_rows(
        _get_data_source_id(runtime),
        table_name=table_name,
        schema_name=schema_name,
        limit=limit,
    )
    return _json_dump({"rows": rows})


@tool("retrieve_knowledge_context", parse_docstring=True)
def retrieve_knowledge_context_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    query: str,
    limit_per_bucket: int = 4,
) -> str:
    """Retrieve trainable SQL knowledge and schema evidence for the current thread.

    Call this after `use_data_source` and before drafting SQL whenever the user's
    question depends on business semantics, metric definitions, example SQL, join
    conventions, or domain-specific documentation.

    Args:
        query: Natural-language business question to use for retrieval.
        limit_per_bucket: Maximum number of hits to keep for each evidence bucket.
    """
    retrieval = get_retrieval_service().preview(
        data_source_id=_get_data_source_id(runtime),
        query=query,
        limit_per_bucket=limit_per_bucket,
    )
    return _json_dump(retrieval.model_dump(mode="json"))


@tool("validate_sql", parse_docstring=True)
def validate_sql_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    sql: str,
    mode: str = "relaxed",
) -> str:
    """Validate read-only SQL against the current data source.

    Args:
        sql: The SQL query to validate.
        mode: Validation mode, either `relaxed` or `strict`.
    """
    validation_mode = ValidationMode(mode)
    result = get_database_service().validate_sql(_get_data_source_id(runtime), sql=sql, mode=validation_mode)
    return _json_dump(result.model_dump(mode="json"))


@tool("execute_sql", parse_docstring=True)
def execute_sql_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    sql: str,
    params: list[str] | None = None,
) -> str:
    """Execute validated read-only SQL against the current data source.

    Args:
        sql: The SQL query to execute.
        params: Optional query parameters.
    """
    thread_id = _get_thread_id(runtime)
    result = get_database_service().execute_sql(_get_data_source_id(runtime), sql=sql, params=params)
    session_store = get_session_store()
    session_store.set_last_sql(thread_id, result.sql)
    session_store.set_last_result(thread_id, result)
    return _json_dump(result.model_dump(mode="json"))


@tool("export_query_result", parse_docstring=True)
def export_query_result_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    format: str = "csv",
    filename: str | None = None,
) -> Command:
    """Export the most recent query result to the current thread's outputs directory.

    Args:
        format: Output format, one of csv, json, md, markdown.
        filename: Optional output filename.
    """
    thread_id = _get_thread_id(runtime)
    session = get_session_store().get(thread_id)
    if session is None or session.last_result is None:
        return Command(
            update={"messages": [ToolMessage("Error: No query result available to export", tool_call_id=tool_call_id)]},
        )

    if runtime.state is None:
        return Command(
            update={"messages": [ToolMessage("Error: Thread runtime state is not available", tool_call_id=tool_call_id)]},
        )

    thread_data = runtime.state.get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    if not outputs_path:
        return Command(
            update={"messages": [ToolMessage("Error: Thread outputs path is not available", tool_call_id=tool_call_id)]},
        )

    output_path = export_last_result(Path(outputs_path), session.last_result, format=format, filename=filename)
    relative_path = output_path.relative_to(Path(outputs_path))
    virtual_path = f"/mnt/user-data/outputs/{relative_path.as_posix()}"

    return Command(
        update={
            "artifacts": [virtual_path],
            "messages": [ToolMessage(f"Successfully exported query result to {virtual_path}", tool_call_id=tool_call_id)],
        }
    )
