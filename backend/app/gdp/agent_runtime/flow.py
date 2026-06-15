"""兼容旧执行计划工厂导入路径，真实实现位于 domain.factories。"""

from __future__ import annotations

from .domain.factories import (
    create_input_variables,
    create_single_step,
    create_task_run,
    make_scene_action,
)

__all__ = [
    "create_input_variables",
    "create_single_step",
    "create_task_run",
    "make_scene_action",
]

