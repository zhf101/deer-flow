from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool", tags=["datamakepool"])


@router.get("/http-assets")
async def list_http_assets() -> dict:
    """列出 HTTP 资产。"""
    return {"status": "not_implemented"}


@router.post("/http-assets")
async def create_http_asset() -> dict:
    """创建 HTTP 资产。"""
    return {"status": "not_implemented"}


@router.post("/http-assets/{asset_id}/test")
async def test_http_asset(asset_id: str) -> dict:
    """测试某个 HTTP 资产。"""
    return {"asset_id": asset_id, "status": "not_implemented"}


@router.get("/sql-assets")
async def list_sql_assets() -> dict:
    """列出 SQL 资产逻辑对象。"""
    return {"status": "not_implemented"}


@router.post("/sql-assets")
async def create_sql_asset() -> dict:
    """创建 SQL 资产逻辑对象或初始草稿版本。"""
    return {"status": "not_implemented"}


@router.post("/sql-asset-versions/{version_id}/submit-review")
async def submit_sql_asset_review(version_id: str) -> dict:
    """提交 SQL 资产版本审核。"""
    return {"version_id": version_id, "status": "not_implemented"}


@router.post("/sql-asset-versions/{version_id}/approve")
async def approve_sql_asset(version_id: str) -> dict:
    """审批通过 SQL 资产版本。"""
    return {"version_id": version_id, "status": "not_implemented"}
