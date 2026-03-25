from __future__ import annotations

from typing import Any


def build_value_context(
    user_inputs: dict[str, Any] | None,
    step_outputs: dict[str, Any] | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造运行时取值上下文。

    V1 先约定 3 类主要命名空间：
    - inputs / user_inputs: 用户输入
    - steps / step_outputs: 已成功步骤输出
    - extra: 当前执行器附加的响应或结果上下文
    """

    context = {
        "inputs": user_inputs or {},
        "user_inputs": user_inputs or {},
        "steps": step_outputs or {},
        "step_outputs": step_outputs or {},
    }
    if extra:
        context.update(extra)
    return context


def render_template(template: Any, context: dict[str, Any]) -> Any:
    """按 datamakepool 的最小引用规则渲染模板值。"""

    if isinstance(template, dict):
        if "source" in template:
            resolved = _resolve_reference(template.get("source"), context)
            if resolved is None and "default" in template:
                return template.get("default")
            return resolved
        return {key: render_template(value, context) for key, value in template.items()}

    if isinstance(template, list):
        return [render_template(item, context) for item in template]

    if isinstance(template, str) and template.startswith("$"):
        return _resolve_reference(template, context)

    return template


def _resolve_reference(reference: Any, context: dict[str, Any]) -> Any:
    """解析 `$namespace.path` 形式的最小引用。"""

    if not isinstance(reference, str):
        return reference

    path = reference[1:]
    if path.startswith("."):
        path = path[1:]
    if not path:
        return None

    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
            continue
        return None

    return current
