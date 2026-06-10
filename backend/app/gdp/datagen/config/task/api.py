"""造数任务控制面 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.config.task.models import (
    DatagenTaskContinueResponse,
    DatagenTaskEventResponse,
    DatagenTaskPhase,
    DatagenTaskRunCreateRequest,
    DatagenTaskRunResponse,
    DatagenTaskRunStartRequest,
    DatagenTaskRunStartResponse,
    DatagenTaskStatus,
    DatagenTaskStepResponse,
    DatagenTaskSummaryResponse,
    DatagenTaskUserReplyRequest,
)
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-task"])


def _get_service() -> DatagenTaskService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return DatagenTaskService(DatagenTaskRepository(sf))


async def _get_operator(request: Request) -> str | None:
    from app.gateway.deps import get_current_user

    return await get_current_user(request)


@router.get("/tasks/runs", response_model=list[DatagenTaskRunResponse])
async def list_task_runs(
    status: DatagenTaskStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: DatagenTaskService = Depends(_get_service),
) -> list[DatagenTaskRunResponse]:
    return await service.list_task_runs(status=status, limit=limit, offset=offset)


@router.post("/tasks/runs", response_model=DatagenTaskRunResponse)
async def create_task_run(
    body: DatagenTaskRunCreateRequest,
    operator: str | None = Depends(_get_operator),
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskRunResponse:
    return await service.create_task_run(body, operator=operator)


@router.get("/tasks/runs/{taskRunId}", response_model=DatagenTaskRunResponse)
async def get_task_run(
    taskRunId: str,
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskRunResponse:
    return await service.get_task_run(taskRunId)


@router.post("/tasks/runs/{taskRunId}/start", response_model=DatagenTaskRunStartResponse)
async def start_task_run(
    taskRunId: str,
    body: DatagenTaskRunStartRequest,
    request: Request,
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskRunStartResponse:
    task_run = await service.get_task_run(taskRunId)
    if task_run.status in {
        DatagenTaskStatus.COMPLETED,
        DatagenTaskStatus.FAILED,
        DatagenTaskStatus.CANCELLED,
    }:
        await service.record_event(
            taskRunId,
            event_type="GDP_AGENT_RUN_REJECTED",
            phase=task_run.phase,
            message="任务已结束，不能启动 GDP Agent 运行。",
            payload={"status": task_run.status.value, "deerflowThreadId": body.threadId},
        )
        raise HTTPException(status_code=409, detail="任务已结束，不能启动 GDP Agent 运行。")

    await service.record_event(
        taskRunId,
        event_type="GDP_AGENT_RUN_REQUESTED",
        phase=task_run.phase,
        message="已收到 GDP Agent 运行启动请求。",
        payload={"deerflowThreadId": body.threadId},
    )
    try:
        from app.gateway.routers.thread_runs import RunCreateRequest
        from app.gateway.services import start_run

        run_body = RunCreateRequest(
            assistant_id="gdp_agent",
            input={"task_run_id": taskRunId},
            metadata={
                "agent_name": "gdp_agent",
                "task_run_id": taskRunId,
                "source": "datagen-task-run-start",
            },
            stream_mode=["values", "custom"],
            multitask_strategy="reject",
            on_disconnect="continue",
        )
        record = await start_run(run_body, body.threadId, request)
    except HTTPException as exc:
        await service.record_event(
            taskRunId,
            event_type="GDP_AGENT_RUN_FAILED",
            phase=task_run.phase,
            message="提交 GDP Agent 运行失败。",
            payload={"deerflowThreadId": body.threadId, "error": str(exc.detail)},
        )
        raise
    except Exception as exc:
        await service.record_event(
            taskRunId,
            event_type="GDP_AGENT_RUN_FAILED",
            phase=task_run.phase,
            message="提交 GDP Agent 运行失败。",
            payload={"deerflowThreadId": body.threadId, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"提交 GDP Agent 运行失败：{exc}") from exc

    updated = await service.bind_deerflow_run(
        taskRunId,
        deerflow_thread_id=body.threadId,
        deerflow_run_id=record.run_id,
    )
    await service.record_event(
        taskRunId,
        event_type="GDP_AGENT_RUN_SUBMITTED",
        phase=updated.phase,
        message="已向 DeerFlow Runtime 提交 GDP Agent 运行。",
        payload={"deerflowThreadId": body.threadId, "deerflowRunId": record.run_id},
    )
    return DatagenTaskRunStartResponse(
        taskRun=updated,
        run=_deerflow_run_response(record),
        message="已提交 GDP Agent 运行。",
    )


@router.post("/tasks/runs/{taskRunId}/continue", response_model=DatagenTaskContinueResponse)
async def continue_task(
    taskRunId: str,
    request: Request,
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskContinueResponse:
    response = await service.continue_task(taskRunId)
    task_run = response.taskRun
    if task_run.status == DatagenTaskStatus.WAITING_USER or not task_run.deerflowThreadId:
        return response
    try:
        from app.gateway.routers.thread_runs import RunCreateRequest
        from app.gateway.services import start_run

        run_body = RunCreateRequest(
            assistant_id="gdp_agent",
            input={"task_run_id": taskRunId},
            stream_mode=["values", "custom"],
            multitask_strategy="reject",
            on_disconnect="continue",
        )
        record = await start_run(run_body, task_run.deerflowThreadId, request)
        updated = await service.bind_deerflow_run(taskRunId, deerflow_run_id=record.run_id)
        await service.record_event(
            taskRunId,
            event_type="CONTINUE_RUN_REQUESTED",
            phase=updated.phase,
            message="已向 DeerFlow Runtime 提交任务继续推进请求。",
            payload={"deerflowThreadId": updated.deerflowThreadId, "deerflowRunId": record.run_id},
        )
        return DatagenTaskContinueResponse(taskRun=updated, message="已提交 GDP Agent 运行继续推进任务。")
    except Exception as exc:
        await service.record_event(
            taskRunId,
            event_type="CONTINUE_RUN_FAILED",
            phase=task_run.phase,
            message="提交任务继续推进请求失败。",
            payload={"error": str(exc)},
        )
        raise


@router.post("/tasks/runs/{taskRunId}/cancel", response_model=DatagenTaskRunResponse)
async def cancel_task(
    taskRunId: str,
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskRunResponse:
    return await service.cancel_task(taskRunId)


@router.post("/tasks/runs/{taskRunId}/user-reply", response_model=DatagenTaskEventResponse)
async def record_user_reply(
    taskRunId: str,
    body: DatagenTaskUserReplyRequest,
    request: Request,
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskEventResponse:
    event = await service.record_user_reply(taskRunId, body)
    task_run = await service.get_task_run(taskRunId)
    if task_run.status == DatagenTaskStatus.WAITING_USER and task_run.deerflowThreadId:
        try:
            from app.gateway.routers.thread_runs import RunCreateRequest
            from app.gateway.services import start_run

            run_body = RunCreateRequest(
                assistant_id="gdp_agent",
                command={"resume": body.reply},
                stream_mode=["values", "custom"],
                multitask_strategy="reject",
                on_disconnect="continue",
            )
            record = await start_run(run_body, task_run.deerflowThreadId, request)
            await service.bind_deerflow_run(taskRunId, deerflow_run_id=record.run_id)
            await service.record_event(
                taskRunId,
                event_type="RESUME_REQUESTED",
                phase=DatagenTaskPhase.WAITING_USER,
                message="已向 DeerFlow Runtime 提交中断恢复请求。",
                payload={"deerflowThreadId": task_run.deerflowThreadId, "deerflowRunId": record.run_id},
            )
        except Exception as exc:
            await service.record_event(
                taskRunId,
                event_type="RESUME_FAILED",
                phase=DatagenTaskPhase.WAITING_USER,
                message="提交中断恢复请求失败。",
                payload={"error": str(exc)},
            )
            raise
    return event


@router.get("/tasks/runs/{taskRunId}/steps", response_model=list[DatagenTaskStepResponse])
async def list_task_steps(
    taskRunId: str,
    service: DatagenTaskService = Depends(_get_service),
) -> list[DatagenTaskStepResponse]:
    return await service.list_steps(taskRunId)


@router.get("/tasks/runs/{taskRunId}/events", response_model=list[DatagenTaskEventResponse])
async def list_task_events(
    taskRunId: str,
    service: DatagenTaskService = Depends(_get_service),
) -> list[DatagenTaskEventResponse]:
    return await service.list_events(taskRunId)


@router.get("/tasks/runs/{taskRunId}/summary", response_model=DatagenTaskSummaryResponse)
async def get_task_summary(
    taskRunId: str,
    service: DatagenTaskService = Depends(_get_service),
) -> DatagenTaskSummaryResponse:
    return await service.get_summary(taskRunId)


def _deerflow_run_response(record) -> dict:
    status = getattr(record, "status", "")
    return {
        "run_id": record.run_id,
        "thread_id": record.thread_id,
        "assistant_id": getattr(record, "assistant_id", None),
        "status": getattr(status, "value", status),
        "metadata": getattr(record, "metadata", {}) or {},
        "kwargs": getattr(record, "kwargs", {}) or {},
        "multitask_strategy": getattr(record, "multitask_strategy", "reject"),
        "created_at": getattr(record, "created_at", ""),
        "updated_at": getattr(record, "updated_at", ""),
        "total_input_tokens": getattr(record, "total_input_tokens", 0),
        "total_output_tokens": getattr(record, "total_output_tokens", 0),
        "total_tokens": getattr(record, "total_tokens", 0),
        "llm_call_count": getattr(record, "llm_call_count", 0),
        "lead_agent_tokens": getattr(record, "lead_agent_tokens", 0),
        "subagent_tokens": getattr(record, "subagent_tokens", 0),
        "middleware_tokens": getattr(record, "middleware_tokens", 0),
        "message_count": getattr(record, "message_count", 0),
    }
