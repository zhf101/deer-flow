from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/runs", tags=["datamakepool"])


@router.post("/from-template")
async def create_run_from_template() -> dict:
    """从已发布模板创建正式执行 Run。"""
    return {"status": "not_implemented"}


@router.get("/{run_id}")
async def get_run(run_id: int) -> dict:
    """读取单个 Run 详情。"""
    return {"run_id": run_id, "status": "not_implemented"}


@router.get("/{run_id}/steps")
async def get_run_steps(run_id: int) -> dict:
    """读取某个 Run 的步骤列表。"""
    return {"run_id": run_id, "status": "not_implemented"}


@router.post("/{run_id}/confirm-dangerous-sql")
async def confirm_dangerous_sql(run_id: int) -> dict:
    """对当前 Run 中待确认的危险 SQL 进行确认。"""
    return {"run_id": run_id, "status": "not_implemented"}
