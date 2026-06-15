"""任务账本时间线投影。"""

from __future__ import annotations

from typing import Any

from ..models import (
    Action,
    ActionAttempt,
    DecisionRecord,
    Evidence,
    Observation,
    PlanStep,
    Requirement,
    RequirementProposal,
    Variable,
    Verdict,
)


def build_timeline(
    *,
    task_run_id: str,
    steps: list[PlanStep],
    actions: list[Action],
    attempts: list[ActionAttempt],
    observations: list[Observation],
    evidences: list[Evidence],
    verdicts: list[Verdict],
    variables: list[Variable],
    requirements: list[Requirement],
    proposals: list[RequirementProposal],
    decisions: list[DecisionRecord],
    approval_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """把完整账本事实投影为前端可渲染的任务时间线。"""
    return {
        "task_run_id": task_run_id,
        "steps": [s.model_dump(mode="json") for s in steps],
        "actions": [a.model_dump(mode="json") for a in actions],
        "attempts": [a.model_dump(mode="json") for a in attempts],
        "observations": [o.model_dump(mode="json") for o in observations],
        "evidences": [e.model_dump(mode="json") for e in evidences],
        "verdicts": [v.model_dump(mode="json") for v in verdicts],
        "variables": [v.model_dump(mode="json") for v in variables],
        "requirements": [r.model_dump(mode="json") for r in requirements],
        "proposals": [_proposal_view(p) for p in proposals],
        "decisions": [d.model_dump(mode="json") for d in decisions],
        "approval_records": approval_records,
    }


def _proposal_view(proposal: RequirementProposal) -> dict[str, Any]:
    """候选集投影——只向用户展示决策所需信息，不暴露敏感入参原值。

    业务目标：用户在前端看到候选场景列表时，只需知道场景名、匹配分数、推荐原因、
    缺失入参和是否需要确认，不应看到系统内部传给接口的原始参数。
    当前动作：将完整的 Proposal 对象裁剪为安全的前端展示视图。
    预期结果：前端展示候选卡片，用户可基于安全信息做出选择。
    """
    return {
        "proposal_id": proposal.proposal_id,
        "task_run_id": proposal.task_run_id,
        "step_id": proposal.step_id,
        "requirement_id": proposal.requirement_id,
        "status": proposal.status.value,
        "selected_scene_code": proposal.selected_scene_code,
        "selection_source": proposal.selection_source.value if proposal.selection_source else None,
        "query_terms": list(proposal.query_terms),
        "created_at": proposal.created_at.isoformat(),
        "candidates": [
            {
                "scene_code": c.scene_code,
                "scene_name": c.scene_name,
                "score": c.score,
                "reasons": list(c.reasons),
                "missing_inputs": list(c.missing_inputs),
                "requires_confirmation": c.requires_confirmation,
            }
            for c in proposal.candidates
        ],
    }
