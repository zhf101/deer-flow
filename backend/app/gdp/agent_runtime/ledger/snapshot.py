"""任务账本持久化快照投影。"""

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
    TaskRun,
    Variable,
    Verdict,
)


def build_task_run_snapshot(
    *,
    task_run: TaskRun,
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
    payloads: dict[str, Any],
) -> dict[str, Any]:
    """把内存账本事实投影为数据库仓储可落库的完整快照。"""
    return {
        "task_run": task_run.model_dump(mode="json"),
        "steps": [item.model_dump(mode="json") for item in steps],
        "actions": [item.model_dump(mode="json") for item in actions],
        "attempts": [item.model_dump(mode="json") for item in attempts],
        "observations": [item.model_dump(mode="json") for item in observations],
        "evidences": [item.model_dump(mode="json") for item in evidences],
        "verdicts": [item.model_dump(mode="json") for item in verdicts],
        "variables": [item.model_dump(mode="json") for item in variables],
        "requirements": [item.model_dump(mode="json") for item in requirements],
        "proposals": [item.model_dump(mode="json") for item in proposals],
        "decisions": [item.model_dump(mode="json") for item in decisions],
        "approval_records": approval_records,
        "payloads": [
            {"task_run_id": task_run.task_run_id, "ref": ref, "payload": payload}
            for ref, payload in payloads.items()
        ],
    }
