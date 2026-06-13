"""GDP Agent Runtime MVP API 路由。

路径前缀: /agent-runtime
挂载后完整路径: /api/v1/datagen/agent-runtime/...
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .decision import build_approval_requirement_decision, build_user_scene_selection_decision
from .log_text import describe_code, describe_content, describe_optional
from .models import DecisionRecord, ProposalStatus, RequirementStatus, SelectionSource, TaskRun, TaskRunStatus
from .repository import AgentRuntimeRepository
from .runner import collect_preflight_missing, execute_scene, pending_start_ref
from .selection import apply_selection
from .store import EntityNotFoundError, Store
from .transitions import IllegalTransition, transition_requirement, transition_task_run

router = APIRouter(prefix="/agent-runtime", tags=["agent-runtime"])
logger = logging.getLogger(__name__)

_store = Store()


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


async def _persist_task_run(task_run_id: str, store: Store | None = None) -> None:
    """在数据库可用时持久化单个 TaskRun 账本。"""
    repository = _get_repository()
    if repository is None:
        return
    await repository.persist_store(store or get_store(), task_run_id)


async def _persist_task_run_or_rollback(task_run_id: str, store: Store, snapshot: dict[str, Any]) -> None:
    """持久化失败时恢复内存账本，避免内存和数据库状态分歧。"""
    try:
        await _persist_task_run(task_run_id, store)
    except Exception as exc:
        store.restore(snapshot)
        logger.exception("GDP Agent 运行时账本持久化失败，已回滚内存状态：任务ID=%s", task_run_id)
        raise HTTPException(status_code=503, detail="运行时账本持久化失败，请稍后重试") from exc


async def _load_store_for_task_run(task_run_id: str) -> Store:
    """优先读内存 Store，未命中时从数据库恢复。"""
    global _store

    store = get_store()
    try:
        store.get_task_run(task_run_id)
        return store
    except EntityNotFoundError:
        repository = _get_repository()
        if repository is None:
            raise
        _store = await repository.hydrate_store(task_run_id)
        return _store


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

    reply_type: Literal["APPROVE", "SUPPLY_INPUT", "CONFIRM_UNKNOWN_STATE", "SELECT_SCENE", "SUPPLY_SCENE_CODE"] = Field(
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
    status: TaskRunStatus | None = Query(default=None, description="按任务状态过滤。"),
    env_code: str | None = Query(default=None, alias="envCode", description="按目标环境编码过滤。"),
    user_id: str | None = Query(default=None, alias="userId", description="按用户 ID 过滤。"),
    limit: int = Query(default=20, ge=1, le=200, description="返回数量。"),
    offset: int = Query(default=0, ge=0, description="分页偏移。"),
) -> list[TaskRunResponse]:
    """分页查询历史 TaskRun。"""
    repository = _get_repository()
    if repository is not None:
        task_runs = await repository.list_task_runs(
            status=status,
            env_code=env_code,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    else:
        task_runs = get_store().list_task_runs()
        if status is not None:
            task_runs = [item for item in task_runs if item.status == status]
        if env_code:
            task_runs = [item for item in task_runs if item.env_code == env_code]
        if user_id:
            task_runs = [item for item in task_runs if item.user_id == user_id]
        task_runs = task_runs[offset : offset + limit]
    return [_to_response(item) for item in task_runs]


@router.post("/task-runs", response_model=TaskRunResponse)
async def create_task_run(request: CreateTaskRunRequest) -> TaskRunResponse:
    """创建 TaskRun。"""
    from .flow import create_task_run as _create

    logger.info(
        "GDP Agent 运行时接口准备创建任务：环境=%s，用户目标=%s ",
        describe_optional(request.env_code),
        request.user_goal,
    )
    task_run = _create(
        user_goal=request.user_goal,
        env_code=request.env_code,
    )
    store = get_store()
    snapshot = store.snapshot()
    store.save_task_run(task_run)
    await _persist_task_run_or_rollback(task_run.task_run_id, store, snapshot)
    logger.info(
        "GDP Agent 运行时接口已创建任务：任务ID=%s，状态=%s，环境=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        describe_optional(task_run.env_code),
    )
    return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/start", response_model=TaskRunResponse)
async def start_task_run(task_run_id: str, request: StartTaskRunRequest) -> TaskRunResponse:
    """启动 TaskRun，指定 scene_code + inputs。"""
    from .runner import run_task

    logger.info(
        "GDP Agent 运行时接口准备启动任务：任务ID=%s，场景编码=%s，用户输入请求报文=%s",
        task_run_id,
        request.scene_code,
        describe_content(request.inputs),
    )
    try:
        store = await _load_store_for_task_run(task_run_id)
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent 运行时接口启动失败，任务不存在：任务ID=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")

    if task_run.status != TaskRunStatus.CREATED:
        logger.warning(
            "GDP Agent 运行时接口启动失败，当前状态不允许启动：任务ID=%s，状态=%s",
            task_run_id,
            describe_code(task_run.status),
        )
        raise HTTPException(status_code=409, detail=f"TaskRun 状态为 {task_run.status}，不能 start")

    snapshot = store.snapshot()
    task_run = await run_task(task_run, request, store)
    await _persist_task_run_or_rollback(task_run.task_run_id, store, snapshot)
    logger.info(
        "GDP Agent 运行时接口启动完成：任务ID=%s，状态=%s，失败原因=%s，待用户确认=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        describe_optional(task_run.failure_reason),
        describe_optional(task_run.pending_question),
    )
    return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/cancel", response_model=TaskRunResponse)
async def cancel_task_run(task_run_id: str) -> TaskRunResponse:
    """取消 TaskRun。"""
    logger.info("GDP Agent 运行时接口准备取消任务：任务ID=%s", task_run_id)
    try:
        store = await _load_store_for_task_run(task_run_id)
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent 运行时接口取消失败，任务不存在：任务ID=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")

    snapshot = store.snapshot()
    try:
        task_run = transition_task_run(task_run, TaskRunStatus.CANCELLED)
    except IllegalTransition:
        logger.warning(
            "GDP Agent 运行时接口取消失败，当前状态不允许取消：任务ID=%s，状态=%s",
            task_run_id,
            describe_code(task_run.status),
        )
        raise HTTPException(status_code=409, detail=f"TaskRun 状态为 {task_run.status}，不能取消")

    store.save_task_run(task_run)
    await _persist_task_run_or_rollback(task_run.task_run_id, store, snapshot)
    logger.info("GDP Agent 运行时接口已取消任务：任务ID=%s，状态=%s", task_run_id, describe_code(task_run.status))
    return _to_response(task_run)


@router.post("/task-runs/{task_run_id}/reply", response_model=TaskRunResponse)
async def reply_task_run(task_run_id: str, request: ReplyTaskRunRequest) -> TaskRunResponse:
    """恢复 WAITING_USER 状态的任务。MVP 阶段仅做状态校验和基础回复。"""
    logger.info(
        "GDP Agent 运行时接口收到任务回复：任务ID=%s，回复类型=%s，回复内容=%s",
        task_run_id,
        request.reply_type,
        describe_content(request.payload),
    )
    try:
        store = await _load_store_for_task_run(task_run_id)
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent 运行时接口回复失败，任务不存在：任务ID=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")

    if task_run.status != TaskRunStatus.WAITING_USER:
        logger.warning(
            "GDP Agent 运行时接口回复失败，当前状态不等待用户：任务ID=%s，状态=%s",
            task_run_id,
            describe_code(task_run.status),
        )
        raise HTTPException(status_code=409, detail=f"TaskRun 状态为 {task_run.status}，不能 reply")

    snapshot = store.snapshot()
    if request.reply_type == "CONFIRM_UNKNOWN_STATE":
        task_run = _confirm_unknown_state(task_run, request.payload, store)
    elif request.reply_type == "SUPPLY_INPUT":
        task_run = await _resume_with_supplied_input(task_run, request.payload, store)
    elif request.reply_type == "SELECT_SCENE":
        task_run = await _select_scene(task_run, request.payload, store)
    elif request.reply_type == "SUPPLY_SCENE_CODE":
        task_run = await _supply_scene_code(task_run, request.payload, store)
    elif request.reply_type == "APPROVE":
        task_run = await _approve_scene(task_run, request.payload, store)
    else:
        raise HTTPException(status_code=422, detail=f"不支持的 reply_type: {request.reply_type}")

    await _persist_task_run_or_rollback(task_run.task_run_id, store, snapshot)
    logger.info("GDP Agent 运行时接口已处理任务回复：任务ID=%s，状态=%s", task_run_id, describe_code(task_run.status))
    return _to_response(task_run)


@router.get("/task-runs/{task_run_id}", response_model=TaskRunResponse)
async def get_task_run(task_run_id: str) -> TaskRunResponse:
    """查询 TaskRun 当前状态。"""
    logger.debug("GDP Agent 运行时接口查询任务：任务ID=%s", task_run_id)
    try:
        store = await _load_store_for_task_run(task_run_id)
        task_run = store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent 运行时接口查询失败，任务不存在：任务ID=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")
    return _to_response(task_run)


@router.get("/task-runs/{task_run_id}/timeline")
async def get_task_run_timeline(task_run_id: str) -> dict[str, Any]:
    """查询 TaskRun 的完整时间线。"""
    logger.debug("GDP Agent 运行时接口查询任务时间线：任务ID=%s", task_run_id)
    try:
        store = await _load_store_for_task_run(task_run_id)
        store.get_task_run(task_run_id)
    except EntityNotFoundError:
        logger.warning("GDP Agent 运行时接口查询时间线失败，任务不存在：任务ID=%s", task_run_id)
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found")
    timeline = store.get_timeline(task_run_id)
    logger.info(
        "GDP Agent 运行时接口已返回任务时间线：任务ID=%s，时间线内容=%s",
        task_run_id,
        describe_content(timeline, max_chars=4000),
    )
    return timeline


@router.get("/task-runs/{task_run_id}/decisions", response_model=list[DecisionRecord])
async def get_task_run_decisions(task_run_id: str) -> list[DecisionRecord]:
    """查询 TaskRun 的决策审计记录。"""
    try:
        store = await _load_store_for_task_run(task_run_id)
        store.get_task_run(task_run_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"TaskRun {task_run_id} not found") from exc
    return store.list_decisions(task_run_id)


@router.get("/task-runs/{task_run_id}/payloads", response_model=RuntimePayloadResponse)
async def get_task_run_payload(
    task_run_id: str,
    ref: str = Query(..., description="payload 引用。"),
) -> RuntimePayloadResponse:
    """查询 TaskRun 的完整 payload。"""
    try:
        store = await _load_store_for_task_run(task_run_id)
        payload = store.get_payload(ref)
    except EntityNotFoundError as memory_exc:
        repository = _get_repository()
        if repository is None:
            raise HTTPException(status_code=404, detail=f"Payload {ref} not found in memory store") from memory_exc
        try:
            payload = await repository.get_payload(task_run_id, ref)
        except EntityNotFoundError as repository_exc:
            raise HTTPException(
                status_code=404,
                detail=f"Payload {ref} not found in memory store or database",
            ) from repository_exc
    return RuntimePayloadResponse(ref=ref, payload=payload)


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


def _confirm_unknown_state(task_run: TaskRun, payload: dict[str, Any], store: Store) -> TaskRun:
    latest_verdict_type = _latest_verdict_type(task_run.task_run_id, store)
    if latest_verdict_type != "UNKNOWN_STATE":
        logger.warning(
            "GDP Agent 运行时接口确认未知结果失败，最近判定不是 UNKNOWN_STATE：任务ID=%s，最近判定=%s",
            task_run.task_run_id,
            describe_optional(latest_verdict_type),
        )
        raise HTTPException(status_code=409, detail="当前 TaskRun 不是执行结果未知状态，不能确认 UNKNOWN_STATE")

    task_run.pending_question = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    task_run.failure_reason = _format_unknown_state_confirmation(payload)
    task_run = transition_task_run(task_run, TaskRunStatus.FAILED)
    store.save_task_run(task_run)
    return task_run


async def _resume_with_supplied_input(task_run: TaskRun, payload: dict[str, Any], store: Store) -> TaskRun:
    if _has_write_attempts(task_run.task_run_id, store):
        logger.warning(
            "GDP Agent 运行时接口补输入失败，任务已发起写请求，禁止重放：任务ID=%s",
            task_run.task_run_id,
        )
        raise HTTPException(status_code=409, detail="当前 TaskRun 已发起写请求，不能通过 SUPPLY_INPUT 重放")

    try:
        pending_start = store.get_payload(pending_start_ref(task_run.task_run_id))
    except EntityNotFoundError:
        logger.warning("GDP Agent 运行时接口补输入失败，找不到待恢复启动请求：任务ID=%s", task_run.task_run_id)
        raise HTTPException(status_code=409, detail="找不到可恢复的启动请求")

    if not isinstance(pending_start, dict):
        raise HTTPException(status_code=409, detail="待恢复启动请求格式无效")

    scene_code = pending_start.get("scene_code")

    supplied_env_code = payload.get("env_code")
    if supplied_env_code is not None:
        if not isinstance(supplied_env_code, str) or not supplied_env_code.strip():
            raise HTTPException(status_code=422, detail="payload.env_code 必须是非空字符串")
        task_run.env_code = supplied_env_code.strip()

    inputs = _merge_supplied_inputs(pending_start.get("inputs"), payload)
    task_run.pending_question = None

    from .runner import run_task

    return await run_task(
        task_run,
        SimpleNamespace(scene_code=_strip_optional(scene_code), inputs=inputs),
        store,
    )


async def _select_scene(task_run: TaskRun, payload: dict[str, Any], store: Store) -> TaskRun:
    requirement = _get_waiting_requirement(task_run.task_run_id, store)
    proposal = _get_waiting_proposal(task_run.task_run_id, store, requirement.requirement_id)
    scene_code = _require_scene_code(payload)
    inputs = await _merge_reply_inputs(task_run, payload, store)

    candidate = next((item for item in proposal.candidates if item.scene_code == scene_code), None)
    if candidate is None:
        raise HTTPException(status_code=422, detail="payload.scene_code 不在最近候选内")

    if requirement.status == RequirementStatus.PENDING:
        requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)

    requirement, proposal = apply_selection(requirement, proposal, scene_code, SelectionSource.USER)
    requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
    store.save_requirement(requirement)
    store.save_proposal(proposal)
    store.save_decision(
        build_user_scene_selection_decision(
            task_run,
            requirement,
            proposal,
            scene_code,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )

    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        store.save_task_run(task_run)
        return task_run

    approved = payload.get("approved") is True
    if candidate.requires_confirmation and not approved:
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                candidate,
                approved=False,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )
        task_run.pending_question = (
            f"场景 {candidate.scene_name}（{candidate.scene_code}）已选定，但执行有写副作用。"
            "请批准后继续。"
        )
        store.save_task_run(task_run)
        return task_run

    if candidate.requires_confirmation:
        _save_approval_record(store, task_run.task_run_id, requirement.requirement_id, proposal.proposal_id, candidate.scene_code)
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                candidate,
                approved=True,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )

    task_run.pending_question = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    return await execute_scene(task_run, store.get_step(requirement.step_id), requirement, scene_code, inputs, candidate, store)


async def _supply_scene_code(task_run: TaskRun, payload: dict[str, Any], store: Store) -> TaskRun:
    requirement = _get_waiting_requirement(task_run.task_run_id, store)
    proposal = _get_waiting_proposal(task_run.task_run_id, store, requirement.requirement_id)
    if proposal.candidates:
        raise HTTPException(status_code=409, detail="当前不是零候选等待状态，不能 SUPPLY_SCENE_CODE")

    scene_code = _require_scene_code(payload)
    inputs = await _merge_reply_inputs(task_run, payload, store)
    catalog = _get_scene_catalog()

    from .catalog import resolve_explicit_scene

    proposal = await resolve_explicit_scene(requirement, scene_code, inputs, catalog)
    resolved = proposal.candidates[0]
    store.save_proposal(proposal)
    requirement = transition_requirement(requirement, RequirementStatus.RESOLVING)
    requirement, proposal = apply_selection(requirement, proposal, scene_code, SelectionSource.USER)
    requirement = transition_requirement(requirement, RequirementStatus.SATISFIED)
    store.save_requirement(requirement)
    store.save_proposal(proposal)
    store.save_decision(
        build_user_scene_selection_decision(
            task_run,
            requirement,
            proposal,
            scene_code,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )

    missing_fields = collect_preflight_missing(task_run, resolved)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        store.save_task_run(task_run)
        return task_run

    approved = payload.get("approved") is True
    if resolved.requires_confirmation and not approved:
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                resolved,
                approved=False,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )
        task_run.pending_question = (
            f"场景 {resolved.scene_name}（{resolved.scene_code}）已补录，但执行有写副作用。请批准后继续。"
        )
        store.save_task_run(task_run)
        return task_run

    if resolved.requires_confirmation:
        _save_approval_record(store, task_run.task_run_id, requirement.requirement_id, proposal.proposal_id, resolved.scene_code)
        store.save_decision(
            build_approval_requirement_decision(
                task_run,
                requirement,
                proposal,
                resolved,
                approved=True,
                input_ref=pending_start_ref(task_run.task_run_id),
            )
        )

    task_run.pending_question = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    return await execute_scene(task_run, store.get_step(requirement.step_id), requirement, scene_code, inputs, resolved, store)


async def _approve_scene(task_run: TaskRun, payload: dict[str, Any], store: Store) -> TaskRun:
    requirement = _get_waiting_requirement(task_run.task_run_id, store)
    proposal = _get_latest_selected_proposal(task_run.task_run_id, store, requirement.requirement_id)
    if proposal.selected_scene_code is None:
        raise HTTPException(status_code=409, detail="当前没有待审批的已选定场景")

    candidate = next((item for item in proposal.candidates if item.scene_code == proposal.selected_scene_code), None)
    if candidate is None or not candidate.requires_confirmation:
        raise HTTPException(status_code=409, detail="当前 TaskRun 没有等待审批的候选")
    if store.has_approval_record(task_run.task_run_id, proposal.selected_scene_code):
        raise HTTPException(status_code=409, detail="该场景已经审批，无需重复 APPROVE")

    inputs = await _merge_reply_inputs(task_run, payload, store)
    missing_fields = collect_preflight_missing(task_run, candidate)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        store.save_task_run(task_run)
        return task_run

    _save_approval_record(store, task_run.task_run_id, requirement.requirement_id, proposal.proposal_id, proposal.selected_scene_code)
    store.save_decision(
        build_approval_requirement_decision(
            task_run,
            requirement,
            proposal,
            candidate,
            approved=True,
            input_ref=pending_start_ref(task_run.task_run_id),
        )
    )
    task_run.pending_question = None
    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    return await execute_scene(
        task_run,
        store.get_step(requirement.step_id),
        requirement,
        proposal.selected_scene_code,
        inputs,
        candidate,
        store,
    )


def _merge_supplied_inputs(pending_inputs: Any, payload: dict[str, Any]) -> dict[str, Any]:
    base_inputs = pending_inputs if isinstance(pending_inputs, dict) else {}
    supplied_inputs = payload.get("inputs")
    if supplied_inputs is None:
        supplied_inputs = {
            key: value
            for key, value in payload.items()
            if key not in {"env_code", "message", "scene_code", "approved"}
        }
    if not isinstance(supplied_inputs, dict):
        raise HTTPException(status_code=422, detail="payload.inputs 必须是对象")
    return {**base_inputs, **supplied_inputs}


def _latest_verdict_type(task_run_id: str, store: Store) -> str | None:
    verdicts = store.get_timeline(task_run_id)["verdicts"]
    if not verdicts:
        return None
    verdict_type = verdicts[-1].get("verdict_type")
    return verdict_type if isinstance(verdict_type, str) else None


def _has_write_attempts(task_run_id: str, store: Store) -> bool:
    return bool(store.get_timeline(task_run_id)["attempts"])


def _format_unknown_state_confirmation(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return "用户确认执行结果未知，任务已停止以避免重复写请求。用户说明：" + message.strip()
    return "用户确认执行结果未知，任务已停止以避免重复写请求。"


def _format_missing_required_question(missing_fields: list[str]) -> str:
    return "缺少必填信息：" + "，".join(missing_fields) + "。请补充后继续。"


def _require_scene_code(payload: dict[str, Any]) -> str:
    scene_code = payload.get("scene_code")
    if not isinstance(scene_code, str) or not scene_code.strip():
        raise HTTPException(status_code=422, detail="payload.scene_code 必须是非空字符串")
    return scene_code.strip()


def _strip_optional(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _get_waiting_requirement(task_run_id: str, store: Store):
    requirement = store.get_active_requirement(task_run_id)
    if requirement is None:
        raise HTTPException(status_code=409, detail="当前 TaskRun 没有可恢复的 Requirement")
    return requirement


def _get_waiting_proposal(task_run_id: str, store: Store, requirement_id: str):
    proposal = store.get_latest_proposal(task_run_id)
    if proposal is None or proposal.requirement_id != requirement_id:
        raise HTTPException(status_code=409, detail="当前 TaskRun 没有可恢复的 Proposal")
    if proposal.status != ProposalStatus.PENDING:
        raise HTTPException(status_code=409, detail="最近候选集已不是待选择状态")
    return proposal


def _get_latest_selected_proposal(task_run_id: str, store: Store, requirement_id: str):
    proposal = store.get_latest_proposal(task_run_id)
    if proposal is None or proposal.requirement_id != requirement_id:
        raise HTTPException(status_code=409, detail="当前 TaskRun 没有可恢复的 Proposal")
    if proposal.status != ProposalStatus.SELECTED:
        raise HTTPException(status_code=409, detail="当前没有已选定且待审批的 Proposal")
    return proposal


async def _merge_reply_inputs(task_run: TaskRun, payload: dict[str, Any], store: Store) -> dict[str, Any]:
    try:
        pending_start = store.get_payload(pending_start_ref(task_run.task_run_id))
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=409, detail="找不到可恢复的启动请求") from exc
    if not isinstance(pending_start, dict):
        raise HTTPException(status_code=409, detail="待恢复启动请求格式无效")

    supplied_env_code = payload.get("env_code")
    if supplied_env_code is not None:
        if not isinstance(supplied_env_code, str) or not supplied_env_code.strip():
            raise HTTPException(status_code=422, detail="payload.env_code 必须是非空字符串")
        task_run.env_code = supplied_env_code.strip()

    inputs = _merge_supplied_inputs(pending_start.get("inputs"), payload)
    store.save_payload(
        pending_start_ref(task_run.task_run_id),
        {"scene_code": payload.get("scene_code", pending_start.get("scene_code")), "inputs": inputs},
    )
    return inputs


def _save_approval_record(
    store: Store,
    task_run_id: str,
    requirement_id: str,
    proposal_id: str,
    scene_code: str,
) -> None:
    from datetime import UTC, datetime

    store.save_approval_record(
        {
            "task_run_id": task_run_id,
            "requirement_id": requirement_id,
            "proposal_id": proposal_id,
            "scene_code": scene_code,
            "approved_by": "USER",
            "approved_at": datetime.now(UTC).isoformat(),
        }
    )


def _get_scene_catalog():
    from . import runner as runtime_runner

    return runtime_runner.get_catalog()
