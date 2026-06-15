"""造数运行时 HTTP API 包。

本包保留历史 runtime API 导入入口，同时把请求响应模型、
依赖装配和路由函数拆分到独立模块。
"""

from __future__ import annotations

import asyncio

from ..ledger.memory import MemoryLedger as Store
from .dependencies import _get_repository, _get_service, _principal_from_request, _to_http_error, get_store
from .routes import (
    cancel_task_run,
    create_task_run,
    get_task_run,
    get_task_run_decisions,
    get_task_run_payload,
    get_task_run_timeline,
    list_task_runs,
    reply_task_run,
    router,
    start_task_run,
)
from .schemas import (
    CreateTaskRunRequest,
    ReplyTaskRunRequest,
    RuntimePayloadResponse,
    StartTaskRunRequest,
    TaskRunResponse,
)

_store = Store()
_mutation_lock = asyncio.Lock()

__all__ = [
    "CreateTaskRunRequest",
    "ReplyTaskRunRequest",
    "RuntimePayloadResponse",
    "StartTaskRunRequest",
    "TaskRunResponse",
    "_get_repository",
    "_get_service",
    "_mutation_lock",
    "_principal_from_request",
    "_store",
    "_to_http_error",
    "cancel_task_run",
    "create_task_run",
    "get_store",
    "get_task_run",
    "get_task_run_decisions",
    "get_task_run_payload",
    "get_task_run_timeline",
    "list_task_runs",
    "reply_task_run",
    "router",
    "start_task_run",
]
