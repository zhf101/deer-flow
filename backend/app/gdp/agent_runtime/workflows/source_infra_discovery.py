"""Source / Infra 只读发现工作流。

本模块只在 Scene 零候选时向下发现已有 HTTP/SQL Source 和基础配置摘要，
不自动保存 Source、Scene 或基础配置。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..adapters.catalog import SceneCatalogPort
from ..domain.config_writeback import ConfigWritebackResult, ConfigWritebackStatus
from ..domain.transitions import transition_requirement
from ..models import (
    InfraCandidate,
    PlanStep,
    ProposalStatus,
    Requirement,
    RequirementLayer,
    RequirementProposal,
    RequirementStatus,
    SourceCandidate,
    TaskRun,
)
from ..ports.config_writeback import ConfigWritebackPort
from ..store import Store
from ..support.errors import RuntimeServiceError
from .decision_records import build_config_writeback_decision


@dataclass
class SourceInfraDiscoveryResult:
    """Scene 零候选后 Source/Infra 发现和可选写回结果。"""

    question: str
    writeback_result: ConfigWritebackResult | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _create_child_requirement(
    task_run: TaskRun,
    step: PlanStep,
    *,
    layer: RequirementLayer,
    goal: str,
    parent_requirement: Requirement,
) -> Requirement:
    now = _now()
    return Requirement(
        requirement_id=_gen_id("req"),
        task_run_id=task_run.task_run_id,
        step_id=step.step_id,
        layer=layer,
        goal=goal,
        status=RequirementStatus.PENDING,
        parent_requirement_id=parent_requirement.requirement_id,
        created_at=now,
        updated_at=now,
    )


def _new_source_proposal(
    requirement: Requirement,
    *,
    source_candidates: list[SourceCandidate],
    infra_candidates: list[InfraCandidate],
    query_terms: list[str],
) -> RequirementProposal:
    return RequirementProposal(
        proposal_id=_gen_id("prop"),
        task_run_id=requirement.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        source_candidates=source_candidates,
        infra_candidates=infra_candidates,
        query_terms=query_terms,
        status=ProposalStatus.PENDING,
        created_at=_now(),
    )


def _new_infra_proposal(
    requirement: Requirement,
    *,
    infra_candidates: list[InfraCandidate],
) -> RequirementProposal:
    return RequirementProposal(
        proposal_id=_gen_id("prop"),
        task_run_id=requirement.task_run_id,
        step_id=requirement.step_id,
        requirement_id=requirement.requirement_id,
        infra_candidates=infra_candidates,
        query_terms=[],
        status=ProposalStatus.PENDING,
        created_at=_now(),
    )


def _source_resource_type(candidate: SourceCandidate) -> str:
    return "SQL" if candidate.source_type.upper() == "SQL" else "HTTP"


def _source_summary(candidate: SourceCandidate) -> str:
    if candidate.source_type.upper() == "SQL":
        return f"{candidate.source_name}（{candidate.source_code}，SQL，{candidate.datasource_code or '未知数据源'}）"
    return f"{candidate.source_name}（{candidate.source_code}，HTTP，{candidate.method or '-'} {candidate.path or '-'}）"


def _build_question(source_candidates: list[SourceCandidate], infra_candidates: list[InfraCandidate]) -> str:
    if source_candidates:
        lines = ["没有找到完整可执行的 Scene，但发现可复用的 Source 线索："]
        for index, candidate in enumerate(source_candidates, start=1):
            parts = [f"{index}. {_source_summary(candidate)}"]
            if candidate.missing_inputs:
                parts.append("缺入参：" + "，".join(candidate.missing_inputs))
            if candidate.requires_confirmation:
                parts.append("后续执行可能需要审批")
            lines.append("；".join(parts))
        missing = sorted({field for infra in infra_candidates for field in infra.missing_fields})
        if missing:
            lines.append("基础配置仍缺：" + "，".join(missing) + "。")
        else:
            lines.append("基础配置诊断未发现阻塞项。")
        lines.append("请先在场景管理中基于这些 Source 创建并发布组合场景，然后回到任务补充 scene_code。")
        return "\n".join(lines)
    return "没有找到匹配的 Scene，也没有发现可复用的 HTTP/SQL Source。请先补充 Source 或手动指定 scene_code。"


def _build_writeback_failed_question(base_question: str, result: ConfigWritebackResult) -> str:
    reason = result.reason or result.message
    issues = "；".join(result.validation_issues)
    suffix = f"自动发布组合 Scene 未完成：{reason}"
    if issues:
        suffix += f"。校验问题：{issues}"
    return f"{base_question}\n{suffix}"


def _can_writeback(source_candidates: list[SourceCandidate], infra_candidates: list[InfraCandidate]) -> bool:
    if not source_candidates or len(infra_candidates) < len(source_candidates):
        return False
    return all(item.ready and not item.missing_fields for item in infra_candidates)


def _normalize_writeback_result(raw: Any) -> ConfigWritebackResult:
    if isinstance(raw, ConfigWritebackResult):
        return raw
    if hasattr(raw, "model_dump"):
        return ConfigWritebackResult.model_validate(raw.model_dump(mode="json"))
    if isinstance(raw, dict):
        return ConfigWritebackResult.model_validate(raw)
    return ConfigWritebackResult.model_validate(vars(raw))


async def discover_source_and_infra_after_scene_miss(
    task_run: TaskRun,
    step: PlanStep,
    scene_requirement: Requirement,
    inputs: dict[str, Any],
    store: Store,
    catalog: SceneCatalogPort,
    config_writeback: ConfigWritebackPort | None = None,
    *,
    limit: int = 5,
) -> SourceInfraDiscoveryResult | None:
    """Scene 零候选后尝试只读发现 Source / Infra，并返回面向用户的提示。

    如果 Catalog 不支持 Source / Infra 发现，或下游依赖不可用，返回 None，
    调用方应保留原有 Scene 零候选挂起路径。
    """

    search_sources = getattr(catalog, "search_sources", None)
    if search_sources is None:
        return None

    visible_variables = [item.model_dump(mode="json") for item in store.list_variables(task_run.task_run_id)]
    try:
        source_candidates, query_terms = await search_sources(
            goal=scene_requirement.goal,
            env_code=task_run.env_code,
            user_inputs=inputs,
            visible_variables=visible_variables,
            limit=limit,
        )
    except RuntimeServiceError:
        return None

    source_requirement = _create_child_requirement(
        task_run,
        step,
        layer=RequirementLayer.SOURCE,
        goal=scene_requirement.goal,
        parent_requirement=scene_requirement,
    )
    infra_candidates: list[InfraCandidate] = []
    resolve_infra = getattr(catalog, "resolve_infra", None)
    if resolve_infra is not None:
        for candidate in source_candidates:
            try:
                infra_candidates.append(
                    await resolve_infra(
                        query=scene_requirement.goal,
                        env_code=task_run.env_code,
                        sys_code=candidate.sys_code,
                        datasource_code=candidate.datasource_code,
                        resource_type=_source_resource_type(candidate),
                    )
                )
            except RuntimeServiceError:
                continue

    source_requirement = transition_requirement(source_requirement, RequirementStatus.RESOLVING)
    source_proposal = _new_source_proposal(
        source_requirement,
        source_candidates=source_candidates,
        infra_candidates=infra_candidates,
        query_terms=query_terms,
    )
    source_requirement.proposal_id = source_proposal.proposal_id
    store.save_requirement(source_requirement)
    store.save_proposal(source_proposal)

    if source_candidates and infra_candidates:
        infra_requirement = _create_child_requirement(
            task_run,
            step,
            layer=RequirementLayer.INFRA,
            goal=scene_requirement.goal,
            parent_requirement=source_requirement,
        )
        infra_requirement = transition_requirement(infra_requirement, RequirementStatus.RESOLVING)
        infra_proposal = _new_infra_proposal(infra_requirement, infra_candidates=infra_candidates)
        infra_requirement.proposal_id = infra_proposal.proposal_id
        store.save_requirement(infra_requirement)
        store.save_proposal(infra_proposal)

    question = _build_question(source_candidates, infra_candidates)
    writeback_result: ConfigWritebackResult | None = None
    if config_writeback is not None and _can_writeback(source_candidates, infra_candidates):
        try:
            writeback_result = _normalize_writeback_result(
                await config_writeback.create_and_publish_scene_from_sources(
                    task_run=task_run,
                    scene_requirement=scene_requirement,
                    source_requirement=source_requirement,
                    proposal=source_proposal,
                    source_candidates=source_candidates,
                    infra_candidates=infra_candidates,
                    inputs=inputs,
                )
            )
        except RuntimeServiceError:
            writeback_result = None
        if writeback_result is not None:
            store.save_decision(
                build_config_writeback_decision(
                    task_run,
                    scene_requirement,
                    source_proposal,
                    writeback_result,
                    input_ref=None,
                )
            )
            if writeback_result.status != ConfigWritebackStatus.SUCCESS:
                question = _build_writeback_failed_question(question, writeback_result)

    return SourceInfraDiscoveryResult(question=question, writeback_result=writeback_result)
