"""GDP Agent 运行时上下文中间件工具。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import fields, is_dataclass
from inspect import signature
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.state import GDPState

GDPNodeCallable = Callable[..., Awaitable[GDPState]]


def wrap_gdp_runtime_context(
    *,
    node: GDPNodeCallable,
    metadata: Any | None = None,
    enabled: bool,
) -> GDPNodeCallable:
    """在节点出口注入本次运行上下文，避免运行时标识只停留在入口节点。"""

    accepts_config = len(signature(node).parameters) >= 2

    async def runtime_context_node(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        result = await node(state, config) if accepts_config else await node(state)
        if not enabled or not isinstance(result, dict):
            return result
        runtime_context = build_gdp_runtime_context(config, metadata)
        if not runtime_context:
            return result
        return {
            **result,
            "runtime_context": {**dict(result.get("runtime_context") or {}), **runtime_context},
        }

    return runtime_context_node


def build_gdp_runtime_context(config: RunnableConfig | None, metadata: Any | None = None) -> dict[str, Any]:
    """从 RunnableConfig 和图装配元数据生成 checkpoint 里的轻量运行上下文。"""

    context: dict[str, Any] = {}
    for key in ("assistant_id", "thread_id", "run_id", "user_id", "operator", "model_name"):
        value = _metadata_value(metadata, key)
        if value is not None:
            context[key] = str(value)
    for container_name in ("context", "configurable", "metadata"):
        container = (config or {}).get(container_name) if config else None
        if not isinstance(container, dict):
            continue
        for key in ("assistant_id", "thread_id", "run_id", "user_id", "operator", "model_name"):
            if container.get(key) is not None:
                context[key] = str(container[key])
    context.setdefault("assistant_id", "gdp_agent")
    return context


def runtime_binding(config: RunnableConfig | None) -> dict[str, str | None]:
    """从 RunnableConfig 提取 DeerFlow thread/run/checkpoint 标识。"""

    result = {"thread_id": None, "run_id": None, "checkpoint_id": None}
    if not config:
        return result
    for container_name in ("context", "configurable", "metadata"):
        container = config.get(container_name)
        if not isinstance(container, dict):
            continue
        for key in result:
            if result[key] is None and container.get(key) is not None:
                result[key] = str(container[key])
    return result


def metadata_payload(metadata: Any | None) -> dict[str, Any]:
    """把图装配元数据转成审计事件可落库的 JSON payload。"""

    if metadata is None:
        return {}
    if is_dataclass(metadata):
        return {"runtime": {field.name: getattr(metadata, field.name) for field in fields(metadata)}}
    if isinstance(metadata, dict):
        return {"runtime": metadata}
    return {"runtime": {"value": str(metadata)}}


def _metadata_value(metadata: Any | None, key: str) -> Any:
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get(key)
    return getattr(metadata, key, None)
