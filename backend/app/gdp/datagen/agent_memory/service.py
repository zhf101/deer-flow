"""GDP Agent 记忆业务服务层。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.gdp.datagen.agent_memory.models import (
    GDPAgentMemoryCategory,
    GDPAgentMemoryContext,
    GDPAgentMemoryContextFact,
    GDPAgentMemoryFactCreateRequest,
    GDPAgentMemoryFactIdRequest,
    GDPAgentMemoryFactResponse,
    GDPAgentMemoryFactUpdateRequest,
    GDPAgentMemoryReloadResponse,
    GDPAgentMemoryScopeType,
    GDPAgentMemoryStatus,
    GDPAgentMemoryTraceItem,
)
from app.gdp.datagen.agent_memory.repository import (
    GDPAgentMemoryConflictError,
    GDPAgentMemoryNotFoundError,
    GDPAgentMemoryRepository,
)

T = TypeVar("T")


class GDPAgentMemoryService:
    """GDP Agent 记忆服务。"""

    def __init__(self, repository: GDPAgentMemoryRepository) -> None:
        self._repo = repository

    async def create_fact(self, request: GDPAgentMemoryFactCreateRequest) -> GDPAgentMemoryFactResponse:
        return await self._guard(lambda: self._repo.create_fact(request))

    async def list_facts(
        self,
        *,
        user_id: str | None = None,
        agent_name: str | None = "gdp_agent",
        category: GDPAgentMemoryCategory | None = None,
        scope_type: GDPAgentMemoryScopeType | None = None,
        scope_key: str | None = None,
        status: GDPAgentMemoryStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GDPAgentMemoryFactResponse]:
        return await self._guard(
            lambda: self._repo.list_facts(
                user_id=user_id,
                agent_name=agent_name,
                category=category,
                scope_type=scope_type,
                scope_key=scope_key,
                status=status,
                limit=limit,
                offset=offset,
            )
        )

    async def update_fact(self, request: GDPAgentMemoryFactUpdateRequest) -> GDPAgentMemoryFactResponse:
        return await self._guard(lambda: self._repo.update_fact(request))

    async def disable_fact(self, request: GDPAgentMemoryFactIdRequest) -> GDPAgentMemoryFactResponse:
        return await self.update_fact(
            GDPAgentMemoryFactUpdateRequest(
                factId=request.factId,
                status=GDPAgentMemoryStatus.DISABLED,
            )
        )

    async def delete_fact(self, request: GDPAgentMemoryFactIdRequest) -> GDPAgentMemoryReloadResponse:
        await self._guard(lambda: self._repo.delete_fact(request.factId))
        return GDPAgentMemoryReloadResponse(reloaded=True, message="记忆事实已删除。")

    async def reload(self) -> GDPAgentMemoryReloadResponse:
        return GDPAgentMemoryReloadResponse(reloaded=True, message="GDP Agent 记忆当前为数据库实时读取，无需额外重载。")

    async def build_context(
        self,
        *,
        user_id: str | None,
        user_intent: str,
        env_code: str | None,
        phase: str | None,
        agent_name: str = "gdp_agent",
        limit: int = 8,
    ) -> tuple[GDPAgentMemoryContext, list[GDPAgentMemoryTraceItem]]:
        """检索只读记忆上下文，不改变任务事实。"""

        candidates = await self._collect_context_candidates(
            user_id=user_id,
            env_code=env_code,
            agent_name=agent_name,
            limit=limit * 3,
        )
        ranked = _rank_facts(candidates, user_intent=user_intent, env_code=env_code)[:limit]
        context_facts = [_context_fact(item) for item in ranked]
        categories: dict[str, list[GDPAgentMemoryContextFact]] = defaultdict(list)
        for fact in context_facts:
            categories[fact.category.value].append(fact)
        trace = [
            GDPAgentMemoryTraceItem(
                factId=fact.factId,
                category=fact.category,
                memoryKey=fact.memoryKey,
                reason="命中用户、环境或 Agent 作用域的高置信记忆。",
            )
            for fact in context_facts
        ]
        await self._repo.mark_used([fact.factId for fact in context_facts])
        return (
            GDPAgentMemoryContext(
                enabled=True,
                userId=user_id,
                envCode=env_code,
                phase=phase,
                facts=context_facts,
                categories=dict(categories),
            ),
            trace,
        )

    async def _collect_context_candidates(
        self,
        *,
        user_id: str | None,
        env_code: str | None,
        agent_name: str,
        limit: int,
    ) -> list[GDPAgentMemoryFactResponse]:
        facts: list[GDPAgentMemoryFactResponse] = []
        if user_id:
            facts.extend(
                await self._repo.list_facts(
                    user_id=user_id,
                    agent_name=agent_name,
                    active_only=True,
                    limit=limit,
                )
            )
        facts.extend(
            await self._repo.list_facts(
                user_id=None,
                agent_name=agent_name,
                scope_type=GDPAgentMemoryScopeType.AGENT,
                scope_key=agent_name,
                active_only=True,
                limit=limit,
            )
        )
        if env_code:
            facts.extend(
                await self._repo.list_facts(
                    user_id=None,
                    agent_name=agent_name,
                    scope_type=GDPAgentMemoryScopeType.ENV,
                    scope_key=env_code,
                    active_only=True,
                    limit=limit,
                )
            )
        return _dedupe_facts(facts)

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except GDPAgentMemoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GDPAgentMemoryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def _context_fact(fact: GDPAgentMemoryFactResponse) -> GDPAgentMemoryContextFact:
    return GDPAgentMemoryContextFact(
        factId=fact.factId,
        category=fact.category,
        memoryKey=fact.memoryKey,
        scopeType=fact.scopeType,
        scopeKey=fact.scopeKey,
        value=fact.value,
        confidence=fact.confidence,
        evidenceSummary=fact.evidenceSummary,
    )


def _rank_facts(
    facts: list[GDPAgentMemoryFactResponse],
    *,
    user_intent: str,
    env_code: str | None,
) -> list[GDPAgentMemoryFactResponse]:
    intent = user_intent.lower()

    def score(fact: GDPAgentMemoryFactResponse) -> tuple[float, int, float]:
        text = " ".join([fact.memoryKey, fact.evidenceSummary or "", str(fact.value)]).lower()
        keyword_hit = 1 if any(part and part in text for part in intent.split()) else 0
        env_hit = 1 if env_code and (fact.scopeKey == env_code or env_code.lower() in text) else 0
        return (float(fact.confidence), keyword_hit + env_hit, float(fact.useCount))

    return sorted(facts, key=score, reverse=True)


def _dedupe_facts(facts: list[GDPAgentMemoryFactResponse]) -> list[GDPAgentMemoryFactResponse]:
    result: list[GDPAgentMemoryFactResponse] = []
    seen: set[str] = set()
    for fact in facts:
        if fact.factId in seen:
            continue
        seen.add(fact.factId)
        result.append(fact)
    return result
