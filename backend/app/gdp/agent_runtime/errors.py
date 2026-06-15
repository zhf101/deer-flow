"""兼容旧错误模块导入路径，真实实现位于 support.errors。"""

from __future__ import annotations

from .support.errors import (
    RuntimeConflictError,
    RuntimeDependencyError,
    RuntimeForbiddenError,
    RuntimeNotFoundError,
    RuntimePersistenceError,
    RuntimeServiceError,
    RuntimeValidationError,
)

__all__ = [
    "RuntimeConflictError",
    "RuntimeDependencyError",
    "RuntimeForbiddenError",
    "RuntimeNotFoundError",
    "RuntimePersistenceError",
    "RuntimeServiceError",
    "RuntimeValidationError",
]

