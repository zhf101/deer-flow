"""GDP Agent LangGraph 观测配置测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent import graph as graph_module
from app.gdp.agent.observability import (
    build_gdp_trace_metadata,
    build_gdp_trace_tags,
    configure_gdp_observability,
)
from deerflow.config.tracing_config import reset_tracing_config


@pytest.fixture(autouse=True)
def _reset_tracing_env(monkeypatch):
    for name in (
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
        "LANGCHAIN_TRACING",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_tracing_config()
    yield
    reset_tracing_config()


def _runtime(**overrides):
    values = {
        "assistant_id": "gdp_agent",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-1",
        "operator": "operator-1",
        "model_name": "gpt-test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _metadata(**overrides):
    values = {
        "log_level": "debug",
        "policy": {"auditEnabled": True, "memoryEnabled": False},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_gdp_trace_metadata_only_contains_run_identity_and_policy():
    result = build_gdp_trace_metadata(runtime=_runtime(), metadata=_metadata())

    assert result == {
        "agent_name": "gdp_agent",
        "agent_kind": "gdp_datagen",
        "gdp_trace_payload_mode": "full",
        "assistant_id": "gdp_agent",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-1",
        "operator": "operator-1",
        "model_name": "gpt-test",
        "gdp_log_level": "debug",
        "gdp_policy": {"auditEnabled": True, "memoryEnabled": False},
    }
    assert "messages" not in result
    assert "input" not in result
    assert "payload" not in result


def test_build_gdp_trace_tags_includes_agent_model_and_environment(monkeypatch):
    monkeypatch.setenv("DEER_FLOW_ENV", "test")

    result = build_gdp_trace_tags(runtime=_runtime())

    assert result == [
        "gdp-datagen-agent",
        "assistant:gdp_agent",
        "model:gpt-test",
        "env:test",
    ]


def test_configure_gdp_observability_preserves_caller_config(monkeypatch):
    callback = object()
    monkeypatch.setattr("app.gdp.agent.observability.build_tracing_callbacks", lambda: [callback])
    config = {
        "run_name": "caller-run",
        "metadata": {
            "caller_key": "caller-value",
            "agent_name": "caller-agent",
            "thread_id": "caller-thread",
        },
        "tags": ["caller-tag", "gdp-datagen-agent"],
        "callbacks": ["caller-callback"],
    }

    configure_gdp_observability(config, runtime=_runtime(), metadata=_metadata())

    assert config["run_name"] == "caller-run"
    assert config["metadata"]["caller_key"] == "caller-value"
    assert config["metadata"]["agent_name"] == "caller-agent"
    assert config["metadata"]["thread_id"] == "caller-thread"
    assert config["metadata"]["agent_kind"] == "gdp_datagen"
    assert config["metadata"]["gdp_trace_payload_mode"] == "full"
    assert config["metadata"]["gdp_policy"] == {"auditEnabled": True, "memoryEnabled": False}
    assert config["tags"].count("gdp-datagen-agent") == 1
    assert "caller-tag" in config["tags"]
    assert "assistant:gdp_agent" in config["tags"]
    assert config["callbacks"] == ["caller-callback", callback]


def test_configure_gdp_observability_works_without_enabled_tracers(monkeypatch):
    monkeypatch.setattr("app.gdp.agent.observability.build_tracing_callbacks", lambda: [])
    monkeypatch.delenv("DEER_FLOW_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    config = {}

    configure_gdp_observability(config, runtime=_runtime(model_name=None), metadata=_metadata(log_level=None))

    assert config["run_name"] == "gdp_agent"
    assert "callbacks" not in config
    assert "model_name" not in config["metadata"]
    assert config["metadata"]["gdp_policy"] == {"auditEnabled": True, "memoryEnabled": False}
    assert config["tags"] == ["gdp-datagen-agent", "assistant:gdp_agent"]


def test_configure_gdp_observability_rejects_hidden_langsmith_payload(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    monkeypatch.setenv("LANGSMITH_HIDE_INPUTS", "true")
    reset_tracing_config()

    with pytest.raises(RuntimeError, match="完整模型请求和响应"):
        configure_gdp_observability({}, runtime=_runtime(), metadata=_metadata())


def test_make_gdp_agent_injects_observability_before_graph_build(monkeypatch):
    calls: dict[str, object] = {}
    services = object()

    def fake_observability(config, *, runtime, metadata):
        calls["observability_config"] = config
        calls["observability_runtime"] = runtime
        calls["observability_metadata"] = metadata
        config.setdefault("metadata", {})["observed"] = True

    def fake_build_services(*, app_config, runtime):
        calls["services_runtime"] = runtime
        return services

    def fake_make_gdp_graph(received_services, *, runtime, policy, metadata):
        calls["graph_services"] = received_services
        calls["graph_runtime"] = runtime
        calls["graph_policy"] = policy
        calls["graph_metadata"] = metadata
        return "graph"

    monkeypatch.setattr(graph_module, "configure_gdp_observability", fake_observability)
    monkeypatch.setattr(graph_module, "_build_services", fake_build_services)
    monkeypatch.setattr(graph_module, "make_gdp_graph", fake_make_gdp_graph)

    config = {
        "context": {
            "thread_id": "thread-runtime",
            "run_id": "run-runtime",
            "user_id": "user-runtime",
            "model_name": "gdp-model",
        }
    }
    app_config = SimpleNamespace(log_level="info", memory=SimpleNamespace(enabled=False), checkpointer=None)

    result = graph_module.make_gdp_agent(config, app_config)

    assert result == "graph"
    assert config["metadata"]["observed"] is True
    assert calls["graph_services"] is services
    assert calls["services_runtime"] is calls["observability_runtime"]
    assert calls["graph_runtime"] is calls["observability_runtime"]
    assert calls["graph_metadata"] is calls["observability_metadata"]
