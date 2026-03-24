from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/audits", tags=["datamakepool"])


@router.get("/sql")
async def list_sql_audits() -> dict:
    """列出 SQL 审计记录。"""
    return {"status": "not_implemented"}


@router.get("/sql/{audit_id}")
async def get_sql_audit(audit_id: int) -> dict:
    """读取单条 SQL 审计详情。"""
    return {"audit_id": audit_id, "status": "not_implemented"}
