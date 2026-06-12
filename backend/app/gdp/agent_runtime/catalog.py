"""GDP Agent Runtime 搜索编排。

建 Requirement、调 Catalog adapter、产出 Proposal。纯编排，不调 LLM，不复刻打分。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from .adapters.catalog import SceneCatalogPort
from .models import (
    PlanStep,
    ProposalStatus,
    Requirement,
    RequirementLayer,
    RequirementProposal,
    RequirementStatus,
    SceneCandidate,
    TaskRun,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def create_scene_requirement(task_run: TaskRun, step: PlanStep) -> Requirement:
    """为当前 step 创建一个 SCENE 层缺口。"""
    now = _now()
    return Requirement(
        requirement_id=_gen_id("req"),
        task_run_id=task_run.task_run_id,
        step_id=step.step_id,
        layer=RequirementLayer.SCENE,
        goal=step.goal,
        status=RequirementStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


def _new_proposal(
    requirement: Requirement,
    candidates: list[SceneCandidate],
    query_terms: list[str],
) -> RequirementProposal:
    return RequirementProposal(
        proposal_id=_gen_id("prop"),
        task_run_id=requirement.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        candidates=candidates,
        query_terms=query_terms,
        status=ProposalStatus.PENDING,
        created_at=_now(),
    )


async def search_scenes(
    requirement: Requirement,
    inputs: dict[str, Any],
    env_code: str | None,
    catalog: SceneCatalogPort,
    limit: int = 5,
    visible_variables: list[dict[str, Any]] | None = None,
) -> RequirementProposal:
    """调 Catalog 搜索候选，排除 blacklist，产出 PENDING Proposal。"""
    candidates, query_terms = await catalog.search(
        goal=requirement.goal,
        env_code=env_code,
        user_inputs=inputs,
        visible_variables=visible_variables or [],
        limit=limit,
    )
    blacklist = set(requirement.blacklist)
    filtered = [c for c in candidates if c.scene_code not in blacklist]
    proposal = _new_proposal(requirement, filtered, query_terms)
    requirement.proposal_id = proposal.proposal_id
    return proposal


async def resolve_explicit_scene(
    requirement: Requirement,
    scene_code: str,
    inputs: dict[str, Any],
    catalog: SceneCatalogPort,
) -> RequirementProposal:
    """按显式 scene_code 解析契约，合成单候选 PENDING Proposal。

    两个入口共用：start 带显式 scene_code（向后兼容路径）、零候选后 SUPPLY_SCENE_CODE
    手动补录。缺参校验只此一套（契约 missing_inputs 驱动），彻底替代 _REQUIRED_INPUTS_BY_SCENE。
    scene_code 不存在 / 未发布 -> catalog.get_contract 抛 404。
    """
    candidate = await catalog.get_contract(scene_code=scene_code, user_inputs=inputs)
    proposal = _new_proposal(requirement, [candidate], query_terms=[])
    requirement.proposal_id = proposal.proposal_id
    return proposal
