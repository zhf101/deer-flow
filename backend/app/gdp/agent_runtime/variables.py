"""场景输出变量规则。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .models import Action, Evidence, Observation, PlanStep, TaskRun, Variable, VariableProvenance, VariableSource
from .store import Store


class SceneOutputBinding(BaseModel):
    """场景输出变量抽取规则。

    业务目标：描述成功步骤如何从场景执行结果中抽取可供后续步骤消费的任务变量，
    并保留语义类型和敏感标记，支撑前端安全展示和后续 provenance 追踪。
    """

    output_path: str = Field(description="输出路径，如 finalOutput.order_id。")
    variable_name: str = Field(description="写入变量名，如 order_id。")
    semantic_type: str = Field(description="变量语义类型，如 ORDER_ID。")
    sensitive: bool = Field(default=False, description="变量是否敏感，敏感变量展示时必须脱敏。")
    required: bool = Field(default=True, description="缺失时是否让当前步骤失败。")


def extract_scene_output_variables(
    task_run: TaskRun,
    step: PlanStep,
    action: Action,
    evidence: Evidence,
    observation: Observation,
    output_bindings: list[SceneOutputBinding],
    store: Store,
) -> list[Variable]:
    """从成功步骤输出中抽取变量并写入变量账本。"""

    variables: list[Variable] = []
    for binding in output_bindings:
        found, value = _read_output_path(observation.preview, binding.output_path)
        if not found:
            if binding.required:
                raise ValueError(f"缺少必需输出变量：{binding.variable_name}")
            continue

        if not _has_evidence_support(evidence, binding):
            if not binding.required:
                continue
            raise ValueError(f"缺少证据支撑：{binding.variable_name}")

        variable_id = _gen_id("var")
        value_ref = f"ref:vars/{variable_id}"
        variable = Variable(
            variable_id=variable_id,
            task_run_id=task_run.task_run_id,
            name=binding.variable_name,
            semantic_type=binding.semantic_type,
            value_ref=value_ref,
            value_preview="***" if binding.sensitive else str(value)[:64],
            sensitive=binding.sensitive,
            provenance=VariableProvenance(
                source_type=VariableSource.SCENE_OUTPUT,
                source_id=step.step_id,
                action_id=action.action_id,
                evidence_id=evidence.evidence_id,
            ),
            created_at=datetime.now(UTC),
        )
        if variable.variable_id not in step.produces:
            step.produces.append(variable.variable_id)
        store.save_payload(task_run.task_run_id, value_ref, value)
        store.save_variable(variable)
        store.save_step(step)
        variables.append(variable)

    return variables


def _read_output_path(preview: dict[str, Any], output_path: str) -> tuple[bool, Any]:
    current: Any = preview
    for part in output_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _has_evidence_support(evidence: Evidence, binding: SceneOutputBinding) -> bool:
    suffix = binding.output_path.rsplit(".", 1)[-1]
    subjects = {binding.output_path, binding.variable_name, suffix}
    return any(fact.passed and (fact.subject in subjects or fact.subject.endswith(f".{suffix}")) for fact in evidence.facts)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
