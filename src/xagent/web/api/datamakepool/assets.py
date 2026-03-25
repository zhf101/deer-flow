from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.user import User
from ...schemas.datamakepool import (
    HTTPAssetCreateRequest,
    HTTPAssetSummaryResponse,
    SQLAssetCreateRequest,
    SQLAssetCreateResponse,
    SQLAssetSummaryResponse,
    SQLAssetVersionReviewResponse,
)
from ....core.datamakepool.assets import AssetService

router = APIRouter(prefix="/api/datamakepool", tags=["datamakepool"])


@router.get("/http-assets", response_model=list[HTTPAssetSummaryResponse])
async def list_http_assets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[HTTPAssetSummaryResponse]:
    """列出 HTTP 资产。"""
    try:
        result = AssetService(db=db).list_http_assets(user)
        return [HTTPAssetSummaryResponse(**item) for item in result]
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/http-assets", response_model=HTTPAssetSummaryResponse)
async def create_http_asset(
    request: HTTPAssetCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTTPAssetSummaryResponse:
    """创建 HTTP 资产。"""
    try:
        result = AssetService(db=db).create_http_asset(
            user=user,
            name=request.name,
            description=request.description,
            system_short=request.system_short,
            base_url=request.base_url,
            method=request.method,
            path_template=request.path_template,
            query_template=request.query_template,
            headers_template=request.headers_template,
            body_template=request.body_template,
            request_schema=request.request_schema,
            auth_type=request.auth_type,
            auth_config_ciphertext=request.auth_config_ciphertext,
            response_extraction_rules=request.response_extraction_rules,
            timeout_seconds=request.timeout_seconds,
            max_response_bytes=request.max_response_bytes,
            enabled=request.enabled,
        )
        return HTTPAssetSummaryResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/http-assets/{asset_id}/test")
async def test_http_asset(asset_id: str) -> dict:
    """测试某个 HTTP 资产。"""
    return {"asset_id": asset_id, "status": "not_implemented"}


@router.get("/sql-assets", response_model=list[SQLAssetSummaryResponse])
async def list_sql_assets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SQLAssetSummaryResponse]:
    """列出 SQL 资产逻辑对象。"""
    try:
        result = AssetService(db=db).list_sql_assets(user)
        return [SQLAssetSummaryResponse(**item) for item in result]
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/sql-assets", response_model=SQLAssetCreateResponse)
async def create_sql_asset(
    request: SQLAssetCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetCreateResponse:
    """创建 SQL 资产逻辑对象或初始草稿版本。"""
    try:
        result = AssetService(db=db).create_sql_asset(
            user=user,
            name=request.name,
            description=request.description,
            system_short=request.system_short,
            connection_config=request.connection_config,
            whitelist=request.whitelist,
            blacklist=request.blacklist,
            mutation_enabled=request.mutation_enabled,
        )
        return SQLAssetCreateResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/sql-asset-versions/{version_id}/submit-review",
    response_model=SQLAssetVersionReviewResponse,
)
async def submit_sql_asset_review(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionReviewResponse:
    """提交 SQL 资产版本审核。"""
    try:
        result = AssetService(db=db).submit_sql_asset_review(version_id, user)
        return SQLAssetVersionReviewResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/sql-asset-versions/{version_id}/approve",
    response_model=SQLAssetVersionReviewResponse,
)
async def approve_sql_asset(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionReviewResponse:
    """审批通过 SQL 资产版本。"""
    try:
        result = AssetService(db=db).approve_sql_asset_version(version_id, user)
        return SQLAssetVersionReviewResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
