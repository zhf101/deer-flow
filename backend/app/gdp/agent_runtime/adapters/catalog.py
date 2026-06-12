"""GDP Agent Runtime Catalog 适配器。

包一层 datagen 的 AgentCatalogService，把 AgentSceneCandidate / AgentSceneContract
转成 runtime 内部的 SceneCandidate。第二阶段红线：不在 runtime 内复刻分词 / 同义词 /
打分逻辑，全部复用 Catalog；只做必要的归一化（score clamp）和契约快照哈希。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from fastapi import HTTPException

from app.gdp.datagen.agent_catalog.models import AgentSceneCandidate, AgentSceneContract
from app.gdp.datagen.agent_catalog.service import _missing_required_inputs

from ..models import SceneCandidate


class SceneCatalogPort(Protocol):
    """Catalog 检索端口。runtime 只依赖该协议，便于测试注入假实现。"""

    async def search(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[SceneCandidate], list[str]]:
        """搜索候选 Scene，返回 (候选列表, 检索词)。"""
        ...

    async def get_contract(
        self,
        *,
        scene_code: str,
        user_inputs: dict[str, Any],
    ) -> SceneCandidate:
        """按显式 scene_code 取契约快照，合成单候选。"""
        ...


def _contract_hash(contract: AgentSceneContract) -> str:
    """对契约快照做稳定哈希，Phase 5 检测契约漂移用。"""
    raw = json.dumps(contract.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _clamp_score(score: float) -> float:
    """把 Catalog 评分归一到 [0, 1]。

    runtime SceneCandidate.score 约束 ge=0.0/le=1.0，而 Catalog _score_contract 返回的是
    累加分，区间未必落在 [0,1]。这里 clamp，避免撞 Pydantic 校验直接抛错。
    """
    return max(0.0, min(1.0, float(score)))


def _to_candidate(candidate: AgentSceneCandidate) -> SceneCandidate:
    """AgentSceneCandidate -> runtime SceneCandidate。"""
    contract = candidate.contract
    return SceneCandidate(
        scene_code=contract.sceneCode,
        scene_name=contract.sceneName,
        score=_clamp_score(candidate.score),
        reasons=list(candidate.reasons),
        missing_inputs=list(candidate.missingInputs),
        requires_confirmation=candidate.requiresConfirmation,
        contract_hash=_contract_hash(contract),
    )


def _provided_keys(user_inputs: dict[str, Any]) -> set[str]:
    """从用户入参推导已提供键集，用于显式契约缺参判定。

    与 Catalog _provided_keys 同源（小写归一），但显式路径只有 user_inputs，没有变量栈。
    """
    return {str(key).lower() for key in user_inputs}


def _explicit_candidate(contract: AgentSceneContract, user_inputs: dict[str, Any]) -> SceneCandidate:
    """显式 scene_code 合成单候选：score=1.0（非检索来源），缺参用同一套契约逻辑判定。"""
    missing_inputs = _missing_required_inputs(contract.inputSchema, _provided_keys(user_inputs))
    return SceneCandidate(
        scene_code=contract.sceneCode,
        scene_name=contract.sceneName,
        score=1.0,
        reasons=["显式指定 scene_code，按契约解析"],
        missing_inputs=missing_inputs,
        requires_confirmation=contract.hasSideEffects,
        contract_hash=_contract_hash(contract),
    )


class AgentCatalogAdapter:
    """SceneCatalogPort 的默认实现，委托给 datagen AgentCatalogService。"""

    def __init__(self, service: Any | None = None) -> None:
        self._service = service

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        from app.gdp.datagen.agent_catalog.service import AgentCatalogService
        from app.gdp.datagen.config.scene.repository import SceneRepository
        from deerflow.persistence.engine import get_session_factory

        session_factory = get_session_factory()
        if session_factory is None:
            raise HTTPException(status_code=503, detail="Catalog persistence not available")
        self._service = AgentCatalogService(scene_repository=SceneRepository(session_factory))
        return self._service

    async def search(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[SceneCandidate], list[str]]:
        from app.gdp.datagen.agent_catalog.models import AgentSceneSearchRequest

        response = await self._get_service().search_scene_contracts(
            AgentSceneSearchRequest(
                goal=goal,
                envCode=env_code,
                userInputs=user_inputs,
                visibleVariables=visible_variables,
                limit=limit,
            )
        )
        candidates = [_to_candidate(item) for item in response.candidates]
        return candidates, list(response.queryTerms)

    async def get_contract(
        self,
        *,
        scene_code: str,
        user_inputs: dict[str, Any],
    ) -> SceneCandidate:
        # scene_code 不存在 / 未发布 -> AgentCatalogService.get_scene_contract 抛 HTTPException(404)。
        contract = await self._get_service().get_scene_contract(scene_code)
        return _explicit_candidate(contract, user_inputs)
