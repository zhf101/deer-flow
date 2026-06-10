"""GDP Agent LangGraph 观测配置。"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from langchain_core.runnables import RunnableConfig

from deerflow.config import get_explicitly_enabled_tracing_providers
from deerflow.tracing import build_tracing_callbacks

_AGENT_KIND = "gdp_datagen"
_DEFAULT_ASSISTANT_ID = "gdp_agent"
_DEFAULT_RUN_NAME = "gdp_agent"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}
_LANGSMITH_HIDE_ENV_VARS = ("LANGSMITH_HIDE_INPUTS", "LANGSMITH_HIDE_OUTPUTS")


def configure_gdp_observability(
    config: RunnableConfig,
    *,
    runtime: Any,
    metadata: Any,
) -> None:
    """把 GDP 运行身份挂到 LangGraph 根配置，供 LangSmith/Langfuse 继承。"""

    _assert_full_langsmith_payload_enabled()
    config.setdefault("run_name", _DEFAULT_RUN_NAME)
    _merge_trace_metadata(config, runtime=runtime, metadata=metadata)
    _merge_trace_tags(config, runtime=runtime)
    _merge_tracing_callbacks(config)


def build_gdp_trace_metadata(*, runtime: Any, metadata: Any) -> dict[str, Any]:
    """生成只包含运行身份和策略开关的追踪元数据。"""

    result: dict[str, Any] = {
        "agent_name": _DEFAULT_ASSISTANT_ID,
        "agent_kind": _AGENT_KIND,
        "gdp_trace_payload_mode": "full",
        "assistant_id": _attr(runtime, "assistant_id") or _DEFAULT_ASSISTANT_ID,
        "thread_id": _attr(runtime, "thread_id"),
        "run_id": _attr(runtime, "run_id"),
        "user_id": _attr(runtime, "user_id"),
        "operator": _attr(runtime, "operator"),
        "model_name": _attr(runtime, "model_name"),
        "gdp_log_level": _attr(metadata, "log_level"),
        "gdp_policy": _attr(metadata, "policy"),
    }
    return {key: value for key, value in result.items() if value is not None}


def build_gdp_trace_tags(*, runtime: Any) -> list[str]:
    """生成便于在 LangSmith UI 中过滤 GDP 运行的标签。"""

    tags = [
        "gdp-datagen-agent",
        _optional_tag("assistant", _attr(runtime, "assistant_id") or _DEFAULT_ASSISTANT_ID),
        _optional_tag("model", _attr(runtime, "model_name")),
        _optional_tag("env", _current_environment()),
    ]
    return [tag for tag in tags if tag]


def _merge_trace_metadata(config: RunnableConfig, *, runtime: Any, metadata: Any) -> None:
    existing = dict(config.get("metadata") or {})
    for key, value in build_gdp_trace_metadata(runtime=runtime, metadata=metadata).items():
        existing.setdefault(key, value)
    config["metadata"] = existing


def _merge_trace_tags(config: RunnableConfig, *, runtime: Any) -> None:
    existing = _as_list(config.get("tags"))
    merged = _append_unique(existing, build_gdp_trace_tags(runtime=runtime))
    if merged:
        config["tags"] = merged


def _merge_tracing_callbacks(config: RunnableConfig) -> None:
    tracing_callbacks = build_tracing_callbacks()
    if not tracing_callbacks:
        return
    existing = _as_list(config.get("callbacks"))
    config["callbacks"] = [*existing, *tracing_callbacks]


def _assert_full_langsmith_payload_enabled() -> None:
    """确保 LangSmith 没有通过环境变量隐藏 trace 输入输出。"""

    if "langsmith" not in get_explicitly_enabled_tracing_providers():
        return
    hidden_names = [name for name in _LANGSMITH_HIDE_ENV_VARS if _env_flag(name)]
    if hidden_names:
        raise RuntimeError(
            "GDP Agent 要求 LangSmith 记录完整模型请求和响应，"
            f"请关闭这些隐藏输入输出的环境变量：{', '.join(hidden_names)}。"
        )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, Iterable) and not isinstance(value, str | bytes | dict):
        return list(value)
    return [value]


def _append_unique(existing: list[Any], additions: list[str]) -> list[Any]:
    merged = list(existing)
    seen = {item for item in existing if isinstance(item, str)}
    for item in additions:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _optional_tag(prefix: str, value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return f"{prefix}:{normalized}"


def _current_environment() -> str | None:
    return os.environ.get("DEER_FLOW_ENV") or os.environ.get("ENVIRONMENT")


def _env_flag(name: str) -> bool:
    value = os.environ.get(name)
    return bool(value and value.strip().lower() in _TRUTHY_VALUES)


def _attr(value: Any, name: str) -> Any:
    return getattr(value, name, None)
