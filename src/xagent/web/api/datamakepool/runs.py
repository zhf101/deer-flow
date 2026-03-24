from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/runs", tags=["datamakepool"])


@router.post("/from-template")
async def create_run_from_template() -> dict:
    return {"status": "not_implemented"}


@router.get("/{run_id}")
async def get_run(run_id: int) -> dict:
    return {"run_id": run_id, "status": "not_implemented"}


@router.get("/{run_id}/steps")
async def get_run_steps(run_id: int) -> dict:
    return {"run_id": run_id, "status": "not_implemented"}


@router.post("/{run_id}/confirm-dangerous-sql")
async def confirm_dangerous_sql(run_id: int) -> dict:
    return {"run_id": run_id, "status": "not_implemented"}
