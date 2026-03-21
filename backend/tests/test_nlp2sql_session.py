from datetime import timedelta

from deerflow.nlp2sql.session import ThreadSessionStore
from deerflow.nlp2sql.types import utc_now


def test_session_store_evicts_expired_sessions():
    store = ThreadSessionStore(ttl_seconds=60)
    stale = store.get_or_create("stale-thread")
    stale.last_used_at = utc_now() - timedelta(minutes=5)

    current = store.get_or_create("current-thread")

    assert store.get("stale-thread") is None
    assert store.get("current-thread") is current
