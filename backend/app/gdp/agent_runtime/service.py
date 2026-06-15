"""兼容旧应用服务导入路径，真实实现位于 application.service。"""

from __future__ import annotations

from .application.service import RuntimePrincipal, RuntimeService

__all__ = ["RuntimePrincipal", "RuntimeService"]

