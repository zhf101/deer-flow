"""GDP Agent Runtime 服务层错误。"""

from __future__ import annotations


class RuntimeServiceError(Exception):
    """服务层错误，API 层负责映射为 HTTP 响应。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class RuntimeNotFoundError(RuntimeServiceError):
    """请求的运行时资源不存在，或当前用户不可见。"""

    def __init__(self, detail: str) -> None:
        super().__init__(404, detail)


class RuntimeConflictError(RuntimeServiceError):
    """请求和当前运行时状态冲突。"""

    def __init__(self, detail: str) -> None:
        super().__init__(409, detail)


class RuntimeValidationError(RuntimeServiceError):
    """请求内容不满足运行时命令契约。"""

    def __init__(self, detail: str) -> None:
        super().__init__(422, detail)


class RuntimeForbiddenError(RuntimeServiceError):
    """当前用户没有读取该运行时详情的权限。"""

    def __init__(self, detail: str) -> None:
        super().__init__(403, detail)


class RuntimePersistenceError(RuntimeServiceError):
    """运行时账本持久化失败。"""

    def __init__(self, detail: str = "运行时账本持久化失败，请稍后重试") -> None:
        super().__init__(503, detail)


class RuntimeDependencyError(RuntimeServiceError):
    """运行时依赖的外部应用服务失败。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code, detail)
