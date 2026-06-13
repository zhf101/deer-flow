"""场景目录搜索与契约解析。

本模块负责为用户的造数目标寻找合适的已发布场景——从场景目录中搜索候选、
解析场景契约，为用户找到能满足需求的造数方案。

纯编排逻辑，不调用 LLM，不复制打分算法；搜索和契约解析均委托给 Catalog adapter。
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
    """为用户的当前造数步骤创建一个"需要找到合适场景"的缺口记录。

    业务目标：标记当前步骤尚未确定用哪个场景来执行，驱动后续搜索流程为用户寻找匹配方案。
    当前动作：基于步骤目标（goal）创建一个 SCENE 层的 Requirement，初始状态为 PENDING。
    预期结果：返回的 Requirement 将作为搜索入口，交由 search_scenes 或 resolve_explicit_scene 填充候选。
    """
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
    """从场景目录中搜索能满足用户造数目标的候选场景。

    业务目标：为用户找到所有可能满足需求的已发布场景，同时排除已知失败的方案，
    避免把用户引导到已经走过的死路上。
    当前动作：调用 Catalog adapter 按用户目标和输入进行搜索，再用黑名单过滤掉
    之前执行失败的场景。
    预期结果：返回一份 PENDING 状态的 Proposal，包含过滤后的候选清单，
    交由 decide_selection 决定是自动选定还是让用户手动选择。
    """
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
    """当用户直接指定了场景编码时，解析该场景的契约并确认入参是否齐全。

    业务目标：用户明确知道要用哪个场景（或系统在零候选后要求用户补录 scene_code），
    此时跳过搜索直接验证该场景是否可用、入参是否足够。
    当前动作：调用 Catalog adapter 获取指定场景的契约，校验必填参数；
    scene_code 不存在或未发布时 adapter 会抛出 404。
    预期结果：返回只含该场景的单候选 PENDING Proposal，由选择决策模块继续处理。

    两个入口共用此函数：
    - start 时带了显式 scene_code（向后兼容路径）
    - 零候选后用户通过 SUPPLY_SCENE_CODE 手动补录
    缺参校验统一由契约的 missing_inputs 驱动，彻底替代旧的 _REQUIRED_INPUTS_BY_SCENE 硬编码。
    """
    candidate = await catalog.get_contract(scene_code=scene_code, user_inputs=inputs)
    proposal = _new_proposal(requirement, [candidate], query_terms=[])
    requirement.proposal_id = proposal.proposal_id
    return proposal
