"""MVP6 回退影响分析与变量污染标记。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import PlanStep, TaskRun, Variable, VariableSource, Verdict, VerdictType
from ..store import EntityNotFoundError, Store


class RollbackImpact(BaseModel):
    """一次失败步骤造成的回退影响摘要。"""

    failed_step_id: str = Field(description="失败步骤 ID。")
    tainted_variable_ids: list[str] = Field(default_factory=list, description="被标记污染的变量 ID。")
    producer_step_ids: list[str] = Field(default_factory=list, description="污染变量的来源步骤 ID。")
    affected_step_ids: list[str] = Field(default_factory=list, description="消费污染变量的步骤 ID。")


def mark_consumed_variables_tainted(
    *,
    task_run: TaskRun,
    failed_step: PlanStep,
    verdict: Verdict,
    store: Store,
) -> RollbackImpact:
    """失败步骤消费过的变量一律标记污染，供后续用户驱动回退和重搜使用。"""

    if verdict.verdict_type != VerdictType.FAILED:
        return RollbackImpact(failed_step_id=failed_step.step_id)

    tainted_variables: list[Variable] = []
    for variable_id in failed_step.consumes:
        try:
            variable = store.get_variable(variable_id)
        except EntityNotFoundError:
            continue
        if variable.task_run_id != task_run.task_run_id:
            continue
        if variable.provenance.source_type != VariableSource.SCENE_OUTPUT:
            continue
        if variable.provenance.source_id == failed_step.step_id:
            continue
        variable.tainted = True
        store.save_variable(variable)
        tainted_variables.append(variable)
        if variable.variable_id not in verdict.tainted_variable_ids:
            verdict.tainted_variable_ids.append(variable.variable_id)

    if tainted_variables:
        store.save_verdict(verdict)

    return RollbackImpact(
        failed_step_id=failed_step.step_id,
        tainted_variable_ids=[item.variable_id for item in tainted_variables],
        producer_step_ids=_unique([item.provenance.source_id for item in tainted_variables]),
        affected_step_ids=_unique(step_id for item in tainted_variables for step_id in item.consumed_by),
    )


def _unique(values) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
