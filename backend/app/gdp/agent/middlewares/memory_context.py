"""GDP Agent 记忆上下文中间件工具。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.agent_memory.models import GDPAgentMemoryContext
from app.gdp.datagen.agent_memory.service import GDPAgentMemoryService


async def load_gdp_memory_context(
    memory_service: GDPAgentMemoryService | None,
    *,
    user_id: str | None,
    user_intent: str,
    env_code: str | None,
    phase: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """加载只读 GDP 记忆上下文，失败时返回禁用态摘要。"""

    if memory_service is None:
        return _disabled_context(user_id=user_id, env_code=env_code, phase=phase), []
    try:
        context, trace = await memory_service.build_context(
            user_id=user_id,
            user_intent=user_intent,
            env_code=env_code,
            phase=phase,
        )
    except Exception as exc:
        return (
            {
                **_disabled_context(user_id=user_id, env_code=env_code, phase=phase),
                "error": str(exc),
            },
            [],
        )
    return (
        context.model_dump(mode="json"),
        [item.model_dump(mode="json") for item in trace],
    )


def _disabled_context(*, user_id: str | None, env_code: str | None, phase: str | None) -> dict[str, Any]:
    return GDPAgentMemoryContext(
        enabled=False,
        userId=user_id,
        envCode=env_code,
        phase=phase,
        facts=[],
        categories={},
    ).model_dump(mode="json")
