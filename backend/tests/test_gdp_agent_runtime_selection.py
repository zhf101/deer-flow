"""GDP Agent Runtime 选择决策专项测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.gdp.agent_runtime.llm import suggest_scene_rerank
from app.gdp.agent_runtime.models import (
    LMProposal,
    ProposalStatus,
    Requirement,
    RequirementLayer,
    RequirementProposal,
    RequirementStatus,
    SceneCandidate,
    SelectionSource,
)
from app.gdp.agent_runtime.selection import (
    AUTO_SELECT_THRESHOLD,
    apply_selection,
    blacklist_scene,
    decide_selection,
    ensure_requirement_matches_scene,
    ensure_selection_consistency,
)


def _candidate(
    scene_code: str = "create_paid_order",
    *,
    score: float = 0.9,
    missing_inputs: list[str] | None = None,
    requires_confirmation: bool = False,
) -> SceneCandidate:
    return SceneCandidate(
        scene_code=scene_code,
        scene_name=f"场景-{scene_code}",
        score=score,
        missing_inputs=missing_inputs or [],
        requires_confirmation=requires_confirmation,
        contract_hash="h",
    )


def _proposal(candidates: list[SceneCandidate]) -> RequirementProposal:
    return RequirementProposal(
        proposal_id="prop-1",
        task_run_id="tr-1",
        step_id="step-1",
        requirement_id="req-1",
        candidates=candidates,
        query_terms=["订单"],
        status=ProposalStatus.PENDING,
        created_at=datetime.now(UTC),
    )


def _requirement(status: RequirementStatus = RequirementStatus.RESOLVING) -> Requirement:
    now = datetime.now(UTC)
    return Requirement(
        requirement_id="req-1",
        task_run_id="tr-1",
        step_id="step-1",
        layer=RequirementLayer.SCENE,
        goal="造一笔已支付订单",
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_decide_single_high_confidence_auto_selected():
    """单候选高置信、入参齐全、无副作用 -> AUTO_SELECTED。"""
    outcome = decide_selection(_proposal([_candidate(score=0.8)]))
    assert outcome.kind == "AUTO_SELECTED"
    assert outcome.scene_code == "create_paid_order"


def test_decide_no_candidate():
    """零候选 -> NO_CANDIDATE，带可解释问题。"""
    outcome = decide_selection(_proposal([]))
    assert outcome.kind == "NO_CANDIDATE"
    assert outcome.question


def test_decide_multiple_candidates_need_user():
    """多候选 -> NEED_USER，问题里列出候选。"""
    outcome = decide_selection(
        _proposal([_candidate("a", score=0.8), _candidate("b", score=0.7)])
    )
    assert outcome.kind == "NEED_USER"
    assert "a" in (outcome.question or "")
    assert "b" in (outcome.question or "")


def test_decide_single_low_score_need_user():
    """单候选但低于阈值 -> NEED_USER。"""
    outcome = decide_selection(_proposal([_candidate(score=AUTO_SELECT_THRESHOLD - 0.1)]))
    assert outcome.kind == "NEED_USER"


def test_decide_single_missing_inputs_need_user():
    """单候选但缺必填入参 -> NEED_USER。"""
    outcome = decide_selection(_proposal([_candidate(missing_inputs=["buyer_id"])]))
    assert outcome.kind == "NEED_USER"
    assert "buyer_id" in (outcome.question or "")


def test_decide_single_requires_confirmation_need_user():
    """单候选高置信但有副作用 -> NEED_USER（等审批）。"""
    outcome = decide_selection(_proposal([_candidate(requires_confirmation=True)]))
    assert outcome.kind == "NEED_USER"


def test_apply_selection_writes_fact():
    """apply_selection 写选定事实到 Requirement 和 Proposal。"""
    proposal = _proposal([_candidate()])
    requirement = _requirement()
    requirement, proposal = apply_selection(
        requirement, proposal, "create_paid_order", SelectionSource.AUTO
    )
    assert requirement.selected_scene_code == "create_paid_order"
    assert proposal.selected_scene_code == "create_paid_order"
    assert proposal.selection_source == SelectionSource.AUTO
    assert proposal.status == ProposalStatus.SELECTED


def test_selection_consistency_rejects_mismatched_requirement_and_proposal():
    """Requirement 和 Proposal 的归属或选定值不一致时，必须显式失败。"""
    proposal = _proposal([_candidate("create_paid_order")])
    requirement = _requirement()
    requirement.requirement_id = "req-other"

    with pytest.raises(ValueError, match="不属于当前 Requirement"):
        ensure_selection_consistency(requirement, proposal)


def test_selection_consistency_rejects_mismatched_scene_code():
    """Requirement / Proposal / 执行目标不能记录三套不同 scene_code。"""
    proposal = _proposal([_candidate("create_paid_order")])
    requirement = _requirement()
    requirement.selected_scene_code = "create_paid_order"
    proposal.selected_scene_code = "create_unpaid_order"
    proposal.status = ProposalStatus.SELECTED

    with pytest.raises(ValueError, match="scene_code 不一致"):
        ensure_selection_consistency(requirement, proposal, "create_paid_order")


def test_requirement_execute_scene_must_match_selected_scene():
    """执行 Action 前，目标 scene_code 必须和 Requirement 已选事实一致。"""
    requirement = _requirement()
    requirement.selected_scene_code = "create_paid_order"

    with pytest.raises(ValueError, match="执行目标不一致"):
        ensure_requirement_matches_scene(requirement, "create_unpaid_order")


def test_apply_selection_rejects_scene_not_in_candidates():
    """选一个不在候选内的 scene_code -> ValueError（验收标准 7）。"""
    proposal = _proposal([_candidate("a")])
    requirement = _requirement()
    with pytest.raises(ValueError):
        apply_selection(requirement, proposal, "not_a_candidate", SelectionSource.USER)


def test_apply_selection_rejects_lm_proposal():
    """LMProposal 不能作为 source 写入（验收标准 10）。"""
    proposal = _proposal([_candidate()])
    requirement = _requirement()
    bad = LMProposal(
        proposal_id="lp-1",
        payload=SelectionSource.LLM,
        prompt_hash="hash",
        model_name="m",
        confidence=0.9,
    )
    with pytest.raises(TypeError):
        apply_selection(requirement, proposal, "create_paid_order", bad)  # type: ignore[arg-type]


def test_blacklist_scene_appends_once():
    """黑名单去重追加。"""
    requirement = _requirement()
    requirement = blacklist_scene(requirement, "bad")
    requirement = blacklist_scene(requirement, "bad")
    assert requirement.blacklist == ["bad"]


@pytest.mark.anyio
async def test_suggest_scene_rerank_returns_lm_proposal():
    """LLM 重排建议必须包成 LMProposal。"""
    proposal = _proposal([_candidate("a"), _candidate("b")])
    suggestion = await suggest_scene_rerank(proposal, "造一笔订单")
    assert isinstance(suggestion, LMProposal)
    assert suggestion.payload.ranked_scene_codes == ["a", "b"]
