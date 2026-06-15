"""Agent Runtime API 依赖装配。"""

from __future__ import annotations

import sys

from fastapi import HTTPException, Request

from ..application.service import RuntimePrincipal, RuntimeService
from ..ledger.memory import MemoryLedger as Store
from ..ledger.sql import SqlLedger
from ..support.errors import RuntimeServiceError


def _api_module():
    """返回父 package，确保测试 monkeypatch runtime_api._store/_get_repository 生效。"""

    return sys.modules[__package__]


def get_store() -> Store:
    """获取全局内存账本实例，测试环境可替换为隔离实例。"""

    return _api_module()._store


def _get_repository() -> SqlLedger | None:
    """获取数据库持久化仓储。若当前配置为纯内存模式，则返回 None。"""

    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return SqlLedger(session_factory)


def _get_service() -> RuntimeService:
    """装配运行时应用服务。"""

    api = _api_module()
    return RuntimeService(api.get_store(), api._get_repository())


def _mutation_lock():
    """获取全局写操作互斥锁。"""

    return _api_module()._mutation_lock


def _principal_from_request(request: Request) -> RuntimePrincipal:
    """从网关认证上下文中解析当前用户身份。"""

    user = getattr(request.state, "user", None)
    if user is None:
        try:
            from deerflow.runtime.user_context import get_current_user

            user = get_current_user()
        except Exception:
            user = None

    user_id = getattr(user, "id", None)
    if user_id is None:
        return RuntimePrincipal(user_id=None)
    return RuntimePrincipal(user_id=str(user_id), is_admin=getattr(user, "system_role", None) == "admin")


def _to_http_error(exc: RuntimeServiceError) -> HTTPException:
    """将应用层异常映射成 HTTP 异常。"""

    return HTTPException(status_code=exc.status_code, detail=exc.detail)
