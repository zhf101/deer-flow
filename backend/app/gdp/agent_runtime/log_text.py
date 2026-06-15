"""兼容旧日志展示工具导入路径，真实实现位于 support.log_text。"""

from __future__ import annotations

from .support.log_text import (
    describe_bool,
    describe_code,
    describe_content,
    describe_fact_name,
    describe_fact_value,
    describe_facts,
    describe_name_list,
    describe_optional,
    describe_variables,
)

__all__ = [
    "describe_bool",
    "describe_code",
    "describe_content",
    "describe_fact_name",
    "describe_fact_value",
    "describe_facts",
    "describe_name_list",
    "describe_optional",
    "describe_variables",
]

