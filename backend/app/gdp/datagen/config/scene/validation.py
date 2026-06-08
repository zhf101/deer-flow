"""场景定义校验。"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from sqlglot import parse_one

from app.gdp.datagen.config.common.models import SqlOperation, StepType
from app.gdp.datagen.config.scene.models import SceneDefinition, StepDefinition, ValidationIssue, ValidationResult
from app.gdp.datagen.config.sqlsource.parsers.common import normalize_sql, replace_parameters_with_question_marks

_STEP_OUTPUT_REF_RE = re.compile(r"\$\{steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)(?:[.\[].*?)?\}")


def validate_scene_draft(scene: SceneDefinition) -> ValidationResult:
    """草稿保存校验。

    草稿允许 HTTP/SQL 执行配置不完整，但必须保证步骤 ID、依赖关系等
    编排结构可被后端稳定保存。
    """

    issues: list[ValidationIssue] = []
    _validate_input_schema(scene, issues)
    _validate_step_ids(scene.steps, issues)
    _validate_dependencies(scene.steps, issues)
    _validate_no_template_references(scene.steps, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def validate_scene_publish(scene: SceneDefinition) -> ValidationResult:
    """发布校验。"""

    draft = validate_scene_draft(scene)
    issues = list(draft.issues)
    steps_by_id = {step.stepId: step for step in scene.steps}

    for index, step in enumerate(scene.steps):
        field = f"steps[{index}]"
        if not step.enabled:
            continue
        if step.type == StepType.HTTP:
            _validate_http_step(field, step, issues)
        elif step.type == StepType.SQL:
            _validate_sql_step(field, step, issues)
        _validate_step_variable_refs(field, step, steps_by_id, issues)

    _validate_result_mapping(scene.resultMapping, steps_by_id, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_input_schema(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    def _check_fields(fields: list, prefix: str) -> None:
        seen: set[str] = set()
        for index, field in enumerate(fields):
            name = field.name or ""
            if not name:
                issues.append(ValidationIssue(field=f"{prefix}[{index}].name", message="参数编码不能为空。"))
            elif not _IDENTIFIER_RE.match(name):
                issues.append(ValidationIssue(field=f"{prefix}[{index}].name", message=f"参数编码需为合法标识符：{name}。"))
            if name and name in seen:
                issues.append(ValidationIssue(field=f"{prefix}[{index}].name", message=f"重复参数编码：{name}。"))
            seen.add(name)
            if field.children:
                _check_fields(field.children, f"{prefix}[{index}].children")

    _check_fields(scene.inputSchema, "inputSchema")
    if scene.resultSchema:
        _check_fields(scene.resultSchema, "resultSchema")


def _validate_step_ids(steps: list[StepDefinition], issues: list[ValidationIssue]) -> None:
    seen: set[str] = set()
    for index, step in enumerate(steps):
        field = f"steps[{index}].stepId"
        if not step.stepId:
            issues.append(ValidationIssue(field=field, message="步骤 ID 不能为空。"))
            continue
        if step.stepId in seen:
            issues.append(ValidationIssue(field=field, message=f"步骤 ID 重复：{step.stepId}。"))
        seen.add(step.stepId)


def _validate_dependencies(steps: list[StepDefinition], issues: list[ValidationIssue]) -> None:
    step_ids = {step.stepId for step in steps}
    graph: dict[str, list[str]] = defaultdict(list)
    indegree = {step.stepId: 0 for step in steps}

    for index, step in enumerate(steps):
        for dep in step.dependsOn:
            field = f"steps[{index}].dependsOn"
            if dep == step.stepId:
                issues.append(ValidationIssue(field=field, message=f"步骤不能依赖自身：{step.stepId}。"))
                continue
            if dep not in step_ids:
                issues.append(ValidationIssue(field=field, message=f"依赖步骤不存在：{dep}。"))
                continue
            graph[dep].append(step.stepId)
            indegree[step.stepId] += 1

    queue = deque(step_id for step_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for nxt in graph[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if visited != len(indegree):
        issues.append(ValidationIssue(field="steps", message="步骤依赖存在环。"))


def _validate_no_template_references(steps: list[StepDefinition], issues: list[ValidationIssue]) -> None:
    for index, step in enumerate(steps):
        if step.templateRef is not None:
            issues.append(ValidationIssue(field=f"steps[{index}].templateRef", message="当前后端仅支持场景内自定义步骤，不支持模板来源引用。"))
        if step.httpSourceCode:
            issues.append(ValidationIssue(field=f"steps[{index}].httpSourceCode", message="当前后端仅支持场景内自定义 HTTP 步骤，不支持 HTTP 模板引用。"))
        if step.sqlSourceCode:
            issues.append(ValidationIssue(field=f"steps[{index}].sqlSourceCode", message="当前后端仅支持场景内自定义 SQL 步骤，不支持 SQL 模板引用。"))


def _validate_http_step(field: str, step: StepDefinition, issues: list[ValidationIssue]) -> None:
    if not step.sysCode:
        issues.append(ValidationIssue(field=f"{field}.sysCode", message="HTTP 步骤必须配置系统编码。"))
    if step.method is None:
        issues.append(ValidationIssue(field=f"{field}.method", message="HTTP 步骤必须配置请求方法。"))
    if not _step_path(step):
        issues.append(ValidationIssue(field=f"{field}.path", message="HTTP 步骤必须配置请求路径。"))


def _validate_sql_step(field: str, step: StepDefinition, issues: list[ValidationIssue]) -> None:
    if not step.sysCode:
        issues.append(ValidationIssue(field=f"{field}.sysCode", message="SQL 步骤必须配置系统编码。"))
    if not step.datasourceCode:
        issues.append(ValidationIssue(field=f"{field}.datasourceCode", message="SQL 步骤必须配置数据源编码。"))
    if step.operation is None:
        issues.append(ValidationIssue(field=f"{field}.operation", message="SQL 步骤必须配置操作类型。"))
    if not step.normalizedSql:
        issues.append(ValidationIssue(field=f"{field}.normalizedSql", message="SQL 步骤发布前必须先解析生成标准 SQL。"))
    _validate_sql_safety(field, step, issues)

    mapping = step.paramMapping or step.sqlParamMapping
    for param in step.parameters:
        if not _param_required(param):
            continue
        name = str(param.get("name") or "")
        if not name:
            continue
        has_default = param.get("defaultValue") is not None
        if name not in mapping and not has_default:
            issues.append(ValidationIssue(field=f"{field}.paramMapping.{name}", message=f"SQL 必填参数未映射：{name}。"))


def _validate_step_variable_refs(
    field: str,
    step: StepDefinition,
    steps_by_id: dict[str, StepDefinition],
    issues: list[ValidationIssue],
) -> None:
    allowed = _dependency_closure(step, steps_by_id)
    values: list[Any] = [
        step.requestMapping,
        step.httpParamMapping,
        step.paramMapping,
        step.sqlParamMapping,
        step.outputMapping,
        step.assertions,
        step.assignments,
    ]
    for ref_step_id, output_name in _extract_step_output_refs(values):
        _validate_output_ref(field, ref_step_id, output_name, steps_by_id, issues, allowed_step_ids=allowed)


def _validate_result_mapping(
    result_mapping: dict[str, str],
    steps_by_id: dict[str, StepDefinition],
    issues: list[ValidationIssue],
) -> None:
    for ref_step_id, output_name in _extract_step_output_refs(result_mapping):
        _validate_output_ref("resultMapping", ref_step_id, output_name, steps_by_id, issues)


def _dependency_closure(step: StepDefinition, steps_by_id: dict[str, StepDefinition]) -> set[str]:
    allowed: set[str] = set()
    stack = list(step.dependsOn)
    while stack:
        dep = stack.pop()
        if dep in allowed:
            continue
        allowed.add(dep)
        dep_step = steps_by_id.get(dep)
        if dep_step:
            stack.extend(dep_step.dependsOn)
    return allowed


def _extract_step_output_refs(value: Any) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    if isinstance(value, str):
        refs.update((step_id, output_name) for step_id, output_name in _STEP_OUTPUT_REF_RE.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            refs.update(_extract_step_output_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_extract_step_output_refs(item))
    elif hasattr(value, "model_dump"):
        refs.update(_extract_step_output_refs(value.model_dump(mode="json")))
    return refs


def _validate_output_ref(
    field: str,
    ref_step_id: str,
    output_name: str,
    steps_by_id: dict[str, StepDefinition],
    issues: list[ValidationIssue],
    *,
    allowed_step_ids: set[str] | None = None,
) -> None:
    # 发布后运行期只会解析已启用步骤真实产出的输出映射字段。
    ref_step = steps_by_id.get(ref_step_id)
    if ref_step is None:
        issues.append(ValidationIssue(field=field, message=f"变量引用的步骤不存在：{ref_step_id}。"))
        return
    if allowed_step_ids is not None and ref_step_id not in allowed_step_ids:
        issues.append(ValidationIssue(field=field, message=f"变量引用必须来自当前步骤依赖链：{ref_step_id}。"))
    if not ref_step.enabled:
        issues.append(ValidationIssue(field=field, message=f"变量不能引用禁用步骤的输出：{ref_step_id}。"))
        return
    if output_name not in ref_step.outputMapping:
        issues.append(ValidationIssue(field=field, message=f"变量引用的步骤输出不存在：{ref_step_id}.{output_name}。"))


def _validate_sql_safety(field: str, step: StepDefinition, issues: list[ValidationIssue]) -> None:
    if step.operation not in {SqlOperation.UPDATE, SqlOperation.DELETE}:
        return
    if not step.safety.requireWhere:
        return
    if not step.normalizedSql:
        return
    if not _has_top_level_where(step.normalizedSql):
        issues.append(ValidationIssue(field=f"{field}.normalizedSql", message="UPDATE/DELETE 步骤启用 requireWhere 时必须包含 WHERE 条件。"))


def _has_top_level_where(sql_text: str) -> bool:
    try:
        expression = parse_one(normalize_sql(replace_parameters_with_question_marks(sql_text)))
    except Exception:
        # SQL 无法解析时按不满足安全条件处理，避免绕过写操作保护。
        return False
    return expression.args.get("where") is not None


def _param_required(param: dict[str, Any]) -> bool:
    required = param.get("required")
    if required is None:
        return False
    return bool(required)


def _step_path(step: StepDefinition) -> str | None:
    return step.path or step.url


def _has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.level == "ERROR" for issue in issues)
