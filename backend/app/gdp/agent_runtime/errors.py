"""GDP Agent Runtime 错误体系。

每种错误对应一种用户或前端可感知的异常情况，API 层负责将错误映射为 HTTP 响应：
- RuntimeNotFoundError（404）：用户请求的任务不存在或无权查看
- RuntimeConflictError（409）：操作与任务当前状态冲突（如对已完成的任务执行 reply）
- RuntimeValidationError（422）：用户提交的数据不满足命令契约（如缺少必填字段）
- RuntimeForbiddenError（403）：用户没有权限查看审计详情
- RuntimePersistenceError（503）：账本持久化失败，系统已自动回滚内存状态
- RuntimeDependencyError：下游服务（如场景目录）不可用
"""

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
