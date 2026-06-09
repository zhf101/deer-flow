"""造数任务控制面 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.gdp.datagen.config.task.models import (
    DatagenTaskContinueResponse,
    DatagenTaskEventResponse,
    DatagenTaskPhase,
    DatagenTaskRunCreateRequest,
    DatagenTaskRunResponse,
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
            stream_mode=["values"],
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
                stream_mode=["values"],
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
