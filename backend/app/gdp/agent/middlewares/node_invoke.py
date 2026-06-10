"""GDP Agent 中间件公共节点调用工具。

所有 GDP 节点 wrapper 都通过本模块判断被包装节点是否接收 ``config``
参数并发起调用，避免每个中间件各自复制 ``inspect.signature`` 反射逻辑。
检测按参数名（``config``）而非参数个数进行，对签名变化更稳健。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from inspect import signature

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.state import GDPState

GDPNodeCallable = Callable[..., Awaitable[GDPState]]
GDPNodeInvoker = Callable[[GDPState, RunnableConfig | None], Awaitable[GDPState]]


def gdp_node_accepts_config(node: GDPNodeCallable) -> bool:
    """判断节点是否声明了 ``config`` 参数。"""

    return "config" in signature(node).parameters


def make_gdp_node_invoker(node: GDPNodeCallable) -> GDPNodeInvoker:
    """生成统一的节点调用器：包装时解析一次签名，调用时不再反射。"""

    if gdp_node_accepts_config(node):

        async def invoke(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
            return await node(state, config)

    else:

        async def invoke(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
            return await node(state)

    return invoke
