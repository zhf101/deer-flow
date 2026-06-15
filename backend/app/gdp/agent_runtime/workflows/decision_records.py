"""决策审计账本——记录系统为用户做出的每个关键选择。

业务目标：让用户能追溯"系统为什么这样做"。
当前动作：为场景搜索、场景选择、审批要求等环节分别生成决策记录。
预期结果：每个决策都有完整的候选项、选中理由、淘汰理由和判定标准，用户可随时回溯审计。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..models import (
    DecisionKind,
    DecisionOption,
    DecisionRecord,
    DecisionRejection,
    DecisionSource,
    DecisionStatus,
    Requirement,
    RequirementProposal,
    SceneCandidate,
    TaskRun,
)
from .selection_policy import AUTO_SELECT_THRESHOLD, SelectionOutcome


def build_scene_search_decision(
    task_run: TaskRun,
    requirement: Requirement,
    proposal: RequirementProposal,
    *,
    input_ref: str | None,
) -> DecisionRecord:
    """记录系统为造数目标搜索到了哪些候选场景。

    业务目标：用户提出造数目标后，系统在场景目录中检索匹配的已发布场景。
    当前动作：将检索结果（候选列表、检索词、匹配标准）包装为一条决策记录。
    预期结果：用户能看到系统搜到了哪些场景、用了什么检索词、基于什么标准筛选。
    """
    return DecisionRecord(
        decision_id=_gen_id(),
        task_run_id=task_run.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        proposal_id=proposal.proposal_id,
        action_id=None,
        scene_run_id=None,
        decision_kind=DecisionKind.SCENE_SEARCH,
        decision_source=DecisionSource.CATALOG,
        status=DecisionStatus.DECIDED,
        target_type="proposal",
        target_id=proposal.proposal_id,
        input_ref=input_ref,
        options=[_candidate_option(item) for item in proposal.candidates],
        selected_option=None,
        selected_reasons=[
            "基于用户目标、环境、当前输入和可见变量检索已发布场景。",
            f"检索词：{', '.join(proposal.query_terms) if proposal.query_terms else '无'}。",
        ],
        rejected_reasons=[],
        criteria=["场景已发布", "目标语义匹配", "环境可用", "黑名单场景已排除"],
        evidence_refs=[requirement.requirement_id, proposal.proposal_id],
        model_info=None,
        summary=f"按目标“{requirement.goal}”检索到 {len(proposal.candidates)} 个候选场景。",
        created_at=_now(),
    )


def build_scene_selection_decision(
    task_run: TaskRun,
    requirement: Requirement,
    proposal: RequirementProposal,
    outcome: SelectionOutcome,
    *,
    input_ref: str | None,
) -> DecisionRecord:
    """记录系统自动选定场景或等待用户选择的原因。

    业务目标：在候选场景中确定最终执行目标，能自动选则自动选，否则交用户决策。
    当前动作：根据选择规则（单候选、评分达标、无缺失入参、无需审批）判定并记录选中理由。
    预期结果：用户能看到选中了哪个场景、为什么选它、其他候选为什么被淘汰。
    """
    selected = _candidate_by_code(proposal, outcome.scene_code)
    status = DecisionStatus.DECIDED if outcome.kind == "AUTO_SELECTED" else DecisionStatus.WAITING_USER
    return DecisionRecord(
        decision_id=_gen_id(),
        task_run_id=task_run.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        proposal_id=proposal.proposal_id,
        action_id=None,
        scene_run_id=None,
        decision_kind=DecisionKind.SCENE_SELECTION,
        decision_source=DecisionSource.RULE,
        status=status,
        target_type="scene" if selected else None,
        target_id=selected.scene_code if selected else None,
        input_ref=input_ref,
        options=[_candidate_option(item) for item in proposal.candidates],
        selected_option=_candidate_option(selected) if selected else None,
        selected_reasons=_selection_reasons(outcome, selected),
        rejected_reasons=_rejected_candidates(proposal.candidates, selected.scene_code if selected else None),
        criteria=[
            "单候选时才允许自动选择",
            f"评分需达到自动选择阈值 {AUTO_SELECT_THRESHOLD}",
            "候选不能缺少必填入参",
            "候选不能要求额外审批",
        ],
        evidence_refs=[requirement.requirement_id, proposal.proposal_id],
        model_info=None,
        summary=outcome.reason,
        created_at=_now(),
    )


def build_user_scene_selection_decision(
    task_run: TaskRun,
    requirement: Requirement,
    proposal: RequirementProposal,
    scene_code: str,
    *,
    input_ref: str | None,
) -> DecisionRecord:
    """记录用户在候选场景中手动选定或补录场景的事实。

    业务目标：系统无法自动决策时，由用户拍板选定要执行的场景。
    当前动作：将用户的选择记录为决策来源为 USER 的决策记录。
    预期结果：审计账本中明确标记该决策由用户显式做出，优先于系统建议。
    """
    selected = _candidate_by_code(proposal, scene_code)
    return DecisionRecord(
        decision_id=_gen_id(),
        task_run_id=task_run.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        proposal_id=proposal.proposal_id,
        action_id=None,
        scene_run_id=None,
        decision_kind=DecisionKind.SCENE_SELECTION,
        decision_source=DecisionSource.USER,
        status=DecisionStatus.DECIDED,
        target_type="scene",
        target_id=scene_code,
        input_ref=input_ref,
        options=[_candidate_option(item) for item in proposal.candidates],
        selected_option=_candidate_option(selected) if selected else None,
        selected_reasons=[f"用户在候选场景中选择了 {scene_code}。"],
        rejected_reasons=_rejected_candidates(proposal.candidates, scene_code),
        criteria=["用户显式选择优先", "scene_code 必须在候选或契约解析结果内"],
        evidence_refs=[requirement.requirement_id, proposal.proposal_id],
        model_info=None,
        summary=f"用户选择场景 {scene_code}。",
        created_at=_now(),
    )


def build_approval_requirement_decision(
    task_run: TaskRun,
    requirement: Requirement,
    proposal: RequirementProposal,
    candidate: SceneCandidate,
    *,
    approved: bool,
    input_ref: str | None,
) -> DecisionRecord:
    """记录场景执行前为什么需要用户审批，以及用户是否已批准。

    业务目标：高风险或有写副作用的场景在执行前必须获得用户显式授权。
    当前动作：根据场景的审批声明和用户回应生成决策记录。
    预期结果：用户能追溯该场景为何被挂起等待审批，以及审批是否已通过。
    """
    return DecisionRecord(
        decision_id=_gen_id(),
        task_run_id=task_run.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        proposal_id=proposal.proposal_id,
        action_id=None,
        scene_run_id=None,
        decision_kind=DecisionKind.APPROVAL_REQUIREMENT,
        decision_source=DecisionSource.USER if approved else DecisionSource.RULE,
        status=DecisionStatus.DECIDED if approved else DecisionStatus.WAITING_USER,
        target_type="scene",
        target_id=candidate.scene_code,
        input_ref=input_ref,
        options=[_candidate_option(candidate)],
        selected_option=_candidate_option(candidate),
        selected_reasons=[
            "候选场景声明执行前需要用户审批。",
            "用户已批准执行。" if approved else "尚未收到用户批准，执行前挂起等待。",
        ],
        rejected_reasons=[],
        criteria=["有写副作用或高风险操作时必须审批", "审批通过前不发起场景写请求"],
        evidence_refs=[requirement.requirement_id, proposal.proposal_id],
        model_info=None,
        summary=(
            f"用户已批准执行场景 {candidate.scene_code}。"
            if approved
            else f"场景 {candidate.scene_code} 执行前需要用户审批。"
        ),
        created_at=_now(),
    )


def _candidate_option(candidate: SceneCandidate) -> DecisionOption:
    return DecisionOption(
        option_id=candidate.scene_code,
        option_type="scene",
        label=candidate.scene_name,
        score=candidate.score,
        reasons=list(candidate.reasons),
        metadata={
            "missing_inputs": list(candidate.missing_inputs),
            "requires_confirmation": candidate.requires_confirmation,
            "contract_hash": candidate.contract_hash,
        },
    )


def _candidate_by_code(proposal: RequirementProposal, scene_code: str | None) -> SceneCandidate | None:
    if scene_code is None:
        return None
    return next((item for item in proposal.candidates if item.scene_code == scene_code), None)


def _selection_reasons(outcome: SelectionOutcome, selected: SceneCandidate | None) -> list[str]:
    if selected is None:
        return [outcome.reason]
    return [
        outcome.reason,
        f"候选评分 {selected.score}。",
        "候选无缺失入参。" if not selected.missing_inputs else "候选仍缺少入参：" + "，".join(selected.missing_inputs),
        "候选无需审批。" if not selected.requires_confirmation else "候选需要审批。",
    ]


def _rejected_candidates(candidates: list[SceneCandidate], selected_scene_code: str | None) -> list[DecisionRejection]:
    return [
        DecisionRejection(option_id=item.scene_code, reason="未被本次决策选中。")
        for item in candidates
        if item.scene_code != selected_scene_code
    ]


def _gen_id() -> str:
    return f"dec-{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(UTC)
