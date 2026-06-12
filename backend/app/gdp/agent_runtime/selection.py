"""GDP Agent Runtime 选择决策。

规则自动选定 + 应用用户/LLM 选定 + 黑名单。确定性逻辑，
事实写入（selected_scene_code）必须经本模块校验，拒绝 LMProposal。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .models import (
    ProposalStatus,
    Requirement,
    RequirementProposal,
    SceneCandidate,
    SelectionSource,
    reject_lm_proposal,
)

# 单候选自动选定的最低评分阈值。做成模块常量便于真实 case 调参；变更必须有测试。
AUTO_SELECT_THRESHOLD = 0.6


class SelectionOutcome(BaseModel):
    """选择决策结果。"""

    kind: Literal["AUTO_SELECTED", "NEED_USER", "NO_CANDIDATE"]
    scene_code: str | None = None
    reason: str
    question: str | None = None  # NEED_USER / NO_CANDIDATE 时给用户的问题


def _candidate_of(proposal: RequirementProposal, scene_code: str) -> SceneCandidate | None:
    for candidate in proposal.candidates:
        if candidate.scene_code == scene_code:
            return candidate
    return None


def decide_selection(proposal: RequirementProposal) -> SelectionOutcome:
    """规则决策：单候选高置信且入参齐全且无需审批 -> AUTO_SELECTED；否则 NEED_USER / NO_CANDIDATE。

    纯函数，不调 LLM，不动状态机。
    """
    candidates = proposal.candidates
    if not candidates:
        return SelectionOutcome(
            kind="NO_CANDIDATE",
            reason="没有匹配到任何已发布 Scene。",
            question="没有找到匹配的 Scene。请补充 scene_code，或调整造数目标后重试。",
        )

    if len(candidates) == 1:
        only = candidates[0]
        if (
            only.score >= AUTO_SELECT_THRESHOLD
            and not only.missing_inputs
            and not only.requires_confirmation
        ):
            return SelectionOutcome(
                kind="AUTO_SELECTED",
                scene_code=only.scene_code,
                reason=f"单候选高置信自动选定：{only.scene_name}（{only.scene_code}）。",
            )

    return SelectionOutcome(
        kind="NEED_USER",
        reason="需要用户在候选中选定或补充信息。",
        question=_build_need_user_question(candidates),
    )


def _build_need_user_question(candidates: list[SceneCandidate]) -> str:
    """列候选 + 缺口 + 需审批项，供用户选择。不含敏感入参原值。"""
    lines = ["请在以下候选中选择一个 Scene（回复 SELECT_SCENE 并带上 scene_code）："]
    for index, candidate in enumerate(candidates, start=1):
        parts = [f"{index}. {candidate.scene_name}（{candidate.scene_code}），评分 {candidate.score}"]
        if candidate.missing_inputs:
            parts.append("缺必填入参：" + "，".join(candidate.missing_inputs))
        if candidate.requires_confirmation:
            parts.append("执行有写副作用，需批准")
        lines.append("；".join(parts))
    return "\n".join(lines)


def apply_selection(
    requirement: Requirement,
    proposal: RequirementProposal,
    scene_code: str,
    source: SelectionSource,
) -> tuple[Requirement, RequirementProposal]:
    """把选定结果写入 Requirement 和 Proposal。拒绝 LMProposal，校验 scene_code 在候选内。

    本函数只负责写选定事实，不负责状态机转移；调用方需先保证 Requirement 已 RESOLVING。
    """
    reject_lm_proposal(scene_code)
    reject_lm_proposal(source)

    candidate = _candidate_of(proposal, scene_code)
    if candidate is None:
        raise ValueError(f"scene_code 不在候选内：{scene_code}")

    proposal.selected_scene_code = scene_code
    proposal.selection_source = source
    proposal.status = ProposalStatus.SELECTED

    requirement.selected_scene_code = scene_code
    return requirement, proposal


def blacklist_scene(requirement: Requirement, scene_code: str) -> Requirement:
    """执行失败后把 scene_code 加入黑名单，重搜时排除。"""
    if scene_code not in requirement.blacklist:
        requirement.blacklist.append(scene_code)
    return requirement
