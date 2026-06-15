"""造数运行时的身份与追踪上下文——让每个执行节点都知道"谁在造数、在哪造的"。

业务目标：在 LangGraph 编排流水线的每个节点间传递运行上下文（用户 ID、线程 ID、
运行 ID 等），确保审计事件和 checkpoint 中始终包含可追溯的身份标识。

当前动作：提供三个工具函数——
- wrap_gdp_runtime_context：在节点出口注入上下文，防止追踪信息在流转中丢失
- build_gdp_runtime_context：从 RunnableConfig 和元数据中提取身份标识
- runtime_binding：提取 thread/run/checkpoint 三元组，用于关联外部系统

预期结果：造数任务的每个执行步骤都能追溯到发起用户和所属线程，
支撑审计追踪、权限校验和问题排查。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import fields, is_dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

RuntimeState = dict[str, Any]
RuntimeNodeCallable = Callable[..., Awaitable[RuntimeState]]


def wrap_gdp_runtime_context(
    *,
    node: RuntimeNodeCallable,
    metadata: Any | None = None,
) -> RuntimeNodeCallable:
    """在编排节点出口注入运行上下文，确保追踪信息不在节点流转中丢失。

    业务目标：让造数任务的每个执行节点都能携带完整的身份标识，
    使审计事件和 checkpoint 始终可追溯到发起用户和所属线程。
    当前动作：包装原始节点函数，在其执行完成后将运行上下文合并到输出状态中。
    预期结果：下游节点和 checkpoint 持久化层都能看到完整的 runtime_context。
    """

    async def runtime_context_node(state: RuntimeState, config: RunnableConfig | None = None) -> RuntimeState:
        result = await node(state, config)
        if not isinstance(result, dict):
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
    """从 LangGraph 配置和装配元数据中提取造数任务的身份标识。

    业务目标：构建一个轻量级的运行上下文字典，供审计事件和 checkpoint 使用。
    当前动作：依次从元数据对象和 RunnableConfig 的 configurable/metadata/context
    三个容器中提取 assistant_id、thread_id、run_id、user_id、operator、model_name。
    预期结果：返回包含可用身份标识的字典，确保后续审计日志能关联到具体用户和执行环境。
    """

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
    """从 LangGraph 配置中提取造数任务与外部系统的关联标识。

    业务目标：提供 thread_id、run_id、checkpoint_id 三元组，
    用于将造数任务与对话系统、执行平台等外部系统进行关联。
    当前动作：遍历 RunnableConfig 中的 configurable/metadata/context 容器，
    提取可用的关联标识。
    预期结果：返回标识字典，供外部系统查询和跨系统追踪使用。
    """

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
    """将装配元数据转为审计事件可落库的 JSON 载荷。

    业务目标：让运维人员能通过审计日志了解每次造数任务是由哪个组件版本、
    什么配置参数驱动的，支撑问题回溯和配置对比。
    当前动作：将 dataclass、dict 或标量元数据统一转为 {"runtime": ...} 结构的字典。
    预期结果：返回的字典可直接序列化为审计事件的 payload 字段。
    """

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
