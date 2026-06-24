"""GDP Agent Runtime 测试用假 Catalog。

第二阶段后，显式 scene_code 路径也走契约解析（catalog.get_contract），
搜索路径走 catalog.search。测试不连真实持久化，统一用这里的假实现注入。

设计目标：
- 让第一阶段回归用例（显式 scene_code）行为不变：create_paid_order 必填 buyer_id，
  其它场景无必填入参、无副作用，可直接执行。
- 为第二阶段搜索用例提供可配置候选。
"""

from __future__ import annotations

from typing import Any

from app.gdp.agent_runtime.models import InfraCandidate, SceneCandidate, SourceCandidate

# 与第一阶段 _REQUIRED_INPUTS_BY_SCENE 等价的契约缺参定义，保证回归行为不变。
_REQUIRED_INPUTS_BY_SCENE: dict[str, tuple[str, ...]] = {
    "create_paid_order": ("buyer_id",),
}
_SIDE_EFFECT_SCENES: set[str] = set()


def _missing_for(scene_code: str, user_inputs: dict[str, Any]) -> list[str]:
    required = _REQUIRED_INPUTS_BY_SCENE.get(scene_code, ())
    provided = {str(k).lower() for k in user_inputs}
    return [name for name in required if name.lower() not in provided]


class FakeSceneCatalog:
    """SceneCatalogPort 的测试实现。

    - get_contract：按显式 scene_code 合成单候选，缺参/副作用按上面的表判定。
    - search：返回预置候选列表（默认空，即零候选）。
    """

    def __init__(
        self,
        *,
        candidates: list[SceneCandidate] | None = None,
        source_candidates: list[SourceCandidate] | None = None,
        infra_candidates: list[InfraCandidate] | None = None,
        query_terms: list[str] | None = None,
        source_query_terms: list[str] | None = None,
        contract_missing: bool = False,
    ) -> None:
        self._candidates = candidates or []
        self._source_candidates = source_candidates or []
        self._infra_candidates = infra_candidates or []
        self._query_terms = query_terms or ["订单"]
        self._source_query_terms = source_query_terms or ["订单", "source"]
        self._contract_missing = contract_missing

    async def search(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[SceneCandidate], list[str]]:
        return list(self._candidates), list(self._query_terms)

    async def get_contract(
        self,
        *,
        scene_code: str,
        user_inputs: dict[str, Any],
    ) -> SceneCandidate:
        from fastapi import HTTPException

        if self._contract_missing:
            raise HTTPException(status_code=404, detail=f"scene {scene_code} not found")
        return SceneCandidate(
            scene_code=scene_code,
            scene_name=scene_code,
            score=1.0,
            reasons=["显式指定 scene_code，按契约解析"],
            missing_inputs=_missing_for(scene_code, user_inputs),
            requires_confirmation=scene_code in _SIDE_EFFECT_SCENES,
            # 与 make_candidate 同源：真实 catalog 保证「同场景→同契约哈希」，
            # search 与 get_contract 必须对同一 scene_code 产出一致哈希，否则执行前重验会误报漂移。
            contract_hash=f"hash-{scene_code}",
        )

    async def search_sources(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[SourceCandidate], list[str]]:
        return list(self._source_candidates), list(self._source_query_terms)

    async def resolve_infra(
        self,
        *,
        query: str,
        env_code: str | None,
        sys_code: str | None,
        datasource_code: str | None,
        resource_type: str,
    ) -> InfraCandidate:
        if self._infra_candidates:
            return self._infra_candidates.pop(0)
        return make_infra_candidate(resource_type=resource_type)


def make_candidate(
    scene_code: str,
    *,
    scene_name: str | None = None,
    score: float = 0.9,
    missing_inputs: list[str] | None = None,
    requires_confirmation: bool = False,
) -> SceneCandidate:
    """构造一个搜索候选，供搜索路径用例使用。"""
    return SceneCandidate(
        scene_code=scene_code,
        scene_name=scene_name or scene_code,
        score=score,
        reasons=[f"命中 {scene_code}"],
        missing_inputs=missing_inputs or [],
        requires_confirmation=requires_confirmation,
        contract_hash=f"hash-{scene_code}",
    )


def make_source_candidate(
    source_code: str,
    *,
    source_type: str = "HTTP",
    source_name: str | None = None,
    score: float = 0.85,
    missing_inputs: list[str] | None = None,
    requires_confirmation: bool = True,
    sys_code: str | None = "TRADE",
    method: str | None = "POST",
    path: str | None = "/api/orders",
    datasource_code: str | None = None,
    operation: str | None = None,
) -> SourceCandidate:
    """构造 Source 发现候选。"""
    return SourceCandidate(
        source_type=source_type,
        source_code=source_code,
        source_name=source_name or source_code,
        score=score,
        reasons=[f"命中 Source {source_code}"],
        missing_inputs=missing_inputs or [],
        requires_confirmation=requires_confirmation,
        sys_code=sys_code,
        method=method if source_type == "HTTP" else None,
        path=path if source_type == "HTTP" else None,
        datasource_code=datasource_code if source_type == "SQL" else None,
        operation=operation if source_type == "SQL" else None,
        contract_hash=f"hash-source-{source_code}",
    )


def make_infra_candidate(
    *,
    resource_type: str = "HTTP",
    ready: bool = True,
    missing_fields: list[str] | None = None,
) -> InfraCandidate:
    """构造 Infra 只读诊断结果。"""
    return InfraCandidate(
        resource_type=resource_type,
        ready=ready,
        confidence=0.9 if ready else 0.4,
        missing_fields=missing_fields or [],
        matched_systems=[{"sysCode": "TRADE", "sysName": "交易系统"}],
        matched_environments=[{"envCode": "SIT1", "envName": "测试环境"}],
        matched_service_endpoints=[{"envCode": "SIT1", "sysCode": "TRADE", "baseUrl": "http://trade.example"}],
        matched_datasources=[],
    )
