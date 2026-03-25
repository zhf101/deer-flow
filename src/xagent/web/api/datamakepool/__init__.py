from typing import Any


def __getattr__(name: str) -> Any:
    """按需导出各 datamakepool 路由。

    这里避免包初始化阶段一次性导入所有 router，减少测试场景下的可选依赖
    和循环引用放大效应。真正访问某个 router 时，再加载对应模块。
    """

    module_map = {
        "assets_router": ".assets",
        "audits_router": ".audits",
        "conversations_router": ".conversations",
        "flowdrafts_router": ".flowdrafts",
        "runs_router": ".runs",
        "templates_router": ".templates",
    }
    module_name = module_map.get(name)
    if module_name is None:
        raise AttributeError(f"module 'xagent.web.api.datamakepool' has no attribute {name!r}")

    from importlib import import_module

    module = import_module(module_name, __name__)
    return getattr(module, "router")


__all__ = [
    "assets_router",
    "audits_router",
    "conversations_router",
    "flowdrafts_router",
    "runs_router",
    "templates_router",
]
