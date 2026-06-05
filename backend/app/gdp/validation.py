"""GDP 场景静态校验——只检查配置结构完整性，不发起任何外部调用。

校验分为两个级别：
- ``validate_draft``：草稿态校验，仅检查基础结构（编码格式、字段非空、ID 唯一性等），
  用于场景新建/编辑时快速反馈；
- ``validate_publish``：发布态校验，在草稿态基础上额外检查环境变量、步骤依赖引用、
  HTTP/SQL 步骤配置完整性以及结果映射引用合法性，确保场景可被引擎安全执行。
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

# 场景编码正则：以字母开头，允许字母、数字、下划线、冒号、短横线，长度 2-128
SCENE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]{1,127}$")
# 合法标识符正则：用于 inputSchema 字段名和 stepId
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# 变量引用正则：匹配 ${xxx.yyy} 形式的占位符
VAR_REF_RE = re.compile(r"\$\{([^}]+)}")
# 允许的变量引用根节点集合
ALLOWED_REF_ROOTS = {"input", "steps", "vars", "system", "env", "error"}


def validate_draft(scene: SceneDefinition) -> ValidationResult:
    """草稿态校验：仅验证场景基础结构完整性。

    检查内容包括场景编码格式、名称非空、输入字段名和步骤 ID 的唯一性与合法性。
    适用于场景保存时的快速反馈，不要求场景达到可执行状态。
    """
    issues: list[ValidationIssue] = []
    _validate_basic_scene(scene, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def validate_publish(
    scene: SceneDefinition,
    *,
    sql_templates_by_code: dict[str, SqlTemplateConfig] | None = None,
) -> ValidationResult:
    """发布态校验：在基础校验之上执行全量检查。

    额外检查包括：
    1. 环境变量字段必须存在且标记为必填；
    2. 步骤依赖顺序合法（只能引用前序步骤）；
    3. HTTP/SQL/ASSERT/TRANSFORM 各类型步骤的配置完整性；
    4. SQL 步骤引用的模板必须存在且已启用、必填参数已映射；
    5. 结果映射中的变量引用指向合法步骤。
    """
    issues: list[ValidationIssue] = []
    _validate_basic_scene(scene, issues)
    _validate_env_input(scene, issues)
    _validate_step_order_and_refs(scene, issues)
    _validate_step_configs(scene, issues, sql_templates_by_code or {})
    _validate_result_mapping(scene, issues)
    return ValidationResult(valid=not _has_errors(issues), issues=issues)


def _has_errors(issues: Iterable[ValidationIssue]) -> bool:
    """判断校验问题列表中是否存在 ERROR 级别的问题。"""
    return any(issue.level == "ERROR" for issue in issues)


def _add(issues: list[ValidationIssue], field: str, message: str) -> None:
    """向问题列表追加一条 ERROR 级别的校验问题。"""
    issues.append(ValidationIssue(field=field, message=message))


def _validate_basic_scene(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    """校验场景基础结构：编码格式、名称非空、environmentField 固定值、
    输入字段名和步骤 ID 的唯一性与标识符合法性。"""
    if not SCENE_CODE_RE.match(scene.sceneCode):
        _add(issues, "sceneCode", "sceneCode must start with a letter and only contain letters, numbers, _, :, -")
    if not scene.sceneName.strip():
        _add(issues, "sceneName", "sceneName cannot be empty")
    # V1 版本中 environmentField 固定为 "env"，后续版本可能放开
    if scene.environmentField != "env":
        _add(issues, "environmentField", "environmentField V1 fixed to env")

    # 校验输入字段名唯一性 & 合法标识符
    input_names: set[str] = set()
    for index, field in enumerate(scene.inputSchema):
        if field.name in input_names:
            _add(issues, f"inputSchema[{index}].name", f"duplicate input field: {field.name}")
        input_names.add(field.name)
        if not IDENTIFIER_RE.match(field.name):
            _add(issues, f"inputSchema[{index}].name", "input field name must be a valid identifier")

    # 校验步骤 ID 唯一性 & 合法标识符
    step_ids: set[str] = set()
    for index, step in enumerate(scene.steps):
        if step.stepId in step_ids:
            _add(issues, f"steps[{index}].stepId", f"duplicate stepId: {step.stepId}")
        step_ids.add(step.stepId)
        if not IDENTIFIER_RE.match(step.stepId):
            _add(issues, f"steps[{index}].stepId", "stepId must be a valid identifier")


def _validate_env_input(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    """校验环境变量输入字段：发布前必须在 inputSchema 中声明 env 字段且标记为必填。

    这确保造数引擎在执行时一定能收到目标环境参数。
    """
    env_field = next((field for field in scene.inputSchema if field.name == scene.environmentField), None)
    if env_field is None:
        _add(issues, "inputSchema", "env input field is required before publish")
        return
    if not env_field.required:
        _add(issues, "inputSchema.env.required", "env input field must be required before publish")


def _validate_step_order_and_refs(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    """校验步骤执行顺序与依赖引用的合法性。

    规则：
    - dependsOn 引用的步骤必须存在且必须是当前步骤之前已声明的步骤（保证 DAG 无环）；
    - 步骤配置值中的 ``${steps.xxx}`` 引用也必须指向前序步骤。
    """
    seen_steps: set[str] = set()
    all_step_ids = {step.stepId for step in scene.steps}
    for index, step in enumerate(scene.steps):
        # 校验 dependsOn 依赖
        for dep in step.dependsOn:
            if dep not in all_step_ids:
                _add(issues, f"steps[{index}].dependsOn", f"dependsOn references missing step: {dep}")
            elif dep not in seen_steps:
                _add(issues, f"steps[{index}].dependsOn", f"dependsOn must reference previous steps only: {dep}")

        # 校验步骤配置值中的变量引用
        for field_path, value in _iter_step_values(step):
            _validate_value_refs(value, issues, field_path, seen_steps)

        seen_steps.add(step.stepId)


def _iter_step_values(step: StepDefinition):
    """遍历步骤中所有可包含变量引用的配置字段（排除元数据字段）。

    跳过 stepId、stepName、type 等纯描述性字段，只产出可能嵌入 ${...} 占位符的业务配置。
    """
    data = step.model_dump(mode="python")
    for key, value in data.items():
        if key in {"stepId", "stepName", "type", "enabled", "dependsOn", "description", "position"}:
            continue
        yield f"steps.{step.stepId}.{key}", value


def _validate_value_refs(value, issues: list[ValidationIssue], field_path: str, seen_steps: set[str]) -> None:
    """递归检查配置值中的 ${...} 变量引用是否合法。

    支持字符串、字典、列表的嵌套结构，逐层递归查找变量引用。
    """
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
    """校验单个变量引用的合法性。

    检查根节点是否在允许集合中，以及 steps 引用是否指向已声明的前序步骤。
    """
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
    """按步骤类型分发校验各步骤的业务配置完整性。

    - HTTP：校验 method、url、responseHandling 等必填项；
    - SQL：校验数据源、模板编码、必填参数映射；
    - ASSERT：校验断言列表非空；
    - TRANSFORM：校验赋值列表非空。
    """
    for index, step in enumerate(scene.steps):
        prefix = f"steps[{index}]"
        if step.type == StepType.HTTP:
            _validate_http_step(step, prefix, issues)
        elif step.type == StepType.SQL:
            _validate_sql_step(step, prefix, issues, sql_templates_by_code)
        elif step.type == StepType.ASSERT and not step.assertions:
            _add(issues, f"{prefix}.assertions", "ASSERT step must contain at least one assertion")
        elif step.type == StepType.TRANSFORM and not step.assignments:
            _add(issues, f"{prefix}.assignments", "TRANSFORM step must contain at least one assignment")


def _validate_http_step(step: StepDefinition, prefix: str, issues: list[ValidationIssue]) -> None:
    """校验 HTTP 类型步骤的必填配置。

    检查 method、url、responseHandling（含成功状态码和业务成功规则），
    以及重试策略。
    """
    if step.method is None:
        _add(issues, f"{prefix}.method", "HTTP step method is required")
    if not step.url:
        _add(issues, f"{prefix}.url", "HTTP step url is required")
    if step.responseHandling is None:
        _add(issues, f"{prefix}.responseHandling", "HTTP responseHandling is required")
        return
    # 响应处理：至少定义一个成功状态码
    if not step.responseHandling.statusCode.success:
        _add(issues, f"{prefix}.responseHandling.statusCode.success", "at least one success status code is required")
    # 响应处理：至少定义一条业务成功判定规则
    if not step.responseHandling.businessSuccess.allOf:
        _add(issues, f"{prefix}.responseHandling.businessSuccess.allOf", "at least one business success rule is required")
    # 重试策略启用时必须声明重试触发条件
    if step.retryPolicy and step.retryPolicy.enabled and not step.retryPolicy.retryOn:
        _add(issues, f"{prefix}.retryPolicy.retryOn", "enabled retryPolicy must define retryOn")


def _validate_sql_step(
    step: StepDefinition,
    prefix: str,
    issues: list[ValidationIssue],
    sql_templates_by_code: dict[str, SqlTemplateConfig],
) -> None:
    """校验 SQL 类型步骤的配置完整性。

    检查数据源和模板编码必填、模板是否存在且已启用、必填参数是否已全部映射。
    """
    if not step.datasource:
        _add(issues, f"{prefix}.datasource", "SQL step datasource is required")
    if not step.sqlTemplateCode:
        _add(issues, f"{prefix}.sqlTemplateCode", "SQL step sqlTemplateCode is required")
        return

    # 校验 SQL 模板是否存在
    template = sql_templates_by_code.get(step.sqlTemplateCode)
    if template is None:
        _add(issues, f"{prefix}.sqlTemplateCode", f"SQL template not found: {step.sqlTemplateCode}")
        return
    # 校验模板是否已启用
    if template.status != ConfigStatus.ENABLED:
        _add(issues, f"{prefix}.sqlTemplateCode", f"SQL template disabled: {step.sqlTemplateCode}")
    # 校验必填参数是否已在 paramMapping 中全部映射
    required_params = {param.name for param in template.parameters if param.required}
    missing_params = sorted(required_params - set(step.paramMapping.keys()))
    if missing_params:
        _add(issues, f"{prefix}.paramMapping", f"missing SQL template parameters: {', '.join(missing_params)}")


def _validate_result_mapping(scene: SceneDefinition, issues: list[ValidationIssue]) -> None:
    """校验结果映射中的变量引用合法性。

    结果映射在场景全部步骤执行完成后生效，因此可引用任意已声明步骤的输出。
    """
    seen_steps = {step.stepId for step in scene.steps}
    _validate_value_refs(scene.resultMapping, issues, "resultMapping", seen_steps)
