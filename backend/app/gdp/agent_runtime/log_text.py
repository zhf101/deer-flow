"""GDP Agent Runtime 日志中文展示工具。"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

_SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "cookie",
    "authorization",
    "csrf",
    "session",
)

_CODE_TEXT: dict[str, str] = {
    "CREATED": "已创建",
    "RUNNING": "运行中",
    "WAITING_USER": "等待用户确认",
    "COMPLETED": "已完成",
    "FAILED": "已失败",
    "CANCELLED": "已取消",
    "PENDING": "待执行",
    "DONE": "已完成",
    "BLOCKED": "已阻塞",
    "PLANNED": "已计划",
    "WAITING_APPROVAL": "等待审批",
    "SUCCEEDED": "执行成功",
    "UNKNOWN_STATE": "结果未知",
    "SUCCESS": "成功",
    "PARTIAL": "部分完成",
    "SCENE_FAILED": "场景执行失败",
    "TIMEOUT": "请求超时",
    "CONNECTION_ERROR": "连接断开",
    "IDEMPOTENCY_CONFLICT": "幂等冲突",
    "NEED_USER": "需要用户补充",
    "EXECUTE_SCENE": "执行场景",
    "USER_INPUT": "用户输入",
    "SCENE_OUTPUT": "场景输出",
    "CONTEXT": "上下文",
    "EXISTS": "存在",
    "EQUALS": "等于",
    "IN": "属于",
    "NON_EMPTY": "非空",
}

_FACT_TEXT: dict[str, str] = {
    "attempt.status": "执行尝试状态",
    "scene.status": "场景执行状态",
    "scene.business_success": "场景业务判定",
    "order.order_id": "订单号",
    "order.pay_status": "订单支付状态",
    "attempt_result_unknown": "执行尝试结果未知",
}


def describe_code(value: Any) -> str:
    """把状态码、错误码或枚举值展示成中文说明。"""
    if value is None:
        return "无"
    raw = value.value if isinstance(value, Enum) else str(value)
    text = _CODE_TEXT.get(raw)
    if not text:
        return raw
    return f"{text}({raw})"


def describe_optional(value: Any) -> str:
    """日志中展示可空字段。"""
    if value is None or value == "":
        return "无"
    return describe_code(value)


def describe_bool(value: bool) -> str:
    """日志中展示布尔值。"""
    return "是" if value else "否"


def describe_fact_name(value: str) -> str:
    """展示事实字段名，保留原始字段码便于排查。"""
    text = _FACT_TEXT.get(value)
    if not text:
        return value
    return f"{text}({value})"


def describe_fact_value(value: Any) -> str:
    """展示事实期望值或实际值。"""
    if isinstance(value, bool):
        return f"{'是' if value else '否'}({value})"
    return describe_code(value)


def describe_name_list(values: list[str]) -> str:
    """展示字段名列表。"""
    if not values:
        return "无"
    return "[" + ", ".join(describe_fact_name(value) for value in values) + "]"


def describe_content(value: Any, *, max_chars: int = 1600) -> str:
    """展示结构化内容摘要，避免只打印数量或字段名。"""
    safe_value = _mask_sensitive(_to_jsonable(value))
    try:
        text = json.dumps(safe_value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(safe_value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...（已截断）"


def describe_variables(variables: list[Any]) -> str:
    """展示变量关键内容。"""
    rows: list[dict[str, Any]] = []
    for variable in variables:
        provenance = getattr(variable, "provenance", None)
        rows.append(
            {
                "变量名": getattr(variable, "name", None),
                "语义类型": getattr(variable, "semantic_type", None),
                "值预览": getattr(variable, "value_preview", None),
                "是否敏感": describe_bool(bool(getattr(variable, "sensitive", False))),
                "来源类型": describe_code(getattr(provenance, "source_type", None)),
                "来源对象": getattr(provenance, "source_id", None),
            }
        )
    return describe_content(rows)


def describe_facts(facts: list[Any]) -> str:
    """展示判定事实关键内容。"""
    rows: list[dict[str, Any]] = []
    for fact in facts:
        rows.append(
            {
                "事实": describe_fact_name(str(getattr(fact, "subject", ""))),
                "判定方式": describe_code(getattr(fact, "predicate", None)),
                "期望": describe_fact_value(getattr(fact, "expected", None)),
                "实际": describe_fact_value(getattr(fact, "actual", None)),
                "是否通过": describe_bool(bool(getattr(fact, "passed", False))),
                "来源观察": getattr(fact, "source_observation_id", None),
            }
        )
    return describe_content(rows)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_jsonable(item) for item in value]
    return value


def _mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                masked[key_text] = "***"
            else:
                masked[key_text] = _mask_sensitive(item)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(keyword in lower for keyword in _SENSITIVE_KEYWORDS)
