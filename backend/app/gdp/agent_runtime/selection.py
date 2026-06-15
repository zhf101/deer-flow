"""兼容旧场景选择策略导入路径，真实实现位于 workflows.selection_policy。"""

from __future__ import annotations

from .workflows.selection_policy import (
    AUTO_SELECT_THRESHOLD,
    SelectionOutcome,
    apply_selection,
    blacklist_scene,
    decide_selection,
    ensure_requirement_matches_scene,
    ensure_selection_consistency,
)

__all__ = [
    "AUTO_SELECT_THRESHOLD",
    "SelectionOutcome",
    "apply_selection",
    "blacklist_scene",
    "decide_selection",
    "ensure_requirement_matches_scene",
    "ensure_selection_consistency",
]

