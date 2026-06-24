"""Agent Runtime HTTP 路由。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request

from ..models import DecisionRecord, TaskRunStatus
from ..support.errors import RuntimeServiceError
from ..support.log_text import describe_content, describe_optional
from ..workflows.reply_commands import parse_runtime_command
from .dependencies import _get_service, _mutation_lock, _principal_from_request, _to_http_error
from .schemas import (
    ContextItemResponse,
    CreateTaskRunRequest,
    ReplyTaskRunRequest,
    RollbackPlanRequest,
    RollbackPlanResponse,
    RollbackReplayRequest,
    RollbackReplayResponse,
    RuntimePayloadResponse,
    StartTaskRunRequest,
    TaskRunResponse,
    to_context_item_response,
    to_response,
)

router = APIRouter(prefix="/agent-runtime", tags=["agent-runtime"])
logger = logging.getLogger(__name__)


@router.get("/task-runs", response_model=list[TaskRunResponse])
async def list_task_runs(
    request: Request,
    status: TaskRunStatus | None = Query(default=None, description="按任务状态过滤。"),
    env_code: str | None = Query(default=None, alias="envCode", description="按目标环境编码过滤。"),
    user_id: str | None = Query(default=None, alias="userId", description="按用户 ID 过滤。"),
    limit: int = Query(default=20, ge=1, le=200, description="返回数量。"),
    offset: int = Query(default=0, ge=0, description="分页偏移。"),
) -> list[TaskRunResponse]:
    """分页查询用户的造数任务历史，支持按状态、环境、用户筛选。"""

    principal = _principal_from_request(request)
    task_runs = await _get_service().list_task_runs(
        status=status,
        env_code=env_code,
        user_id=user_id,
        limit=limit,
        offset=offset,
        principal=principal,
    )
    return [to_response(item) for item in task_runs]


@router.post("/task-runs", response_model=TaskRunResponse)
async def create_task_run(request: Request, body: CreateTaskRunRequest) -> TaskRunResponse:
    """用户提交造数目标，创建一个新的造数任务。"""

    async with _mutation_lock():
        logger.info(
            "GDP Agent 运行时接口准备创建任务：环境=%s，用户目标=%s",
            describe_optional(body.env_code),
            body.user_goal,
        )
        try:
            task_run = await _get_service().create_task_run(
                user_goal=body.user_goal,
                env_code=body.env_code,
                thread_id=body.thread_id,
                principal=_principal_from_request(request),
            )
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        logger.info("GDP Agent 运行时接口已创建任务：任务ID=%s，状态=%s", task_run.task_run_id, task_run.status)
        return to_response(task_run)


@router.get("/context-items", response_model=list[ContextItemResponse])
async def list_context_items(
    request: Request,
    thread_id: str | None = Query(default=None, alias="threadId", description="按线程 ID 过滤。"),
    env_code: str | None = Query(default=None, alias="envCode", description="按环境编码过滤。"),
    semantic_type: str | None = Query(default=None, alias="semanticType", description="按语义类型过滤。"),
    limit: int = Query(default=20, ge=1, le=200, description="返回数量。"),
) -> list[ContextItemResponse]:
    """查询可显式复用的安全上下文项，只返回展示摘要和来源追踪。"""

    try:
        items = await _get_service().list_context_items(
            thread_id=thread_id,
            env_code=env_code,
            semantic_type=semantic_type,
            limit=limit,
            principal=_principal_from_request(request),
        )
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    return [to_context_item_response(item) for item in items]


@router.post("/task-runs/{task_run_id}/start", response_model=TaskRunResponse)
async def start_task_run(task_run_id: str, request: Request, body: StartTaskRunRequest) -> TaskRunResponse:
    """启动造数任务执行，可指定场景编码和输入参数，不指定时系统自动搜索选择。"""

    async with _mutation_lock():
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
        return to_response(task_run)


@router.post("/task-runs/{task_run_id}/cancel", response_model=TaskRunResponse)
async def cancel_task_run(task_run_id: str, request: Request) -> TaskRunResponse:
    """取消正在运行或等待中的造数任务，终止后续场景执行。"""

    async with _mutation_lock():
        logger.info("GDP Agent 运行时接口准备取消任务：任务ID=%s", task_run_id)
        try:
            task_run = await _get_service().cancel_task_run(task_run_id, _principal_from_request(request))
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        logger.info("GDP Agent 运行时接口已取消任务：任务ID=%s，状态=%s", task_run_id, task_run.status)
        return to_response(task_run)


@router.post("/task-runs/{task_run_id}/reply", response_model=TaskRunResponse)
async def reply_task_run(task_run_id: str, request: Request, body: ReplyTaskRunRequest) -> TaskRunResponse:
    """用户回复暂停的造数任务（如批准、补参、选场景），驱动任务恢复执行。"""

    async with _mutation_lock():
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
        return to_response(task_run)


@router.post("/task-runs/{task_run_id}/rollback-plan", response_model=RollbackPlanResponse)
async def build_task_run_rollback_plan(
    task_run_id: str,
    request: Request,
    body: RollbackPlanRequest,
) -> RollbackPlanResponse:
    """为失败任务生成用户驱动回退计划；只做影响分析，不自动重放。"""

    try:
        plan = await _get_service().build_rollback_plan(
            task_run_id,
            failed_step_id=body.failed_step_id,
            principal=_principal_from_request(request),
        )
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    return RollbackPlanResponse.model_validate(plan.model_dump(mode="json"))


@router.post("/task-runs/{task_run_id}/rollback-replay", response_model=RollbackReplayResponse)
async def replay_task_run_from_rollback_plan(
    task_run_id: str,
    request: Request,
    body: RollbackReplayRequest,
) -> RollbackReplayResponse:
    """按用户选择的回退点创建替代任务重放；来源失败任务保持终态。"""

    async with _mutation_lock():
        try:
            result = await _get_service().rollback_replay(
                task_run_id,
                rollback_step_id=body.rollback_step_id,
                failed_step_id=body.failed_step_id,
                inputs=body.inputs,
                scene_code=body.scene_code,
                principal=_principal_from_request(request),
            )
        except RuntimeServiceError as exc:
            raise _to_http_error(exc) from exc
        return RollbackReplayResponse(
            source_task_run_id=result.source_task_run_id,
            replacement_task_run=to_response(result.replacement_task_run),
            selected_rollback_step_id=result.selected_rollback_step_id,
            failed_step_id=result.failed_step_id,
            tainted_variable_ids=result.tainted_variable_ids,
            affected_step_ids=result.affected_step_ids,
            carried_input_names=result.carried_input_names,
            replay_mode=result.replay_mode,
        )


@router.get("/task-runs/{task_run_id}", response_model=TaskRunResponse)
async def get_task_run(task_run_id: str, request: Request) -> TaskRunResponse:
    """查询造数任务的当前状态和进展，用户可据此了解任务是否在运行、等待回复或已完成。"""

    try:
        task_run = await _get_service().get_task_run(task_run_id, _principal_from_request(request))
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    return to_response(task_run)


@router.get("/task-runs/{task_run_id}/timeline")
async def get_task_run_timeline(task_run_id: str, request: Request) -> dict[str, Any]:
    """查询造数任务的完整执行时间线，包含每步的场景搜索、执行尝试、证据和判定详情。"""

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
    """查询造数任务的决策审计记录，让用户追溯系统在每个关键节点做了什么选择以及为什么。"""

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
    """查询造数任务的完整请求/响应原始数据，仅限管理员审计权限访问。"""

    try:
        payload = await _get_service().get_payload(task_run_id, ref, _principal_from_request(request))
    except RuntimeServiceError as exc:
        raise _to_http_error(exc) from exc
    return RuntimePayloadResponse(ref=ref, payload=payload)
