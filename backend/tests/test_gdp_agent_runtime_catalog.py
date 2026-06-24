"""GDP Agent Runtime Catalog 适配器与搜索编排专项测试。"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from app.gdp.agent_runtime.adapters.catalog import (
    AgentCatalogAdapter,
    _clamp_score,
    _explicit_candidate,
    _missing_required_inputs,
)
from app.gdp.agent_runtime.catalog import (
    create_scene_requirement,
    resolve_explicit_scene,
    search_scenes,
)
from app.gdp.agent_runtime.flow import create_single_step, create_task_run
from app.gdp.agent_runtime.models import RequirementStatus, SceneCandidate
from app.gdp.datagen.agent_catalog.models import (
    AgentSceneCandidate,
    AgentSceneContract,
    AgentSceneSearchResponse,
)
from app.gdp.datagen.config.common.models import (
    CapabilityType,
    InputFieldDefinition,
    InputFieldType,
)


def _make_contract(
    scene_code: str = "create_paid_order",
    scene_name: str = "造一笔已支付订单",
    *,
    required_inputs: list[str] | None = None,
    has_side_effects: bool = False,
) -> AgentSceneContract:
    input_schema = [
        InputFieldDefinition(name=name, label=name, type=InputFieldType.STRING, required=True)
        for name in (required_inputs or [])
    ]
    return AgentSceneContract(
        sceneCode=scene_code,
        sceneName=scene_name,
        capabilityType=CapabilityType.CREATE,
        inputSchema=input_schema,
        versionNo=1,
        executable=True,
        hasSideEffects=has_side_effects,
    )


class _FakeService:
    """假 AgentCatalogService，返回预置候选/契约，不碰真实持久化。"""

    def __init__(
        self,
        *,
        candidates: list[AgentSceneCandidate] | None = None,
        query_terms: list[str] | None = None,
        contract: AgentSceneContract | None = None,
        contract_missing: bool = False,
    ) -> None:
        self._candidates = candidates or []
        self._query_terms = query_terms or []
        self._contract = contract
        self._contract_missing = contract_missing

    async def search_scene_contracts(self, request: Any) -> AgentSceneSearchResponse:
        return AgentSceneSearchResponse(candidates=self._candidates, queryTerms=self._query_terms)

    async def get_scene_contract(self, scene_code: str) -> AgentSceneContract:
        if self._contract_missing or self._contract is None:
            raise HTTPException(status_code=404, detail=f"scene {scene_code} not found")
        return self._contract


def test_clamp_score_keeps_in_unit_range():
    """超界累加分 clamp 到 [0,1]，不抛 Pydantic 校验错。"""
    assert _clamp_score(3.7) == 1.0
    assert _clamp_score(-0.5) == 0.0
    assert _clamp_score(0.6) == 0.6


def test_explicit_candidate_uses_contract_missing_inputs():
    """显式契约缺参用同一套契约逻辑判定，score=1.0。"""
    contract = _make_contract(required_inputs=["buyer_id"], has_side_effects=True)
    candidate = _explicit_candidate(contract, user_inputs={})
    assert candidate.score == 1.0
    assert candidate.missing_inputs == ["buyer_id"]
    assert candidate.requires_confirmation is True

    candidate_ok = _explicit_candidate(contract, user_inputs={"buyer_id": "U1"})
    assert candidate_ok.missing_inputs == []


def test_runtime_catalog_missing_inputs_is_owned_by_runtime():
    """Runtime 本地维护显式契约缺参逻辑，不依赖 Catalog 内部 helper。"""
    contract = AgentSceneContract(
        sceneCode="create_paid_order",
        sceneName="造一笔已支付订单",
        capabilityType=CapabilityType.CREATE,
        inputSchema=[
            InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING, required=True),
            InputFieldDefinition(
                name="buyer_id",
                label="买家",
                type=InputFieldType.STRING,
                required=True,
                semanticType="USER_ID",
                aliases=["userId"],
            ),
            InputFieldDefinition(name="remark", label="备注", type=InputFieldType.STRING, required=False),
        ],
        versionNo=1,
        executable=True,
        hasSideEffects=False,
    )

    assert _missing_required_inputs(contract, {"userid"}) == []
    assert _missing_required_inputs(contract, {"unknown"}) == ["buyer_id"]


@pytest.mark.anyio
async def test_adapter_search_converts_and_clamps_high_score():
    """高累加分候选转换后 score<=1.0（验收标准 13）。"""
    contract = _make_contract()
    agent_candidate = AgentSceneCandidate(
        contract=contract,
        score=0.95,
        reasons=["文本命中"],
        missingInputs=[],
        requiresConfirmation=False,
    )
    # 模型层 score 受 le=1 约束，这里直接绕过校验塞一个超界值模拟累加分。
    object.__setattr__(agent_candidate, "score", 4.2)

    adapter = AgentCatalogAdapter(service=_FakeService(candidates=[agent_candidate], query_terms=["订单"]))
    candidates, terms = await adapter.search(
        goal="造一笔已支付订单",
        env_code="SIT1",
        user_inputs={},
        visible_variables=[],
        limit=5,
    )
    assert len(candidates) == 1
    assert candidates[0].score <= 1.0
    assert candidates[0].scene_code == "create_paid_order"
    assert candidates[0].contract_hash
    assert terms == ["订单"]


@pytest.mark.anyio
async def test_adapter_get_contract_raises_404_when_missing():
    """显式 scene_code 不存在 -> 404 透传。"""
    adapter = AgentCatalogAdapter(service=_FakeService(contract_missing=True))
    with pytest.raises(HTTPException) as exc:
        await adapter.get_contract(scene_code="nope", user_inputs={})
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_search_scenes_excludes_blacklist():
    """黑名单内 scene 不再被选中（验收标准 6 地基）。"""

    class _StubCatalog:
        async def search(self, **kwargs):
            return (
                [
                    SceneCandidate(
                        scene_code="bad_scene",
                        scene_name="坏场景",
                        score=0.9,
                        requires_confirmation=False,
                        contract_hash="h1",
                    ),
                    SceneCandidate(
                        scene_code="good_scene",
                        scene_name="好场景",
                        score=0.8,
                        requires_confirmation=False,
                        contract_hash="h2",
                    ),
                ],
                ["订单"],
            )

        async def get_contract(self, **kwargs):  # pragma: no cover - 不该被调用
            raise AssertionError("search 路径不应调 get_contract")

    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    requirement = create_scene_requirement(task_run, step)
    requirement.blacklist = ["bad_scene"]

    proposal = await search_scenes(requirement, {}, "SIT1", _StubCatalog())
    codes = [c.scene_code for c in proposal.candidates]
    assert codes == ["good_scene"]
    assert requirement.proposal_id == proposal.proposal_id


@pytest.mark.anyio
async def test_resolve_explicit_scene_synthesizes_single_candidate():
    """显式 scene_code 合成单候选 Proposal。"""

    class _StubCatalog:
        async def search(self, **kwargs):  # pragma: no cover - 不该被调用
            raise AssertionError("显式路径不应调 search")

        async def get_contract(self, *, scene_code, user_inputs):
            return SceneCandidate(
                scene_code=scene_code,
                scene_name="造一笔已支付订单",
                score=1.0,
                missing_inputs=["buyer_id"] if "buyer_id" not in user_inputs else [],
                requires_confirmation=False,
                contract_hash="h",
            )

    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    requirement = create_scene_requirement(task_run, step)

    proposal = await resolve_explicit_scene(requirement, "create_paid_order", {}, _StubCatalog())
    assert len(proposal.candidates) == 1
    assert proposal.candidates[0].scene_code == "create_paid_order"
    assert proposal.candidates[0].missing_inputs == ["buyer_id"]
    assert requirement.status == RequirementStatus.PENDING  # 编排不动状态机


def test_catalog_hash_equals_guard_hash():
    """红线：catalog 适配器与执行前重验 gate 必须复算出相同 hash。

    若 catalog._contract_hash 与 support.contract_hash.contract_hash 不一致，
    执行前重验会对所有未变化的场景误报漂移。此测试锁定两者同源。
    """
    from app.gdp.agent_runtime.adapters.catalog import _contract_hash
    from app.gdp.agent_runtime.support.contract_hash import contract_hash

    contract = _make_contract(required_inputs=["buyer_id", "amount"], has_side_effects=True)
    assert _contract_hash(contract) == contract_hash(contract)


def test_contract_hash_is_stable_and_drift_sensitive():
    """同一契约复算稳定；契约变化（新增必填参数）哈希必变。"""
    from app.gdp.agent_runtime.support.contract_hash import contract_hash

    base = _make_contract(required_inputs=["buyer_id"])
    same = _make_contract(required_inputs=["buyer_id"])
    drifted = _make_contract(required_inputs=["buyer_id", "amount"])

    assert contract_hash(base) == contract_hash(same)
    assert contract_hash(base) != contract_hash(drifted)
