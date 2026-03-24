from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool", tags=["datamakepool"])


@router.get("/http-assets")
async def list_http_assets() -> dict:
    return {"status": "not_implemented"}


@router.post("/http-assets")
async def create_http_asset() -> dict:
    return {"status": "not_implemented"}


@router.post("/http-assets/{asset_id}/test")
async def test_http_asset(asset_id: str) -> dict:
    return {"asset_id": asset_id, "status": "not_implemented"}


@router.get("/sql-assets")
async def list_sql_assets() -> dict:
    return {"status": "not_implemented"}


@router.post("/sql-assets")
async def create_sql_asset() -> dict:
    return {"status": "not_implemented"}


@router.post("/sql-asset-versions/{version_id}/submit-review")
async def submit_sql_asset_review(version_id: str) -> dict:
    return {"version_id": version_id, "status": "not_implemented"}


@router.post("/sql-asset-versions/{version_id}/approve")
async def approve_sql_asset(version_id: str) -> dict:
    return {"version_id": version_id, "status": "not_implemented"}
