from __future__ import annotations

import threading
from datetime import timedelta

from deerflow.nlp2sql.types import QueryExecutionResult, ThreadDatabaseSession, ValidationMode, utc_now


class ThreadSessionStore:
    """Per-process in-memory store for thread database context."""

    def __init__(self, ttl_seconds: int = 24 * 60 * 60) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, ThreadDatabaseSession] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def _evict_expired_locked(self) -> None:
        if self._ttl.total_seconds() <= 0:
            return
        cutoff = utc_now() - self._ttl
        expired = [
            thread_id
            for thread_id, session in self._sessions.items()
            if session.last_used_at < cutoff
        ]
        for thread_id in expired:
            self._sessions.pop(thread_id, None)

    def get(self, thread_id: str) -> ThreadDatabaseSession | None:
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(thread_id)
            if session is not None:
                session.touch()
            return session

    def get_or_create(self, thread_id: str) -> ThreadDatabaseSession:
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(thread_id)
            if session is None:
                session = ThreadDatabaseSession(thread_id=thread_id)
                self._sessions[thread_id] = session
            session.touch()
            return session

    def bind_data_source(self, thread_id: str, data_source_id: str) -> ThreadDatabaseSession:
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(thread_id) or ThreadDatabaseSession(thread_id=thread_id)
            session.data_source_id = data_source_id
            session.touch()
            self._sessions[thread_id] = session
            return session

    def set_validation_mode(self, thread_id: str, mode: ValidationMode) -> ThreadDatabaseSession:
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(thread_id) or ThreadDatabaseSession(thread_id=thread_id)
            session.validation_mode = mode
            session.touch()
            self._sessions[thread_id] = session
            return session

    def set_last_sql(self, thread_id: str, sql: str | None) -> None:
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(thread_id) or ThreadDatabaseSession(thread_id=thread_id)
            session.last_sql = sql
            session.touch()
            self._sessions[thread_id] = session

    def set_last_result(self, thread_id: str, result: QueryExecutionResult | None) -> None:
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(thread_id) or ThreadDatabaseSession(thread_id=thread_id)
            session.last_result = result
            session.touch()
            self._sessions[thread_id] = session

    def clear(self, thread_id: str) -> None:
        with self._lock:
            self._sessions.pop(thread_id, None)


_session_store: ThreadSessionStore | None = None


def get_session_store() -> ThreadSessionStore:
    global _session_store
    if _session_store is None:
        _session_store = ThreadSessionStore()
    return _session_store


def _reset_session_store() -> None:
    global _session_store
    _session_store = None
