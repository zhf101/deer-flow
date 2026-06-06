"""造数任务静态校验。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.gdp.datagen.scene.models import SceneDefinition
from app.gdp.datagen.task.models import (
    TaskDefinition,
    TaskStepDefinition,
    TaskValidationIssue,
    TaskValidationResult,
)

TASK_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]{1,127}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VAR_REF_RE = re.compile(r"\$\{([^}]+)}")
ALLOWED_REF_ROOTS = {"input", "steps", "vars", "system", "env", "error"}


def validate_task_draft(task: TaskDefinition) -> TaskValidationResult:
    issues: list[TaskValidationIssue] = []
    _validate_basic(task, issues)
    return TaskValidationResult(valid=not _has_errors(issues), issues=issues)


def validate_task_publish(
    task: TaskDefinition,
    *,
    scenes_by_code: dict[str, SceneDefinition] | None = None,
) -> TaskValidationResult:
    issues: list[TaskValidationIssue] = []
    _validate_basic(task, issues)
    _validate_env_input(task, issues)
    _validate_step_order(task, issues)
    _validate_scene_references(task, issues, scenes_by_code or {})
    _validate_result_mapping(task, issues)
    return TaskValidationResult(valid=not _has_errors(issues), issues=issues)


def _has_errors(issues: Iterable[TaskValidationIssue]) -> bool:
    return any(i.level == "ERROR" for i in issues)


def _add(issues: list[TaskValidationIssue], field: str, message: str) -> None:
    issues.append(TaskValidationIssue(field=field, message=message))


def _validate_basic(task: TaskDefinition, issues: list[TaskValidationIssue]) -> None:
    if not TASK_CODE_RE.match(task.taskCode):
        _add(issues, "taskCode", "taskCode must start with a letter")
    if not task.taskName.strip():
        _add(issues, "taskName", "taskName cannot be empty")

    step_ids: set[str] = set()
    for index, step in enumerate(task.steps):
        if step.stepId in step_ids:
            _add(issues, f"steps[{index}].stepId", f"duplicate stepId: {step.stepId}")
        step_ids.add(step.stepId)
        if not IDENTIFIER_RE.match(step.stepId):
            _add(issues, f"steps[{index}].stepId", "stepId must be a valid identifier")


def _validate_env_input(task: TaskDefinition, issues: list[TaskValidationIssue]) -> None:
    env_field = next((f for f in task.inputSchema if f.name == task.environmentField), None)
    if env_field is None:
        _add(issues, "inputSchema", "env input field is required before publish")
        return
    if not env_field.required:
        _add(issues, "inputSchema.env.required", "env input field must be required before publish")


def _validate_step_order(task: TaskDefinition, issues: list[TaskValidationIssue]) -> None:
    seen: set[str] = set()
    all_ids = {s.stepId for s in task.steps}
    for index, step in enumerate(task.steps):
        for dep in step.dependsOn:
            if dep not in all_ids:
                _add(issues, f"steps[{index}].dependsOn", f"dependsOn references missing step: {dep}")
            elif dep not in seen:
                _add(issues, f"steps[{index}].dependsOn", f"dependsOn must reference previous steps only: {dep}")
        seen.add(step.stepId)


def _validate_scene_references(
    task: TaskDefinition,
    issues: list[TaskValidationIssue],
    scenes_by_code: dict[str, SceneDefinition],
) -> None:
    for index, step in enumerate(task.steps):
        prefix = f"steps[{index}]"
        if not step.sceneCode:
            _add(issues, f"{prefix}.sceneCode", "sceneCode is required")
            continue
        scene = scenes_by_code.get(step.sceneCode)
        if scene is None:
            _add(issues, f"{prefix}.sceneCode", f"scene not found: {step.sceneCode}")


def _validate_result_mapping(task: TaskDefinition, issues: list[TaskValidationIssue]) -> None:
    seen_steps = {s.stepId for s in task.steps}
    _validate_value_refs(task.resultMapping, issues, "resultMapping", seen_steps)


def _validate_value_refs(value, issues: list[TaskValidationIssue], field_path: str, seen_steps: set[str]) -> None:
    if isinstance(value, str):
        for ref in VAR_REF_RE.findall(value):
            parts = ref.split(".")
            if not parts or parts[0] not in ALLOWED_REF_ROOTS:
                _add(issues, field_path, f"unsupported variable reference: ${{{ref}}}")
            elif parts[0] == "steps" and len(parts) >= 2 and parts[1] not in seen_steps:
                _add(issues, field_path, f"step reference must point to a declared step: ${{{ref}}}")
    elif isinstance(value, dict):
        for k, v in value.items():
            _validate_value_refs(v, issues, f"{field_path}.{k}", seen_steps)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _validate_value_refs(v, issues, f"{field_path}[{i}]", seen_steps)
