"""Runtime helpers for DeerFlow tracing."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from deerflow.config.paths import resolve_path
from deerflow.config.tracing_config import get_langfuse_config, get_tracing_config, is_langfuse_enabled, is_tracing_enabled
from deerflow.tracing.local_logger import LocalFileTraceCallbackHandler, get_local_trace_logger

logger = logging.getLogger(__name__)


def get_trace_log_path() -> Path:
    """Resolve the local structured trace log path."""
    return resolve_path(get_tracing_config().trace_log_path)


def _merge_tags(existing: list[str] | None, new_tags: list[str] | None) -> list[str]:
    merged: list[str] = []
    for value in [*(existing or []), *(new_tags or [])]:
        if value not in merged:
            merged.append(value)
    return merged


def _ensure_trace_identifiers(metadata: dict[str, Any]) -> dict[str, Any]:
    if not metadata.get("trace_id"):
        metadata["trace_id"] = uuid.uuid4().hex
    if not metadata.get("trace_root_span_id"):
        metadata["trace_root_span_id"] = uuid.uuid4().hex[:16]
    return metadata


def _build_metadata(
    *,
    session_id: str | None,
    metadata: dict[str, Any] | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    _ensure_trace_identifiers(merged)

    if session_id:
        merged.setdefault("trace_session_id", session_id)

    if tags:
        merged["trace_tags"] = _merge_tags(merged.get("trace_tags"), tags)

    if is_langfuse_enabled():
        if session_id:
            merged["langfuse_session_id"] = session_id
        if tags:
            merged["langfuse_tags"] = _merge_tags(merged.get("langfuse_tags"), tags)

    return merged


def ensure_langfuse_client() -> bool:
    """Initialize the Langfuse singleton client if tracing is enabled."""
    if not is_langfuse_enabled():
        return False

    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning("Langfuse tracing is enabled but the langfuse package is not installed; falling back to local trace logs.")
        return False

    config = get_langfuse_config()
    try:
        Langfuse(
            public_key=config.public_key,
            secret_key=config.secret_key,
            base_url=config.base_url,
            environment=config.environment,
            release=config.release,
        )
    except Exception:
        logger.exception("Failed to initialize Langfuse client; falling back to local trace logs.")
        return False

    return True


def build_root_callbacks(
    *,
    session_id: str | None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    run_name: str | None = None,
) -> list[Any]:
    """Return callback handlers for a root execution."""
    merged_metadata = _build_metadata(session_id=session_id, metadata=metadata, tags=tags)

    if ensure_langfuse_client():
        try:
            from langfuse.langchain import CallbackHandler

            return [CallbackHandler()]
        except Exception:
            logger.exception("Failed to create Langfuse callback handler; falling back to local trace logs.")

    logger.info("Tracing is %s; writing structured traces to %s", "disabled" if not is_tracing_enabled() else "using local fallback", get_trace_log_path())
    return [
        LocalFileTraceCallbackHandler(
            logger=get_local_trace_logger(get_trace_log_path()),
            session_id=session_id,
            default_trace_id=str(merged_metadata["trace_id"]),
            root_span_id=str(merged_metadata["trace_root_span_id"]),
            default_name=run_name,
        )
    ]


def build_child_callbacks(
    *,
    session_id: str | None,
    trace_context: dict[str, str] | None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    run_name: str | None = None,
) -> list[Any]:
    """Return callback handlers for a child execution."""
    merged_metadata = _build_metadata(session_id=session_id, metadata=metadata, tags=tags)

    if ensure_langfuse_client():
        try:
            from langfuse.langchain import CallbackHandler

            return [CallbackHandler(trace_context=trace_context)]
        except Exception:
            logger.exception("Failed to create Langfuse child callback handler; falling back to local trace logs.")

    return [
        LocalFileTraceCallbackHandler(
            logger=get_local_trace_logger(get_trace_log_path()),
            session_id=session_id,
            default_trace_id=str(merged_metadata["trace_id"]),
            root_span_id=str(merged_metadata["trace_root_span_id"]),
            trace_context=trace_context,
            default_name=run_name,
        )
    ]


def get_current_trace_context(config: dict[str, Any] | None = None) -> dict[str, str] | None:
    """Return the current active trace/span context if one is available."""
    try:
        from opentelemetry import trace as otel_trace

        span = otel_trace.get_current_span()
        span_context = span.get_span_context()
        if span_context and span_context.is_valid:
            return {
                "trace_id": f"{span_context.trace_id:032x}",
                "parent_span_id": f"{span_context.span_id:016x}",
            }
    except Exception:
        pass

    metadata = dict((config or {}).get("metadata", {}))
    trace_id = metadata.get("trace_id")
    parent_span_id = metadata.get("trace_root_span_id")
    if trace_id and parent_span_id:
        return {
            "trace_id": str(trace_id),
            "parent_span_id": str(parent_span_id),
        }
    return None


def prepare_root_runnable_config(
    config: dict[str, Any],
    *,
    session_id: str | None,
    run_name: str,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Attach root tracing metadata and callbacks to a runnable config."""
    merged_metadata = _build_metadata(session_id=session_id, metadata=config.get("metadata") or metadata, tags=tags)
    if metadata:
        merged_metadata.update(metadata)
        _ensure_trace_identifiers(merged_metadata)

    config["metadata"] = merged_metadata
    config["callbacks"] = [*(config.get("callbacks") or []), *build_root_callbacks(session_id=session_id, metadata=merged_metadata, tags=tags, run_name=run_name)]
    config["tags"] = _merge_tags(config.get("tags"), tags)
    config["run_name"] = run_name
    return config


def prepare_child_runnable_config(
    config: dict[str, Any],
    *,
    session_id: str | None,
    run_name: str,
    trace_context: dict[str, str] | None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Attach child tracing metadata and callbacks to a runnable config."""
    merged_metadata = _build_metadata(session_id=session_id, metadata=config.get("metadata") or metadata, tags=tags)
    if metadata:
        merged_metadata.update(metadata)
        _ensure_trace_identifiers(merged_metadata)

    config["metadata"] = merged_metadata
    config["callbacks"] = [*(config.get("callbacks") or []), *build_child_callbacks(session_id=session_id, trace_context=trace_context, metadata=merged_metadata, tags=tags, run_name=run_name)]
    config["tags"] = _merge_tags(config.get("tags"), tags)
    config["run_name"] = run_name
    return config
