from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.user import User
from ...schemas.datamakepool import SQLAuditDetailResponse, SQLAuditSummaryResponse
from ....core.datamakepool.governance import GovernanceService

router = APIRouter(prefix="/api/datamakepool/audits", tags=["datamakepool"])


@router.get("/sql", response_model=list[SQLAuditSummaryResponse])
async def list_sql_audits(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SQLAuditSummaryResponse]:
    """列出 SQL 审计记录。"""

    try:
        result = GovernanceService(db=db).list_sql_audits(user)
        return [SQLAuditSummaryResponse(**item) for item in result]
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/sql/{audit_id}", response_model=SQLAuditDetailResponse)
async def get_sql_audit(
    audit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAuditDetailResponse:
    """读取单条 SQL 审计详情。"""

    try:
        result = GovernanceService(db=db).get_sql_audit(audit_id, user)
        return SQLAuditDetailResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
