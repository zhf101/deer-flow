"""Tests for deerflow.config.tracing_config."""

from __future__ import annotations

from deerflow.config import tracing_config as tracing_module


def _reset_tracing_cache() -> None:
    tracing_module._tracing_config = None
    tracing_module._langfuse_config = None


def test_reads_deerflow_tracing_switch_and_log_path(monkeypatch):
    monkeypatch.setenv("DEERFLOW_TRACING_ENABLED", "true")
    monkeypatch.setenv("DEERFLOW_TRACE_LOG_PATH", "./custom/traces.jsonl")

    _reset_tracing_cache()
    cfg = tracing_module.get_tracing_config()

    assert cfg.enabled is True
    assert cfg.trace_log_path == "./custom/traces.jsonl"
    assert tracing_module.is_tracing_enabled() is True


def test_defaults_when_tracing_env_is_missing(monkeypatch):
    monkeypatch.delenv("DEERFLOW_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("DEERFLOW_TRACE_LOG_PATH", raising=False)

    _reset_tracing_cache()
    cfg = tracing_module.get_tracing_config()

    assert cfg.enabled is False
    assert cfg.trace_log_path == "./logs/traces.jsonl"


def test_langfuse_base_url_wins_over_host(monkeypatch):
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://base.example.com")
    monkeypatch.setenv("LANGFUSE_HOST", "https://host.example.com")

    _reset_tracing_cache()
    cfg = tracing_module.get_langfuse_config()

    assert cfg.base_url == "https://base.example.com"


def test_langfuse_host_is_used_as_fallback(monkeypatch):
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "https://host.example.com")

    _reset_tracing_cache()
    cfg = tracing_module.get_langfuse_config()

    assert cfg.base_url == "https://host.example.com"


def test_is_langfuse_enabled_requires_switch_and_complete_keys(monkeypatch):
    monkeypatch.setenv("DEERFLOW_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3001")

    _reset_tracing_cache()

    assert tracing_module.is_langfuse_enabled() is True


def test_is_langfuse_enabled_false_when_keys_incomplete(monkeypatch):
    monkeypatch.setenv("DEERFLOW_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    _reset_tracing_cache()

    assert tracing_module.is_langfuse_enabled() is False


def test_langsmith_envs_do_not_enable_tracing(monkeypatch):
    monkeypatch.delenv("DEERFLOW_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")

    _reset_tracing_cache()
    cfg = tracing_module.get_tracing_config()

    assert cfg.enabled is False
    assert tracing_module.is_tracing_enabled() is False
