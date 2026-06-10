"""GDP Agent 运行时上下文中间件工具。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig


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
