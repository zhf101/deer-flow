"""兼容旧状态机导入路径，真实实现位于 domain.transitions。"""

from __future__ import annotations

from .domain.transitions import (
    IllegalTransition,
    transition_action,
    transition_requirement,
    transition_step,
    transition_task_run,
)

__all__ = [
    "IllegalTransition",
    "transition_action",
    "transition_requirement",
    "transition_step",
    "transition_task_run",
]

