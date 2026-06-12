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

from app.gdp.agent_runtime.models import SceneCandidate

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
        query_terms: list[str] | None = None,
        contract_missing: bool = False,
    ) -> None:
        self._candidates = candidates or []
        self._query_terms = query_terms or ["订单"]
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
            contract_hash="fake-hash",
        )


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
