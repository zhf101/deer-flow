from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.dm_run import DMRun
from ...models.user import User
from ...schemas.datamakepool import (
    CreateRunFromTemplateRequest,
    DangerousSQLConfirmRequest,
    DangerousSQLConfirmResponse,
    PendingDangerousSQLResponse,
    RunDetailResponse,
    RunSQLAuditSummaryResponse,
    RunStepResponse,
    TrialResponse,
)
from ....core.datamakepool.governance import GovernanceService
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
        governance_service = GovernanceService(db=db)
        initiator_user_id = governance_service.assert_initiator_override_allowed(
            request.initiator_user_id,
            user,
        )
        result = RunService(db=db, runtime_bridge=RunRuntimeBridge()).create_run_from_template(
            template_revision_id=request.template_revision_id,
            user=user,
            initiator_user_id=initiator_user_id,
            system_short=request.system_short,
            input_payload=request.input_payload,
        )
        return TrialResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunDetailResponse:
    """读取单个 Run 详情。"""
    try:
        service = RunService(db=db, runtime_bridge=RunRuntimeBridge())
        run = db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        GovernanceService(db=db).assert_run_access(run, user)
        result = service.get_run(run_id)
        return RunDetailResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{run_id}/steps", response_model=list[RunStepResponse])
async def get_run_steps(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RunStepResponse]:
    """读取某个 Run 的步骤列表。"""
    try:
        service = RunService(db=db, runtime_bridge=RunRuntimeBridge())
        run = db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        GovernanceService(db=db).assert_run_access(run, user)
        result = service.get_run_steps(run_id)
        return [RunStepResponse(**item) for item in result]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{run_id}/start", response_model=RunDetailResponse)
async def start_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunDetailResponse:
    """启动一条待执行的正式 Run。"""
    try:
        result = RunService(db=db, runtime_bridge=RunRuntimeBridge()).start_run(run_id, user)
        return RunDetailResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{run_id}/dangerous-sql-pending", response_model=PendingDangerousSQLResponse)
async def get_pending_dangerous_sql(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PendingDangerousSQLResponse:
    """读取当前 Run 仍待人工确认的危险 SQL 摘要。"""
    try:
        result = GovernanceService(db=db).get_pending_dangerous_sql_for_run(run_id, user)
        return PendingDangerousSQLResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{run_id}/sql-audits", response_model=RunSQLAuditSummaryResponse)
async def get_run_sql_audits(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunSQLAuditSummaryResponse:
    """读取当前 Run 的 SQL 审计摘要。"""
    try:
        result = GovernanceService(db=db).list_run_sql_audits(run_id, user)
        return RunSQLAuditSummaryResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/{run_id}/confirm-dangerous-sql", response_model=DangerousSQLConfirmResponse)
async def confirm_dangerous_sql(
    run_id: int,
    request: DangerousSQLConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DangerousSQLConfirmResponse:
    """对当前 Run 中待确认的危险 SQL 进行确认。"""
    try:
        governance_result = GovernanceService(db=db).confirm_dangerous_sql(
            run_id=run_id,
            user=user,
            reason=request.reason,
            step_ids=request.run_step_ids,
        )
        resume_result = None
        resumed = False
        if request.resume_execution:
            resume_result = RunService(db=db, runtime_bridge=RunRuntimeBridge()).resume_run(run_id)
            governance_result["status"] = str(resume_result.get("status") or governance_result["status"])
            resumed = True

        return DangerousSQLConfirmResponse(
            **governance_result,
            resumed=resumed,
            resume_result=resume_result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
