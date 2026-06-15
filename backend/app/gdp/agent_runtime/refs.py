"""兼容旧账本引用工具导入路径，真实实现位于 ledger.refs。"""

from __future__ import annotations

from .ledger.refs import pending_start_ref

__all__ = ["pending_start_ref"]

