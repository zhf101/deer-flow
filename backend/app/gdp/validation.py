"""Static validation for GDP scene configuration.

The validator only checks configuration structure. It never calls HTTP,
executes SQL, evaluates JSONPath against live payloads, or resolves secrets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.gdp.models import (
    ConfigStatus,
    SceneDefinition,
    SqlTemplateConfig,
    StepDefinition,
    StepType,
    ValidationIssue,
    ValidationResult,
)

SCENE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]{1,127}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VAR_REF_RE = re.compile(r"\$\{([^}]+)}")
ALLOWED_REF_ROOTS = {"input", "steps", "vars", "system", "env", "auth", "error"}


def validate_draft(scene: SceneDefinition) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _validate_basic_scene(scene, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def validate_publish(
    scene: SceneDefinition,
    *,
    sql_templates_by_code: dict[str, SqlTemplateConfig] | None = None,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _validate_basic_scene(scene, issues)
    _validate_env_input(scene, issues)
    _validate_step_order_and_refs(scene, issues)
    _validate_step_configs(scene, issues, sql_templates_by_code or {})
    _validate_result_mapping(scene, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def _has_errors(issues: Iterable[ValidationIssue]) -> bool:
    return any(issue.level == "ERROR" for issue in issues)


def _add(issues: list[ValidationIssue], field: str, message: str) -> None:
    issues.append(ValidationIssue(field=field, message=message))


def _validate_basic_scene(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
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
    env_field = next((field for field in scene.inputSchema if field.name == scene.environmentField), None)
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
        if key in {"stepId", "stepName", "type", "enabled", "dependsOn", "description", "position"}:
            continue
        yield f"steps.{step.stepId}.{key}", value


def _validate_value_refs(value, issues: list[ValidationIssue], field_path: str, seen_steps: set[str]) -> None:
    if isinstance(value, str):
        for ref in VAR_REF_RE.findall(value):
            _validate_ref(ref, issues, field_path, seen_steps)
    elif isinstance(value, dict):
        for nested_key, nested_value in value.items():
            _validate_value_refs(nested_value, issues, f"{field_path}.{nested_key}", seen_steps)
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            _validate_value_refs(nested_value, issues, f"{field_path}[{index}]", seen_steps)


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


def _validate_step_configs(
    scene: SceneDefinition,
    issues: list[ValidationIssue],
    sql_templates_by_code: dict[str, SqlTemplateConfig],
) -> None:
    for index, step in enumerate(scene.steps):
        prefix = f"steps[{index}]"
        if step.type in (StepType.HTTP, StepType.AUTH_HTTP):
            _validate_http_step(step, prefix, issues)
        elif step.type == StepType.SQL:
            _validate_sql_step(step, prefix, issues, sql_templates_by_code)
        elif step.type == StepType.ASSERT and not step.assertions:
            _add(issues, f"{prefix}.assertions", "ASSERT step must contain at least one assertion")
        elif step.type == StepType.TRANSFORM and not step.assignments:
            _add(issues, f"{prefix}.assignments", "TRANSFORM step must contain at least one assignment")


def _validate_http_step(step: StepDefinition, prefix: str, issues: list[ValidationIssue]) -> None:
    if step.method is None:
        _add(issues, f"{prefix}.method", "HTTP step method is required")
    if not step.url:
        _add(issues, f"{prefix}.url", "HTTP step url is required")
    if step.responseHandling is None:
        _add(issues, f"{prefix}.responseHandling", "HTTP responseHandling is required")
        return
    if not step.responseHandling.statusCode.success:
        _add(issues, f"{prefix}.responseHandling.statusCode.success", "at least one success status code is required")
    if not step.responseHandling.businessSuccess.allOf:
        _add(issues, f"{prefix}.responseHandling.businessSuccess.allOf", "at least one business success rule is required")
    if step.retryPolicy and step.retryPolicy.enabled and not step.retryPolicy.retryOn:
        _add(issues, f"{prefix}.retryPolicy.retryOn", "enabled retryPolicy must define retryOn")
    if step.type == StepType.AUTH_HTTP and step.authMapping is None:
        _add(issues, f"{prefix}.authMapping", "AUTH_HTTP step authMapping is required")


def _validate_sql_step(
    step: StepDefinition,
    prefix: str,
    issues: list[ValidationIssue],
    sql_templates_by_code: dict[str, SqlTemplateConfig],
) -> None:
    if not step.datasource:
        _add(issues, f"{prefix}.datasource", "SQL step datasource is required")
    if not step.sqlTemplateCode:
        _add(issues, f"{prefix}.sqlTemplateCode", "SQL step sqlTemplateCode is required")
        return

    template = sql_templates_by_code.get(step.sqlTemplateCode)
    if template is None:
        _add(issues, f"{prefix}.sqlTemplateCode", f"SQL template not found: {step.sqlTemplateCode}")
        return
    if template.status != ConfigStatus.ENABLED:
        _add(issues, f"{prefix}.sqlTemplateCode", f"SQL template disabled: {step.sqlTemplateCode}")
    required_params = {param.name for param in template.parameters if param.required}
    missing_params = sorted(required_params - set(step.paramMapping.keys()))
    if missing_params:
        _add(issues, f"{prefix}.paramMapping", f"missing SQL template parameters: {', '.join(missing_params)}")


def _validate_result_mapping(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    seen_steps = {step.stepId for step in scene.steps}
    _validate_value_refs(scene.resultMapping, issues, "resultMapping", seen_steps)
