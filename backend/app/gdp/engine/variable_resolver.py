"""GDP 变量解析器——将配置中的 ``${...}`` 引用替换为运行时的实际值。

支持的变量引用路径：
- ``${input.xxx}``                        → 用户输入参数
- ``${steps.stepId.outputs.xxx}``         → 前序步骤的输出
- ``${vars.xxx}``                         → TRANSFORM 写入的变量
- ``${system.now}`` / ``${system.uuid}``  → 系统变量
- ``${env.services.code.baseUrl}``        → 服务端点配置
- ``${error.xxx}``                        → 错误信息（保留扩展）

关键行为：
- 当整个字符串就是一个变量引用时（fullmatch），返回原始类型（int/bool/None）
- 当字符串混合了文字和引用时，所有值转为字符串拼接
"""

from __future__ import annotations

import re
from typing import Any

from app.gdp.engine.context import ExecutionContext

# 匹配 ${xxx} 变量引用的正则
_VAR_RE = re.compile(r"\$\{([^}]+)}")


def resolve_value(value: Any, ctx: ExecutionContext) -> Any:
    """递归解析变量引用。字符串做替换，dict/list 递归处理，其他类型原样返回。"""
    if isinstance(value, str):
        return _resolve_string(value, ctx)
    if isinstance(value, dict):
        return {k: resolve_value(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, ctx) for item in value]
    return value


def _resolve_string(s: str, ctx: ExecutionContext) -> Any:
    """替换字符串中的变量引用。

    如果整个字符串就是一个 ``${...}`` 引用（fullmatch），返回原始类型值；
    否则将各引用替换为字符串后拼接。
    """
    # 整串匹配——保留原始类型
    match = _VAR_RE.fullmatch(s)
    if match:
        return _lookup(match.group(1), ctx)

    # 混合拼接——所有值转 str
    def replacer(m: re.Match) -> str:
        val = _lookup(m.group(1), ctx)
        return str(val) if val is not None else ""

    return _VAR_RE.sub(replacer, s)


def _lookup(ref: str, ctx: ExecutionContext) -> Any:
    """根据引用路径从上下文中查找值。

    路径格式: root.key1.key2...
    root 可选值: input / steps / vars / system / env / error
    """
    parts = ref.split(".")
    if not parts:
        return None

    root = parts[0]

    if root == "input":
        # ${input.fieldName} 或 ${input.obj.subField}
        return _nested_get(ctx.inputs, parts[1:])

    if root == "steps":
        # ${steps.stepId.outputs.fieldName}
        if len(parts) < 2:
            return None
        step_id = parts[1]
        if len(parts) >= 3 and parts[2] == "outputs":
            return _nested_get(ctx.step_outputs.get(step_id, {}), parts[3:])
        # ${steps.stepId.result.xxx} 等直接访问原始响应
        if len(parts) >= 3 and parts[2] == "result":
            return _nested_get(ctx.step_raw.get(step_id, {}), parts[3:])
        return ctx.step_outputs.get(step_id)

    if root == "vars":
        # ${vars.varName}
        return _nested_get(ctx.vars, parts[1:])

    if root == "system":
        # ${system.now} / ${system.uuid} / ${system.timestamp}
        return ctx.get_system_var(parts[1] if len(parts) > 1 else "")

    if root == "env":
        # ${env.services.serviceCode.baseUrl}
        if len(parts) >= 4 and parts[1] == "services" and parts[3] == "baseUrl":
            return ctx.service_endpoints.get(parts[2], "")
        # ${env.datasources.dsCode} — 返回数据源编码（由执行器后续解析）
        if len(parts) >= 3 and parts[1] == "datasources":
            ds_code = parts[2]
            ds_config = ctx.datasources.get(ds_code)
            if ds_config is not None:
                return ds_config
            return ds_code
        return ""

    if root == "error":
        # 保留扩展，暂不实现
        return None

    return None


def _nested_get(obj: Any, keys: list[str]) -> Any:
    """沿路径逐层取值，任一层缺失返回 None。"""
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k)
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(k)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj
