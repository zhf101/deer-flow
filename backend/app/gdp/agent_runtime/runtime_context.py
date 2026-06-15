"""兼容旧运行上下文导入路径，真实实现位于 support.runtime_context。"""

from __future__ import annotations

from .support.runtime_context import (
    RuntimeNodeCallable,
    RuntimeState,
    build_gdp_runtime_context,
    metadata_payload,
    runtime_binding,
    wrap_gdp_runtime_context,
)

__all__ = [
    "RuntimeNodeCallable",
    "RuntimeState",
    "build_gdp_runtime_context",
    "metadata_payload",
    "runtime_binding",
    "wrap_gdp_runtime_context",
]

