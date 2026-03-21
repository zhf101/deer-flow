"""Local structured trace logging for DeerFlow.

This module provides a lightweight LangChain callback handler that records
trace/span lifecycle events to a JSONL file when remote tracing is disabled.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_jsonable(value: Any, *, max_length: int = 2000) -> Any:
    """Convert arbitrary callback payloads into JSON-safe summaries."""
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return value if len(value) <= max_length else value[:max_length] + "..."

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _safe_jsonable(v, max_length=max_length) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_safe_jsonable(v, max_length=max_length) for v in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _safe_jsonable(model_dump(), max_length=max_length)
        except Exception:
            pass

    text = repr(value)
    return text if len(text) <= max_length else text[:max_length] + "..."


class LocalTraceLogger:
    """Append-only JSONL writer used by local tracing callbacks."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")


_loggers: dict[Path, LocalTraceLogger] = {}
_loggers_lock = threading.Lock()


def get_local_trace_logger(path: Path) -> LocalTraceLogger:
    """Return a singleton JSONL logger for ``path``."""
    resolved = path.resolve()
    with _loggers_lock:
        logger = _loggers.get(resolved)
        if logger is None:
            logger = LocalTraceLogger(resolved)
            _loggers[resolved] = logger
        return logger


class LocalFileTraceCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that writes structured span events to JSONL."""

    raise_error = False
    run_inline = True

    def __init__(
        self,
        *,
        logger: LocalTraceLogger,
        session_id: str | None = None,
        default_trace_id: str | None = None,
        root_span_id: str | None = None,
        trace_context: dict[str, str] | None = None,
        default_name: str | None = None,
    ) -> None:
        super().__init__()
        self._logger = logger
        self._session_id = session_id
        self._default_trace_id = default_trace_id
        self._root_span_id = root_span_id
        self._trace_context = trace_context or {}
        self._default_name = default_name
        self._run_state: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _stringify_run_id(run_id: UUID | str) -> str:
        return str(run_id)

    @staticmethod
    def _resolve_name(serialized: dict[str, Any] | None, kwargs: dict[str, Any], fallback: str | None = None) -> str:
        if kwargs.get("name"):
            return str(kwargs["name"])
        if serialized and serialized.get("name"):
            return str(serialized["name"])
        if serialized and serialized.get("id"):
            try:
                return str(serialized["id"][-1])
            except Exception:
                pass
        return fallback or "<unknown>"

    def _register_run(
        self,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        span_type: str,
        serialized: dict[str, Any] | None,
        payload: Any,
        tags: list[str] | None,
        metadata: dict[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        run_key = self._stringify_run_id(run_id)
        parent_key = self._stringify_run_id(parent_run_id) if parent_run_id else None
        parent_state = self._run_state.get(parent_key) if parent_key else None

        trace_id = parent_state["trace_id"] if parent_state else self._trace_context.get("trace_id") or self._default_trace_id or run_key
        span_id = (
            self._root_span_id
            if parent_state is None and self._root_span_id is not None
            else run_key
        )
        effective_parent_span_id = (
            parent_state["span_id"]
            if parent_state is not None
            else self._trace_context.get("parent_span_id")
        )

        state = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": effective_parent_span_id,
            "session_id": self._session_id,
            "type": span_type,
            "name": self._resolve_name(serialized, kwargs, self._default_name),
            "started_at": _utc_now(),
            "tags": list(tags or []),
            "metadata": _safe_jsonable(metadata or {}),
        }
        self._run_state[run_key] = state

        if parent_state is None:
            self._logger.emit(
                {
                    "ts": state["started_at"],
                    "kind": "trace_start",
                    "trace_id": trace_id,
                    "session_id": self._session_id,
                    "name": state["name"],
                    "metadata": state["metadata"],
                    "tags": state["tags"],
                }
            )

        self._logger.emit(
            {
                "ts": state["started_at"],
                "kind": "span_start",
                "trace_id": trace_id,
                "session_id": self._session_id,
                "span_id": span_id,
                "parent_span_id": effective_parent_span_id,
                "name": state["name"],
                "type": span_type,
                "input": _safe_jsonable(payload),
                "metadata": state["metadata"],
                "tags": state["tags"],
            }
        )
        return state

    def _finish_run(self, run_id: UUID, *, status: str, payload: Any = None, error: Any = None) -> None:
        run_key = self._stringify_run_id(run_id)
        state = self._run_state.pop(run_key, None)
        if state is None:
            return

        finished_at = _utc_now()
        self._logger.emit(
            {
                "ts": finished_at,
                "kind": "span_end",
                "trace_id": state["trace_id"],
                "session_id": state["session_id"],
                "span_id": state["span_id"],
                "parent_span_id": state["parent_span_id"],
                "name": state["name"],
                "type": state["type"],
                "status": status,
                "output": _safe_jsonable(payload),
                "error": _safe_jsonable(error),
            }
        )

        if state["parent_span_id"] is None:
            self._logger.emit(
                {
                    "ts": finished_at,
                    "kind": "trace_end",
                    "trace_id": state["trace_id"],
                    "session_id": state["session_id"],
                    "name": state["name"],
                    "status": status,
                    "error": _safe_jsonable(error),
                }
            )

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._register_run(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type="chain",
            serialized=serialized,
            payload=inputs,
            tags=tags,
            metadata=metadata,
            kwargs=kwargs,
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="ok", payload=outputs)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="error", error=error)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._register_run(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type="generation",
            serialized=serialized,
            payload=messages,
            tags=tags,
            metadata=metadata,
            kwargs=kwargs,
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._register_run(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type="generation",
            serialized=serialized,
            payload=prompts,
            tags=tags,
            metadata=metadata,
            kwargs=kwargs,
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="ok", payload=response)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="error", error=error)

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._register_run(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type="tool",
            serialized=serialized,
            payload=input_str,
            tags=tags,
            metadata=metadata,
            kwargs=kwargs,
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="ok", payload=output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="error", error=error)

    def on_retriever_start(
        self,
        serialized: dict[str, Any] | None,
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._register_run(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type="retriever",
            serialized=serialized,
            payload=query,
            tags=tags,
            metadata=metadata,
            kwargs=kwargs,
        )

    def on_retriever_end(
        self,
        documents: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="ok", payload=documents)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._finish_run(run_id, status="error", error=error)
