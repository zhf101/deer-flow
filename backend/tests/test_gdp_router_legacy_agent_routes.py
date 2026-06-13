"""GDP 聚合路由旧 Agent 入口拆除回归测试。"""

from __future__ import annotations

from fastapi import FastAPI

from app.gdp.router import router


def test_gdp_router_no_longer_mounts_legacy_agent_entries():
    """聚合路由不再暴露旧 Agent API、技能和 MCP 入口。"""

    app = FastAPI()
    app.include_router(router)
    paths = {
        str(route.path)
        for route in app.routes
        if hasattr(route, "path")
    }

    legacy_prefixes = (
        "/api/v1/datagen/agent/scenes",
        "/api/v1/datagen/agent/sources",
        "/api/v1/datagen/agent/infra",
        "/api/v1/datagen/agent-skills",
        "/api/v1/datagen/agent-mcp",
    )
    legacy_paths = sorted(
        path
        for path in paths
        if any(path.startswith(prefix) for prefix in legacy_prefixes)
    )

    assert legacy_paths == []
    assert any(path.startswith("/api/v1/datagen/agent-runtime") for path in paths)
    assert any(path.startswith("/api/v1/datagen/agent/catalog") for path in paths)
    assert any(path.startswith("/api/v1/datagen/agent-memory") for path in paths)
