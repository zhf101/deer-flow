"""GDP Agent Runtime MVP API 路由。

路径前缀: /agent-runtime
挂载后完整路径: /api/v1/datagen/agent-runtime/...
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .commands import parse_runtime_command
from .errors import RuntimeServiceError
from .log_text import describe_content, describe_optional
from .models import DecisionRecord, ReplyType, TaskRun, TaskRunStatus
from .repository import AgentRuntimeRepository
from .service import RuntimePrincipal, RuntimeService
from .store import Store

router = APIRouter(prefix="/agent-runtime", tags=["agent-runtime"])
logger = logging.getLogger(__name__)

_store = Store()
_mutation_lock = asyncio.Lock()


def get_store() -> Store:
    """获取全局 Store 实例。测试可替换。"""

    return _store


def _get_repository() -> AgentRuntimeRepository | None:
    """获取数据库仓储。内存数据库配置下返回 None。"""

    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return AgentRuntimeRepository(session_factory)


def _get_service() -> RuntimeService:
    """装配 Runtime 应用服务。"""

    return RuntimeService(get_store(), _get_repository())


def _principal_from_request(request: Request) -> RuntimePrincipal:
    """从 Gateway 认证上下文解析 RuntimePrincipal。

    裸 FastAPI 单测没有认证上下文时返回 user_id=None，保持旧的开发/测试行为。
    """

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
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---------- Request / Response Models ----------


class CreateTaskRunRequest(BaseModel):
    """创建 GDP Agent MVP 任务。"""

    user_goal: str = Field(min_length=1, description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")


class StartTaskRunRequest(BaseModel):
    """启动 GDP Agent 任务。第二阶段 scene_code 可选。"""

    scene_code: str | None = Field(default=None, description="显式指定 Scene 编码。为空则由系统按目标搜索。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Scene 输入参数。")


class ReplyTaskRunRequest(BaseModel):
    """恢复 WAITING_USER 状态的任务。"""

    reply_type: ReplyType = Field(
        description=(
            "回复类型。APPROVE：批准已选定且待审批的场景。"
            "SUPPLY_INPUT：补充缺失输入。"
            "CONFIRM_UNKNOWN_STATE：确认执行结果未知并停止。"
            "SELECT_SCENE：在候选中选定场景，可携带 approved=true 表示选择并批准。"
            "SUPPLY_SCENE_CODE：零候选时手动补 scene_code。"
        )
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="回复内容。SELECT_SCENE / SUPPLY_SCENE_CODE 需含 scene_code；选择可带 approved。",
    )


class TaskRunResponse(BaseModel):
    """TaskRun 状态响应。"""

    task_run_id: str = Field(description="任务运行 ID。")
    status: str = Field(description="任务当前状态。")
    user_goal: str = Field(description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")
    suspend_reason: str | None = Field(default=None, description="挂起原因。仅 WAITING_USER 时有值，用于前端和审计识别恢复类型。")
    pending_question: str | None = Field(default=None, description="等待用户输入时展示的问题。")
    failure_reason: str | None = Field(default=None, description="终态失败时的可读原因。")
    created_at: str = Field(description="创建时间，ISO 8601 字符串。")
    updated_at: str = Field(description="更新时间，ISO 8601 字符串。")
    finished_at: str | None = Field(default=None, description="结束时间，非终态为空。")


class RuntimePayloadResponse(BaseModel):
    """Runtime payload 详情响应。"""

    ref: str = Field(description="payload 引用。")
    payload: Any = Field(description="payload 完整内容。")


# ---------- Endpoints ----------


@router.get("/task-runs", response_model=list[TaskRunResponse])
async def list_task_runs(
    request: Request,
    status: TaskRunStatus | None = Query(default=None, description="按任务状态过滤。"),
    env_code: str | None = Query(default=None, alias="envCode", description="按目标环境编码过滤。"),
    user_id: str | None = Query(default=None, alias="userId", description="按用户 ID 过滤。"),
    limit: int = Query(default=20, ge=1, le=200, description="返回数量。"),
    offset: int = Query(default=0, ge=0, description="分页偏移。"),
) -> list[TaskRunResponse]:
    """分页查询历史 TaskRun。"""

    principal = _principal_from_request(request)
    task_runs = await _get_service().list_task_runs(
        status=status,
        env_code=env_code,
        user_id=user_id,
        limit=limit,
        offset=offset,
        principal=principal,
    )
    return [_to_response(item) for item in task_runs]


@router.post("/task-runs", response_model=TaskRunResponse)
async def create_task_run(request: Request, body: CreateTaskRunRequest) -> TaskRunResponse:
    """创建 TaskRun。"""

    async with _mutation_lock:
        logger.info(
            "GDP Agent 运行时接口准备创建任务：环境=%s，用户目标=%s",
            describe_optional(body.env_code),
            body.user_goal,
        )
        try:
            task_run = await _get_service().create_task_run(
                user_goal=body.user_goal,
                env_code=body.env_code,
                principal=_principal_from_request(request),
            )
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        logger.info("GDP Agent 运行时接口已创建任务：任务ID=%s，状态=%s", task_run.task_run_id, task_run.status)
        return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/start", response_model=TaskRunResponse)
async def start_task_run(task_run_id: str, request: Request, body: StartTaskRunRequest) -> TaskRunResponse:
    """启动 TaskRun，指定 scene_code + inputs。"""

    async with _mutation_lock:
        logger.info(
            "GDP Agent 运行时接口准备启动任务：任务ID=%s，场景编码=%s，用户输入请求报文=%s",
            task_run_id,
            body.scene_code,
            describe_content(body.inputs),
        )
        try:
            task_run = await _get_service().start_task_run(task_run_id, body, _principal_from_request(request))
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        logger.info("GDP Agent 运行时接口启动完成：任务ID=%s，状态=%s", task_run.task_run_id, task_run.status)
        return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/cancel", response_model=TaskRunResponse)
async def cancel_task_run(task_run_id: str, request: Request) -> TaskRunResponse:
    """取消 TaskRun。"""

    async with _mutation_lock:
        logger.info("GDP Agent 运行时接口准备取消任务：任务ID=%s", task_run_id)
        try:
            task_run = await _get_service().cancel_task_run(task_run_id, _principal_from_request(request))
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        logger.info("GDP Agent 运行时接口已取消任务：任务ID=%s，状态=%s", task_run_id, task_run.status)
        return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/reply", response_model=TaskRunResponse)
async def reply_task_run(task_run_id: str, request: Request, body: ReplyTaskRunRequest) -> TaskRunResponse:
    """恢复 WAITING_USER 状态的任务。"""

    async with _mutation_lock:
        logger.info(
            "GDP Agent 运行时接口收到任务回复：任务ID=%s，回复类型=%s，回复内容=%s",
            task_run_id,
            body.reply_type,
            describe_content(body.payload),
        )
        try:
            command = parse_runtime_command(body.reply_type, body.payload)
            task_run = await _get_service().reply_task_run(task_run_id, command, _principal_from_request(request))
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        logger.info("GDP Agent 运行时接口已处理任务回复：任务ID=%s，状态=%s", task_run_id, task_run.status)
        return _to_response(task_run)


@router.get("/task-runs/{task_run_id}", response_model=TaskRunResponse)
async def get_task_run(task_run_id: str, request: Request) -> TaskRunResponse:
    """查询 TaskRun 当前状态。"""

    try:
        task_run = await _get_service().get_task_run(task_run_id, _principal_from_request(request))
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    return _to_response(task_run)


@router.get("/task-runs/{task_run_id}/timeline")
async def get_task_run_timeline(task_run_id: str, request: Request) -> dict[str, Any]:
    """查询 TaskRun 的完整时间线。"""

    try:
        timeline = await _get_service().get_timeline(task_run_id, _principal_from_request(request))
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    logger.info(
        "GDP Agent 运行时接口已返回任务时间线：任务ID=%s，时间线内容=%s",
        task_run_id,
        describe_content(timeline, max_chars=4000),
    )
    return timeline


@router.get("/task-runs/{task_run_id}/decisions", response_model=list[DecisionRecord])
async def get_task_run_decisions(task_run_id: str, request: Request) -> list[DecisionRecord]:
    """查询 TaskRun 的决策审计记录。"""

    try:
        return await _get_service().list_decisions(task_run_id, _principal_from_request(request))
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc


@router.get("/task-runs/{task_run_id}/payloads", response_model=RuntimePayloadResponse)
async def get_task_run_payload(
    task_run_id: str,
    request: Request,
    ref: str = Query(..., description="payload 引用。"),
) -> RuntimePayloadResponse:
    """查询 TaskRun 的完整 payload。认证用户必须具备审计权限。"""

    try:
        payload = await _get_service().get_payload(task_run_id, ref, _principal_from_request(request))
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    return RuntimePayloadResponse(ref=ref, payload=payload)


# ---------- Helpers ----------


def _to_response(task_run: TaskRun) -> TaskRunResponse:
    return TaskRunResponse(
        task_run_id=task_run.task_run_id,
        status=task_run.status,
        user_goal=task_run.user_goal,
        env_code=task_run.env_code,
        suspend_reason=task_run.suspend_reason,
        pending_question=task_run.pending_question,
        failure_reason=task_run.failure_reason,
        created_at=task_run.created_at.isoformat(),
        updated_at=task_run.updated_at.isoformat(),
        finished_at=task_run.finished_at.isoformat() if task_run.finished_at else None,
    )
