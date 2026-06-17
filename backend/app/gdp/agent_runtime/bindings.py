"""步骤入参绑定规则。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import PlanStep, StepEdge, TaskRun, Variable
from .store import EntityNotFoundError, Store


class StepInputBinding(BaseModel):
    """步骤入参绑定规则。

    业务目标：描述当前业务步骤执行场景时，每个入参应该从用户输入、任务变量
    或固定值中取值，避免跨步骤数据传递退化成临时字典拼接。
    """

    input_name: str = Field(description="目标场景入参名。")
    source: Literal["USER_INPUT", "VARIABLE", "CONST"] = Field(description="入参来源：用户输入、任务变量或固定值。")
    source_name: str | None = Field(default=None, description="来源名称，如用户输入字段名、变量名或常量名。")
    required: bool = Field(default=True, description="缺失时是否阻断当前步骤执行。")


class StepInputResolution(BaseModel):
    """步骤入参解析结果。"""

    inputs: dict[str, object] = Field(description="可传给场景执行的完整入参。")
    consumed_variable_ids: list[str] = Field(default_factory=list, description="本次绑定消费的变量 ID。")
    missing_inputs: list[str] = Field(default_factory=list, description="缺失的用户输入名。")
    missing_variables: list[str] = Field(default_factory=list, description="缺失或不可用的计划变量名。")


def resolve_step_inputs(
    task_run: TaskRun,
    step: PlanStep,
    bindings: list[StepInputBinding],
    request_inputs: dict[str, object],
    store: Store,
) -> StepInputResolution:
    """根据用户输入、常量和任务变量解析当前步骤入参。"""

    inputs: dict[str, object] = {}
    consumed_variable_ids: list[str] = []
    missing_inputs: list[str] = []
    missing_variables: list[str] = []

    for binding in bindings:
        source_name = binding.source_name or binding.input_name
        if binding.source == "USER_INPUT":
            if source_name in request_inputs and not _is_blank(request_inputs[source_name]):
                inputs[binding.input_name] = request_inputs[source_name]
            elif binding.required:
                missing_inputs.append(source_name)
            continue

        if binding.source == "CONST":
            if source_name is not None:
                inputs[binding.input_name] = source_name
            elif binding.required:
                missing_inputs.append(binding.input_name)
            continue

        variable = _find_variable(task_run.task_run_id, source_name, store)
        if variable is None or variable.tainted:
            if binding.required:
                missing_variables.append(source_name)
            continue

        try:
            inputs[binding.input_name] = store.get_payload(task_run.task_run_id, variable.value_ref)
        except EntityNotFoundError:
            if binding.required:
                missing_variables.append(source_name)
            continue

        consumed_variable_ids.append(variable.variable_id)
        _record_variable_consumption(task_run, step, variable, store)

    return StepInputResolution(
        inputs=inputs,
        consumed_variable_ids=consumed_variable_ids,
        missing_inputs=missing_inputs,
        missing_variables=missing_variables,
    )


def _find_variable(task_run_id: str, name: str, store: Store) -> Variable | None:
    for variable in store.list_variables(task_run_id):
        if variable.name == name:
            return variable
    return None


def _record_variable_consumption(task_run: TaskRun, step: PlanStep, variable: Variable, store: Store) -> None:
    if variable.variable_id not in step.consumes:
        step.consumes.append(variable.variable_id)
    if step.step_id not in variable.consumed_by:
        variable.consumed_by.append(step.step_id)

    for edge in task_run.step_edges:
        if _edge_matches_variable(edge, step, variable) and variable.variable_id not in edge.variable_ids:
            edge.variable_ids.append(variable.variable_id)

    store.save_task_run(task_run)
    store.save_step(step)
    store.save_variable(variable)


def _edge_matches_variable(edge: StepEdge, step: PlanStep, variable: Variable) -> bool:
    return edge.to_step_id == step.step_id and edge.from_step_id == variable.provenance.source_id


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""
