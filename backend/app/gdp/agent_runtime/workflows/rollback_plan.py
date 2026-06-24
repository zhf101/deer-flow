"""MVP6-B 用户驱动回退计划。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import TaskRun
from ..store import Store
from ..support.errors import RuntimeConflictError


class RollbackPlan(BaseModel):
    """回退计划安全投影。"""

    task_run_id: str = Field(description="任务运行 ID。")
    failed_step_id: str = Field(description="触发回退分析的失败步骤 ID。")
    rollback_candidate_step_ids: list[str] = Field(description="建议纳入用户确认的回退步骤 ID。")
    tainted_variable_ids: list[str] = Field(description="被污染变量 ID。")
    affected_step_ids: list[str] = Field(description="受污染变量或失败链路影响的步骤 ID。")
    reasons: list[str] = Field(description="生成该计划的原因说明。")
    safety_warnings: list[str] = Field(description="安全提示，说明不会自动重放副作用。")
    can_auto_replay: bool = Field(default=False, description="当前 MVP 是否允许自动重放。")


def build_rollback_plan(task_run: TaskRun, store: Store, failed_step_id: str | None = None) -> RollbackPlan:
    """根据失败账本生成用户驱动回退计划，不修改任何事实状态。"""

    timeline = store.get_timeline(task_run.task_run_id)
    steps = {item["step_id"]: item for item in timeline["steps"]}
    variables = {item["variable_id"]: item for item in timeline["variables"]}
    verdict = _select_failed_verdict(timeline["verdicts"], failed_step_id)
    failed_step = steps.get(verdict["step_id"])
    if failed_step is None:
        raise RuntimeConflictError("找不到可回退分析的失败步骤")

    tainted_ids = [item for item in verdict.get("tainted_variable_ids", []) if item in variables]
    if not tainted_ids:
        tainted_ids = [
            variable_id
            for variable_id in failed_step.get("consumes", [])
            if variable_id in variables and variables[variable_id].get("tainted") is True
        ]
    if not tainted_ids:
        raise RuntimeConflictError("当前任务没有污染变量证据，不能生成回退计划")

    producer_step_ids = _unique(
        str(variables[variable_id]["provenance"]["source_id"])
        for variable_id in tainted_ids
        if variables[variable_id].get("provenance", {}).get("source_id") in steps
    )
    affected_step_ids = _affected_steps(
        failed_step_id=failed_step["step_id"],
        tainted_variable_ids=tainted_ids,
        timeline=timeline,
    )
    rollback_candidate_step_ids = _unique([*producer_step_ids, failed_step["step_id"]])

    return RollbackPlan(
        task_run_id=task_run.task_run_id,
        failed_step_id=failed_step["step_id"],
        rollback_candidate_step_ids=rollback_candidate_step_ids,
        tainted_variable_ids=tainted_ids,
        affected_step_ids=affected_step_ids,
        reasons=[
            "失败步骤消费了已标记污染的上游变量。",
            "回退计划仅做影响分析，等待用户选择后续处置。",
        ],
        safety_warnings=[
            "不会自动重放有副作用动作。",
            "不会修改终态 Action、Attempt 或历史账本。",
        ],
        can_auto_replay=False,
    )


def _select_failed_verdict(verdicts: list[dict], failed_step_id: str | None) -> dict:
    candidates = [item for item in verdicts if item.get("verdict_type") == "FAILED"]
    if failed_step_id is not None:
        candidates = [item for item in candidates if item.get("step_id") == failed_step_id]
        if not candidates:
            raise RuntimeConflictError("指定步骤不是可回退分析的失败步骤")
    candidates_with_taint = [item for item in candidates if item.get("tainted_variable_ids")]
    if candidates_with_taint:
        return candidates_with_taint[-1]
    if candidates:
        return candidates[-1]
    raise RuntimeConflictError("当前任务没有失败步骤，不能生成回退计划")


def _affected_steps(*, failed_step_id: str, tainted_variable_ids: list[str], timeline: dict) -> list[str]:
    affected = [failed_step_id]
    for variable in timeline["variables"]:
        if variable["variable_id"] in tainted_variable_ids:
            affected.extend(variable.get("consumed_by", []))

    queue = list(affected)
    while queue:
        current = queue.pop(0)
        for edge in timeline["step_edges"]:
            if edge["from_step_id"] != current:
                continue
            to_step_id = edge["to_step_id"]
            if to_step_id not in affected:
                affected.append(to_step_id)
                queue.append(to_step_id)
    return _unique(affected)


def _unique(values) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
