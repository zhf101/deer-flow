"""GDP Agent 模型工厂。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from deerflow.config.app_config import AppConfig
from deerflow.models import create_chat_model


def create_gdp_chat_model(
    config: RunnableConfig | None = None,
    *,
    app_config: AppConfig | None = None,
):
    """创建 GDP 图内使用的聊天模型，并继承图根追踪配置。"""

    model_name = resolve_gdp_model_name(config)
    return create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=app_config,
        attach_tracing=False,
    )


def resolve_gdp_model_name(config: RunnableConfig | None = None) -> str | None:
    """从运行配置中解析 GDP 本次调用要使用的模型名。"""

    for container_name in ("context", "configurable", "metadata"):
        container = (config or {}).get(container_name)
        if not isinstance(container, dict):
            continue
        for key in ("gdp_model_name", "model_name", "model"):
            value = container.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def build_gdp_llm_config(
    parent_config: RunnableConfig | None,
    *,
    run_name: str,
    node_name: str,
    decision_name: str,
    metadata: dict[str, Any] | None = None,
) -> RunnableConfig:
    """为单次 GDP 模型决策派生子运行配置。"""

    child_config: RunnableConfig = dict(parent_config or {})
    child_config["run_name"] = run_name
    child_config["tags"] = _append_unique(
        _as_list(child_config.get("tags")),
        [
            "gdp-datagen-agent",
            f"node:gdp.{node_name}",
            f"decision:{decision_name}",
        ],
    )
    child_metadata = dict(child_config.get("metadata") or {})
    child_metadata.update(
        {
            "gdp_node": node_name,
            "gdp_decision": decision_name,
        }
    )
    if metadata:
        child_metadata.update(metadata)
    child_config["metadata"] = child_metadata
    return child_config


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _append_unique(existing: list[Any], additions: list[str]) -> list[Any]:
    result = list(existing)
    seen = {item for item in result if isinstance(item, str)}
    for item in additions:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result
