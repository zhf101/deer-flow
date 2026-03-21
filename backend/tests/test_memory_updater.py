from unittest.mock import patch

from deerflow.agents.memory.updater import MemoryUpdater
from deerflow.config.memory_config import MemoryConfig


def _make_memory(facts: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "version": "1.0",
        "lastUpdated": "",
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentMonths": {"summary": "", "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        },
        "facts": facts or [],
    }


def _memory_config(**overrides: object) -> MemoryConfig:
    config = MemoryConfig()
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_apply_updates_skips_existing_duplicate_and_preserves_removals() -> None:
    updater = MemoryUpdater()
    current_memory = _make_memory(
        facts=[
            {
                "id": "fact_existing",
                "content": "User likes Python",
                "category": "preference",
                "confidence": 0.9,
                "createdAt": "2026-03-18T00:00:00Z",
                "source": "thread-a",
            },
            {
                "id": "fact_remove",
                "content": "Old context to remove",
                "category": "context",
                "confidence": 0.8,
                "createdAt": "2026-03-18T00:00:00Z",
                "source": "thread-a",
            },
        ]
    )
    update_data = {
        "factsToRemove": ["fact_remove"],
        "newFacts": [
            {"content": "User likes Python", "category": "preference", "confidence": 0.95},
        ],
    }

    with patch(
        "deerflow.agents.memory.updater.get_memory_config",
        return_value=_memory_config(max_facts=100, fact_confidence_threshold=0.7),
    ):
        result = updater._apply_updates(current_memory, update_data, thread_id="thread-b")

    assert [fact["content"] for fact in result["facts"]] == ["User likes Python"]
    assert all(fact["id"] != "fact_remove" for fact in result["facts"])


def test_apply_updates_skips_same_batch_duplicates_and_keeps_source_metadata() -> None:
    updater = MemoryUpdater()
    current_memory = _make_memory()
    update_data = {
        "newFacts": [
            {"content": "User prefers dark mode", "category": "preference", "confidence": 0.91},
            {"content": "User prefers dark mode", "category": "preference", "confidence": 0.92},
            {"content": "User works on DeerFlow", "category": "context", "confidence": 0.87},
        ],
    }

    with patch(
        "deerflow.agents.memory.updater.get_memory_config",
        return_value=_memory_config(max_facts=100, fact_confidence_threshold=0.7),
    ):
        result = updater._apply_updates(current_memory, update_data, thread_id="thread-42")

    assert [fact["content"] for fact in result["facts"]] == [
        "User prefers dark mode",
        "User works on DeerFlow",
    ]
    assert all(fact["id"].startswith("fact_") for fact in result["facts"])
    assert all(fact["source"] == "thread-42" for fact in result["facts"])


def test_apply_updates_preserves_threshold_and_max_facts_trimming() -> None:
    updater = MemoryUpdater()
    current_memory = _make_memory(
        facts=[
            {
                "id": "fact_python",
                "content": "User likes Python",
                "category": "preference",
                "confidence": 0.95,
                "createdAt": "2026-03-18T00:00:00Z",
                "source": "thread-a",
            },
            {
                "id": "fact_dark_mode",
                "content": "User prefers dark mode",
                "category": "preference",
                "confidence": 0.8,
                "createdAt": "2026-03-18T00:00:00Z",
                "source": "thread-a",
            },
        ]
    )
    update_data = {
        "newFacts": [
            {"content": "User prefers dark mode", "category": "preference", "confidence": 0.9},
            {"content": "User uses uv", "category": "context", "confidence": 0.85},
            {"content": "User likes noisy logs", "category": "behavior", "confidence": 0.6},
        ],
    }

    with patch(
        "deerflow.agents.memory.updater.get_memory_config",
        return_value=_memory_config(max_facts=2, fact_confidence_threshold=0.7),
    ):
        result = updater._apply_updates(current_memory, update_data, thread_id="thread-9")

    assert [fact["content"] for fact in result["facts"]] == [
        "User likes Python",
        "User uses uv",
    ]
    assert all(fact["content"] != "User likes noisy logs" for fact in result["facts"])
    assert result["facts"][1]["source"] == "thread-9"


def test_update_memory_prepares_independent_root_trace(monkeypatch) -> None:
    updater = MemoryUpdater()
    messages = ["message-a", "message-b"]
    fake_model = patch("deerflow.agents.memory.updater.MemoryUpdater._get_model").start()
    fake_model.return_value.invoke.return_value.content = '{"user":{},"history":{},"factsToRemove":[],"newFacts":[]}'

    captured: dict[str, object] = {}

    def fake_prepare(config, *, session_id, run_name, metadata, tags=None):
        captured["session_id"] = session_id
        captured["run_name"] = run_name
        captured["metadata"] = metadata
        return {"callbacks": ["memory-root-callback"]}

    monkeypatch.setattr("deerflow.agents.memory.updater.get_memory_config", lambda: _memory_config(enabled=True))
    monkeypatch.setattr("deerflow.agents.memory.updater.get_memory_data", lambda agent_name=None: _make_memory())
    monkeypatch.setattr("deerflow.agents.memory.updater.format_conversation_for_update", lambda msgs: "conversation")
    monkeypatch.setattr("deerflow.agents.memory.updater.prepare_root_runnable_config", fake_prepare)
    monkeypatch.setattr("deerflow.agents.memory.updater._save_memory_to_file", lambda memory_data, agent_name=None: True)

    try:
        assert updater.update_memory(messages, thread_id="thread-memory", agent_name="memory-agent") is True
    finally:
        patch.stopall()

    fake_model.return_value.invoke.assert_called_once()
    assert fake_model.return_value.invoke.call_args.kwargs["config"] == {"callbacks": ["memory-root-callback"]}
    assert captured == {
        "session_id": "thread-memory",
        "run_name": "memory_update",
        "metadata": {
            "thread_id": "thread-memory",
            "agent_name": "memory-agent",
            "source": "memory_queue",
            "message_count": 2,
            "debounced": True,
        },
    }
