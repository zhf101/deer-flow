"""GDP Agent Runtime MVP API 路由。

路径前缀: /agent-runtime
挂载后完整路径: /api/v1/datagen/agent-runtime/...
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .models import TaskRunStatus
from .store import EntityNotFoundError, Store
from .transitions import IllegalTransition, transition_task_run

router = APIRouter(prefix="/agent-runtime", tags=["agent-runtime"])
logger = logging.getLogger(__name__)

_store = Store()


def get_store() -> Store:
    """获取全局 Store 实例。测试可替换。"""
    return _store


# ---------- Request / Response Models ----------


class CreateTaskRunRequest(BaseModel):
    """创建 GDP Agent MVP 任务。"""

    user_goal: str = Field(min_length=1, description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")


class StartTaskRunRequest(BaseModel):
    """启动 GDP Agent MVP 任务。"""

    scene_code: str = Field(min_length=1, description="要执行的已有 Scene 编码。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Scene 输入参数。")


class ReplyTaskRunRequest(BaseModel):
    """恢复 WAITING_USER 状态的任务。"""

    reply_type: str = Field(description="回复类型：APPROVE / SUPPLY_INPUT / CONFIRM_UNKNOWN_STATE。")
    payload: dict[str, Any] = Field(default_factory=dict, description="回复内容。")


class TaskRunResponse(BaseModel):
    """TaskRun 状态响应。"""

    task_run_id: str = Field(description="任务运行 ID。")
    status: str = Field(description="任务当前状态。")
    user_goal: str = Field(description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")
    pending_question: str | None = Field(default=None, description="等待用户输入时展示的问题。")
    failure_reason: str | None = Field(default=None, description="终态失败时的可读原因。")
    created_at: str = Field(description="创建时间，ISO 8601 字符串。")
    updated_at: str = Field(description="更新时间，ISO 8601 字符串。")
    finished_at: str | None = Field(default=None, description="结束时间，非终态为空。")


# ---------- Endpoints ----------


@router.post("/task-runs", response_model=TaskRunResponse)
async def create_task_run(request: CreateTaskRunRequest) -> TaskRunResponse:
    """创建 TaskRun。"""
    from .flow import create_task_run as _create

    logger.info(
        "GDP Agent Runtime API 创建 TaskRun: env_code=%s user_goal_length=%s",
        request.env_code,
        len(request.user_goal),
    )
    task_run = _create(
        user_goal=request.user_goal,
        env_code=request.env_code,
    )
    get_store().save_task_run(task_run)
    logger.info(
        "GDP Agent Runtime API 已创建 TaskRun: task_run_id=%s status=%s env_code=%s",
        task_run.task_run_id,
        task_run.status,
        task_run.env_code,
    )
    return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/start", response_model=TaskRunResponse)
async def start_task_run(task_run_id: str, request: StartTaskRunRequest) -> TaskRunResponse:
    """启动 TaskRun，指定 scene_code + inputs。"""
    from .runner import run_task

    store = get_store()
    logger.info(
        "GDP Agent Runtime API 启动 TaskRun: task_run_id=%s scene_code=%s input_keys=%s input_count=%s",
        task_run_id,
        request.scene_code,
        sorted(request.inputs.keys()),
        len(request.inputs),
    )
    try:
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent Runtime API 启动失败，TaskRun 不存在: task_run_id=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")

    if task_run.status != TaskRunStatus.CREATED:
        logger.warning(
            "GDP Agent Runtime API 启动失败，状态不允许: task_run_id=%s status=%s",
            task_run_id,
            task_run.status,
        )
        raise HTTPException(status_code=409, detail=f"TaskRun 状态为 {task_run.status}，不能 start")

    task_run = await run_task(task_run, request, store)
    logger.info(
        "GDP Agent Runtime API 启动完成: task_run_id=%s status=%s failure_reason=%s pending_question=%s",
        task_run.task_run_id,
        task_run.status,
        task_run.failure_reason,
        task_run.pending_question,
    )
    return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/cancel", response_model=TaskRunResponse)
async def cancel_task_run(task_run_id: str) -> TaskRunResponse:
    """取消 TaskRun。"""
    store = get_store()
    logger.info("GDP Agent Runtime API 取消 TaskRun: task_run_id=%s", task_run_id)
    try:
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent Runtime API 取消失败，TaskRun 不存在: task_run_id=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")

    try:
        task_run = transition_task_run(task_run, TaskRunStatus.CANCELLED)
    except IllegalTransition:
        logger.warning(
            "GDP Agent Runtime API 取消失败，状态不允许: task_run_id=%s status=%s",
            task_run_id,
            task_run.status,
        )
        raise HTTPException(status_code=409, detail=f"TaskRun 状态为 {task_run.status}，不能取消")

    store.save_task_run(task_run)
    logger.info("GDP Agent Runtime API 已取消 TaskRun: task_run_id=%s status=%s", task_run_id, task_run.status)
    return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/reply", response_model=TaskRunResponse)
async def reply_task_run(task_run_id: str, request: ReplyTaskRunRequest) -> TaskRunResponse:
    """恢复 WAITING_USER 状态的任务。MVP 阶段仅做状态校验和基础回复。"""
    store = get_store()
    logger.info(
        "GDP Agent Runtime API 回复 TaskRun: task_run_id=%s reply_type=%s payload_keys=%s",
        task_run_id,
        request.reply_type,
        sorted(request.payload.keys()),
    )
    try:
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent Runtime API 回复失败，TaskRun 不存在: task_run_id=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")

    if task_run.status != TaskRunStatus.WAITING_USER:
        logger.warning(
            "GDP Agent Runtime API 回复失败，状态不允许: task_run_id=%s status=%s",
            task_run_id,
            task_run.status,
        )
        raise HTTPException(status_code=409, detail=f"TaskRun 状态为 {task_run.status}，不能 reply")

    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    task_run.pending_question = None
    store.save_task_run(task_run)
    logger.info("GDP Agent Runtime API 已回复 TaskRun: task_run_id=%s status=%s", task_run_id, task_run.status)
    return _to_response(task_run)


@router.get("/task-runs/{task_run_id}", response_model=TaskRunResponse)
async def get_task_run(task_run_id: str) -> TaskRunResponse:
    """查询 TaskRun 当前状态。"""
    store = get_store()
    logger.debug("GDP Agent Runtime API 查询 TaskRun: task_run_id=%s", task_run_id)
    try:
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent Runtime API 查询失败，TaskRun 不存在: task_run_id=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")
    return _to_response(task_run)


@router.get("/task-runs/{task_run_id}/timeline")
async def get_task_run_timeline(task_run_id: str) -> dict[str, Any]:
    """查询 TaskRun 的完整时间线。"""
    store = get_store()
    logger.debug("GDP Agent Runtime API 查询 timeline: task_run_id=%s", task_run_id)
    try:
        store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent Runtime API 查询 timeline 失败，TaskRun 不存在: task_run_id=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")
    timeline = store.get_timeline(task_run_id)
    logger.info(
        "GDP Agent Runtime API 已返回 timeline: task_run_id=%s steps=%s actions=%s attempts=%s evidences=%s verdicts=%s variables=%s",
        task_run_id,
        len(timeline["steps"]),
        len(timeline["actions"]),
        len(timeline["attempts"]),
        len(timeline["evidences"]),
        len(timeline["verdicts"]),
        len(timeline["variables"]),
    )
    return timeline


# ---------- Helpers ----------


def _to_response(task_run) -> TaskRunResponse:
    return TaskRunResponse(
        task_run_id=task_run.task_run_id,
        status=task_run.status,
        user_goal=task_run.user_goal,
        env_code=task_run.env_code,
        pending_question=task_run.pending_question,
        failure_reason=task_run.failure_reason,
        created_at=task_run.created_at.isoformat(),
        updated_at=task_run.updated_at.isoformat(),
        finished_at=task_run.finished_at.isoformat() if task_run.finished_at else None,
    )
