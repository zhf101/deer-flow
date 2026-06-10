"""GDP Agent 运行时上下文中间件测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gdp.agent.middlewares.runtime_context import build_gdp_runtime_context, wrap_gdp_runtime_context
from app.gdp.datagen.config.task.models import DatagenTaskPhase


async def _plain_node(state, config):
    return {
        "task_run_id": state["task_run_id"],
        "current_phase": DatagenTaskPhase.SCENE_DESIGN.value,
        "runtime_context": {"source": "node"},
    }


def test_build_gdp_runtime_context_prefers_current_config_over_metadata():
    metadata = SimpleNamespace(
        assistant_id="gdp_agent",
        thread_id="thread-from-metadata",
        run_id="run-from-metadata",
        user_id="user-from-metadata",
        model_name="model-from-metadata",
    )

    context = build_gdp_runtime_context(
        {
            "context": {"thread_id": "thread-from-context", "operator": "operator-from-context"},
            "configurable": {"run_id": "run-from-configurable"},
            "metadata": {"model_name": "model-from-run-metadata"},
        },
        metadata,
    )

    assert context == {
        "assistant_id": "gdp_agent",
        "thread_id": "thread-from-context",
        "run_id": "run-from-configurable",
        "user_id": "user-from-metadata",
        "operator": "operator-from-context",
        "model_name": "model-from-run-metadata",
    }


@pytest.mark.anyio
async def test_runtime_context_wrapper_injects_context_without_dropping_node_result():
    node = wrap_gdp_runtime_context(
        node=_plain_node,
        metadata=SimpleNamespace(assistant_id="gdp_agent", user_id="user-meta"),
        enabled=True,
    )

    result = await node(
        {"task_run_id": "task_runtime_1"},
        {"configurable": {"thread_id": "thread-1", "run_id": "run-1"}},
    )

    assert result["current_phase"] == "SCENE_DESIGN"
    assert result["runtime_context"] == {
        "source": "node",
        "assistant_id": "gdp_agent",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-meta",
    }
