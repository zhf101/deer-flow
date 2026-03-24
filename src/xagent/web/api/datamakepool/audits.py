from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/audits", tags=["datamakepool"])


@router.get("/sql")
async def list_sql_audits() -> dict:
    return {"status": "not_implemented"}


@router.get("/sql/{audit_id}")
async def get_sql_audit(audit_id: int) -> dict:
    return {"audit_id": audit_id, "status": "not_implemented"}
