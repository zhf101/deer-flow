from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.user import User
from ...schemas.datamakepool import (
    CreateRunFromTemplateRequest,
    RunDetailResponse,
    RunStepResponse,
    TrialResponse,
)
from ....core.datamakepool.orchestration import RunRuntimeBridge
from ....core.datamakepool.runs import RunService

router = APIRouter(prefix="/api/datamakepool/runs", tags=["datamakepool"])


@router.post("/from-template", response_model=TrialResponse)
async def create_run_from_template(
    request: CreateRunFromTemplateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrialResponse:
    """从已发布模板创建正式执行 Run。"""
    try:
        result = RunService(db=db, runtime_bridge=RunRuntimeBridge()).create_run_from_template(
            template_revision_id=request.template_revision_id,
            initiator_user_id=request.initiator_user_id or int(user.id),
            system_short=request.system_short,
            input_payload=request.input_payload,
        )
        return TrialResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunDetailResponse:
    """读取单个 Run 详情。"""
    del user
    try:
        result = RunService(db=db, runtime_bridge=RunRuntimeBridge()).get_run(run_id)
        return RunDetailResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/steps", response_model=list[RunStepResponse])
async def get_run_steps(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RunStepResponse]:
    """读取某个 Run 的步骤列表。"""
    del user
    try:
        result = RunService(db=db, runtime_bridge=RunRuntimeBridge()).get_run_steps(run_id)
        return [RunStepResponse(**item) for item in result]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/confirm-dangerous-sql")
async def confirm_dangerous_sql(run_id: int) -> dict:
    """对当前 Run 中待确认的危险 SQL 进行确认。"""
    return {"run_id": run_id, "status": "not_implemented"}
