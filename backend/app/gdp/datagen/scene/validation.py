"""造数场景静态校验（引用模式）。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.gdp.datagen.httpsource.models import HttpSourceConfig
from app.gdp.datagen.scene.models import (
    SceneDefinition,
    StepDefinition,
    ValidationIssue,
    ValidationResult,
)
from app.gdp.datagen.sqlsource.models import SqlSourceConfig
from app.gdp.models import ConfigStatus, StepType

SCENE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]{1,127}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VAR_REF_RE = re.compile(r"\$\{([^}]+)}")
ALLOWED_REF_ROOTS = {"input", "steps", "vars", "system", "env", "error"}


def validate_draft(scene: SceneDefinition) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _validate_basic(scene, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def validate_publish(
    scene: SceneDefinition,
    *,
    http_sources_by_code: dict[str, HttpSourceConfig] | None = None,
    sql_sources_by_code: dict[str, SqlSourceConfig] | None = None,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _validate_basic(scene, issues)
    _validate_env_input(scene, issues)
    _validate_step_order_and_refs(scene, issues)
    _validate_step_references(
        scene, issues,
        http_sources_by_code or {},
        sql_sources_by_code or {},
    )
    _validate_result_mapping(scene, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def _has_errors(issues: Iterable[ValidationIssue]) -> bool:
    return any(issue.level == "ERROR" for issue in issues)


def _add(issues: list[ValidationIssue], field: str, message: str) -> None:
    issues.append(ValidationIssue(field=field, message=message))


def _validate_basic(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    if not SCENE_CODE_RE.match(scene.sceneCode):
        _add(issues, "sceneCode", "sceneCode must start with a letter and only contain letters, numbers, _, :, -")
    if not scene.sceneName.strip():
        _add(issues, "sceneName", "sceneName cannot be empty")
    if scene.environmentField != "env":
        _add(issues, "environmentField", "environmentField V1 fixed to env")

    input_names: set[str] = set()
    for index, field in enumerate(scene.inputSchema):
        if field.name in input_names:
            _add(issues, f"inputSchema[{index}].name", f"duplicate input field: {field.name}")
        input_names.add(field.name)
        if not IDENTIFIER_RE.match(field.name):
            _add(issues, f"inputSchema[{index}].name", "input field name must be a valid identifier")

    step_ids: set[str] = set()
    for index, step in enumerate(scene.steps):
        if step.stepId in step_ids:
            _add(issues, f"steps[{index}].stepId", f"duplicate stepId: {step.stepId}")
        step_ids.add(step.stepId)
        if not IDENTIFIER_RE.match(step.stepId):
            _add(issues, f"steps[{index}].stepId", "stepId must be a valid identifier")


def _validate_env_input(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    env_field = next((f for f in scene.inputSchema if f.name == scene.environmentField), None)
    if env_field is None:
        _add(issues, "inputSchema", "env input field is required before publish")
        return
    if not env_field.required:
        _add(issues, "inputSchema.env.required", "env input field must be required before publish")


def _validate_step_order_and_refs(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    seen_steps: set[str] = set()
    all_step_ids = {step.stepId for step in scene.steps}
    for index, step in enumerate(scene.steps):
        for dep in step.dependsOn:
            if dep not in all_step_ids:
                _add(issues, f"steps[{index}].dependsOn", f"dependsOn references missing step: {dep}")
            elif dep not in seen_steps:
                _add(issues, f"steps[{index}].dependsOn", f"dependsOn must reference previous steps only: {dep}")

        for field_path, value in _iter_step_values(step):
            _validate_value_refs(value, issues, field_path, seen_steps)

        seen_steps.add(step.stepId)


def _iter_step_values(step: StepDefinition):
    data = step.model_dump(mode="python")
    for key, value in data.items():
        if key in {"stepId", "stepName", "type", "enabled", "dependsOn", "description", "position", "httpSourceCode", "sqlSourceCode"}:
            continue
        yield f"steps.{step.stepId}.{key}", value


def _validate_value_refs(value, issues: list[ValidationIssue], field_path: str, seen_steps: set[str]) -> None:
    if isinstance(value, str):
        for ref in VAR_REF_RE.findall(value):
            _validate_ref(ref, issues, field_path, seen_steps)
    elif isinstance(value, dict):
        for k, v in value.items():
            _validate_value_refs(v, issues, f"{field_path}.{k}", seen_steps)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _validate_value_refs(v, issues, f"{field_path}[{i}]", seen_steps)


def _validate_ref(ref: str, issues: list[ValidationIssue], field_path: str, seen_steps: set[str]) -> None:
    parts = ref.split(".")
    if not parts or parts[0] not in ALLOWED_REF_ROOTS:
        _add(issues, field_path, f"unsupported variable reference: ${{{ref}}}")
        return
    if parts[0] == "steps":
        if len(parts) < 2:
            _add(issues, field_path, f"step variable reference must include stepId: ${{{ref}}}")
            return
        if parts[1] not in seen_steps:
            _add(issues, field_path, f"step reference must point to a previous step: ${{{ref}}}")


def _validate_step_references(
    scene: SceneDefinition,
    issues: list[ValidationIssue],
    http_sources_by_code: dict[str, HttpSourceConfig],
    sql_sources_by_code: dict[str, SqlSourceConfig],
) -> None:
    """校验步骤引用的 httpsource/sqlsource 是否存在且已启用。"""
    for index, step in enumerate(scene.steps):
        prefix = f"steps[{index}]"
        if step.type == StepType.HTTP:
            if not step.httpSourceCode:
                _add(issues, f"{prefix}.httpSourceCode", "HTTP step httpSourceCode is required")
            else:
                source = http_sources_by_code.get(step.httpSourceCode)
                if source is None:
                    _add(issues, f"{prefix}.httpSourceCode", f"HTTP source not found: {step.httpSourceCode}")
                elif source.status != ConfigStatus.ENABLED:
                    _add(issues, f"{prefix}.httpSourceCode", f"HTTP source disabled: {step.httpSourceCode}")
        elif step.type == StepType.SQL:
            if not step.sqlSourceCode:
                _add(issues, f"{prefix}.sqlSourceCode", "SQL step sqlSourceCode is required")
            else:
                source = sql_sources_by_code.get(step.sqlSourceCode)
                if source is None:
                    _add(issues, f"{prefix}.sqlSourceCode", f"SQL source not found: {step.sqlSourceCode}")
                elif source.status != ConfigStatus.ENABLED:
                    _add(issues, f"{prefix}.sqlSourceCode", f"SQL source disabled: {step.sqlSourceCode}")
                else:
                    # 校验必填参数映射
                    required_params = {p.name for p in source.parameters if p.required}
                    missing = sorted(required_params - set(step.sqlParamMapping.keys()))
                    if missing:
                        _add(issues, f"{prefix}.sqlParamMapping", f"missing SQL source parameters: {', '.join(missing)}")
        elif step.type == StepType.ASSERT and not step.assertions:
            _add(issues, f"{prefix}.assertions", "ASSERT step must contain at least one assertion")
        elif step.type == StepType.TRANSFORM and not step.assignments:
            _add(issues, f"{prefix}.assignments", "TRANSFORM step must contain at least one assignment")


def _validate_result_mapping(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    seen_steps = {step.stepId for step in scene.steps}
    _validate_value_refs(scene.resultMapping, issues, "resultMapping", seen_steps)
