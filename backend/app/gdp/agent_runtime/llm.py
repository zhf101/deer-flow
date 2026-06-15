"""兼容旧 LLM 选择建议导入路径，真实实现位于 workflows.selection_ai。"""

from __future__ import annotations

from .workflows.selection_ai import suggest_scene_rerank

__all__ = ["suggest_scene_rerank"]

