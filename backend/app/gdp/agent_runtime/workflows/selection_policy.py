"""场景选择决策。

本模块负责从候选场景中选出一个可执行的方案——优先自动选定高置信候选，
否则暂停让用户手动选择，确保用户的造数目标用对的场景来执行。

确定性规则逻辑，不调用 LLM；所有选定事实写入 Requirement/Proposal 账本，
且必须经本模块校验，拒绝 LLM 直接提议的选定结果。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..models import (
    ProposalStatus,
    Requirement,
    RequirementProposal,
    SceneCandidate,
    SelectionSource,
    reject_lm_proposal,
)

# 单候选自动选定的最低评分阈值。
# 业务含义：只有当唯一候选的匹配度达到此分数时，系统才会跳过用户确认直接选定，
# 避免把低匹配度的场景强加给用户。调参需基于真实 case，且必须配套测试。
AUTO_SELECT_THRESHOLD = 0.6


class SelectionOutcome(BaseModel):
    """选择决策的结果，描述系统对"用哪个场景来执行"这一问题的回答。"""

    kind: Literal["AUTO_SELECTED", "NEED_USER", "NO_CANDIDATE"]
    scene_code: str | None = None
    reason: str
    question: str | None = None  # 当需要用户介入时（NEED_USER / NO_CANDIDATE），展示给用户的提问


def _candidate_of(proposal: RequirementProposal, scene_code: str) -> SceneCandidate | None:
    for candidate in proposal.candidates:
        if candidate.scene_code == scene_code:
            return candidate
    return None


def decide_selection(proposal: RequirementProposal) -> SelectionOutcome:
    """规则决策引擎：从候选清单中决定是自动选定还是让用户手动选。

    业务目标：在用户无需操心时自动推进（单候选高置信且入参齐全且无需审批），
    在存在歧义或风险时暂停让用户做选择，确保造数任务用对的场景来执行。
    当前动作：按规则判定——无候选返回 NO_CANDIDATE，单候选满足阈值且无缺口返回
    AUTO_SELECTED，其余返回 NEED_USER。
    预期结果：返回 SelectionOutcome，调用方据此决定是直接执行还是挂起等待用户回复。

    纯函数，不调用 LLM，不动状态机。
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
    """为用户生成一个可读的场景选择菜单。

    业务目标：当系统无法自动决策时，把所有候选的名称、评分、缺失入参和审批需求
    以人类可读的方式呈现给用户，帮助用户做出正确选择。
    注意：不展示敏感入参的原始值，只列出字段名。
    """
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
    """把用户（或自动）选定的场景写入事实账本。

    业务目标：确保后续执行使用的场景和用户选定的完全一致，防止张冠李戴。
    当前动作：校验 scene_code 确实在候选清单内，拒绝 LLM 直接提议的值，
    然后同步更新 Requirement 和 Proposal 的选中场景记录。
    预期结果：两个账本对象均标记为已选定，且记录的 scene_code 一致。

    本函数只写选定事实，不负责状态机转移；调用方需保证 Requirement 已进入 RESOLVING 状态。
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
    ensure_selection_consistency(requirement, proposal, scene_code)
    return requirement, proposal


def blacklist_scene(requirement: Requirement, scene_code: str) -> Requirement:
    """把执行失败的场景加入黑名单，避免再次推荐给用户。

    业务目标：用户已经尝试过某个场景并失败了，不应再看到同样的推荐，
    否则会造成"死循环"体验。
    当前动作：将 scene_code 追加到 Requirement 的黑名单列表（去重）。
    预期结果：后续 search_scenes 过滤时会自动排除此场景。
    """
    if scene_code not in requirement.blacklist:
        requirement.blacklist.append(scene_code)
    return requirement


def ensure_selection_consistency(
    requirement: Requirement,
    proposal: RequirementProposal,
    scene_code: str | None = None,
) -> None:
    """校验账本各处的场景选择事实是否一致，防止执行错误的场景。

    业务目标：Requirement 和 Proposal 中记录的任务、步骤、选中场景必须完全匹配，
    任何不一致都意味着系统内部状态出现了错乱，必须立即阻断而非静默继续。
    当前动作：逐一校验 task_run_id、step_id、requirement_id 的对应关系，
    以及三方（Requirement、Proposal、传入参数）的 scene_code 是否一致。
    预期结果：全部通过则静默返回；任一项不一致则抛出 ValueError 阻断执行。
    """
    if requirement.task_run_id != proposal.task_run_id:
        raise ValueError("Requirement 和 Proposal 不属于同一个 TaskRun。")
    if requirement.step_id != proposal.step_id:
        raise ValueError("Requirement 和 Proposal 不属于同一个 PlanStep。")
    if requirement.requirement_id != proposal.requirement_id:
        raise ValueError("Proposal 不属于当前 Requirement。")

    selected_values = [
        value
        for value in (requirement.selected_scene_code, proposal.selected_scene_code, scene_code)
        if value is not None
    ]
    if selected_values and any(value != selected_values[0] for value in selected_values):
        raise ValueError("Requirement、Proposal 和执行目标的 scene_code 不一致。")

    if proposal.status == ProposalStatus.SELECTED and proposal.selected_scene_code is None:
        raise ValueError("Proposal 已选定但缺少 selected_scene_code。")


def ensure_requirement_matches_scene(requirement: Requirement, scene_code: str) -> None:
    """执行前的最后一道防线：确认即将执行的场景与账本中记录的选定场景一致。

    业务目标：防止编排过程中出现场景漂移——用户选的是 A 场景，实际却去执行了 B 场景。
    当前动作：如果 Requirement 已记录了选中场景，则校验它与传入的 scene_code 相同。
    预期结果：一致则静默放行；不一致则抛出 ValueError 阻断执行。
    """
    if requirement.selected_scene_code is not None and requirement.selected_scene_code != scene_code:
        raise ValueError("Requirement 已选场景和执行目标不一致。")
