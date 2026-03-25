from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.user import User
from ...schemas.datamakepool import (
    AssetTemplateReferenceResponse,
    AssetDeleteResponse,
    HTTPAssetCreateRequest,
    HTTPAssetDetailResponse,
    HTTPAssetSummaryResponse,
    HTTPAssetTestRequest,
    HTTPAssetTestResponse,
    HTTPAssetUpdateRequest,
    SQLAssetCreateRequest,
    SQLAssetCreateResponse,
    SQLAssetSummaryResponse,
    SQLAssetUpdateRequest,
    SQLAssetVersionCreateRequest,
    SQLAssetVersionCreateResponse,
    SQLAssetVersionDetailResponse,
    SQLAssetVersionReviewResponse,
    SQLAssetVersionSummaryResponse,
    SQLAssetVersionTestRequest,
    SQLAssetVersionTestResponse,
    SQLAssetVersionUpdateRequest,
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


@router.get("/http-assets/{asset_id}", response_model=HTTPAssetDetailResponse)
async def get_http_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTTPAssetDetailResponse:
    """读取单个 HTTP 资产详情。"""
    try:
        result = AssetService(db=db).get_http_asset(asset_id, user)
        return HTTPAssetDetailResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/http-assets/{asset_id}/template-references",
    response_model=list[AssetTemplateReferenceResponse],
)
async def list_http_asset_template_references(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssetTemplateReferenceResponse]:
    """列出引用某个 HTTP 资产的模板版本摘要。"""
    try:
        result = AssetService(db=db).list_http_asset_template_references(asset_id, user)
        return [AssetTemplateReferenceResponse(**item) for item in result]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.put("/http-assets/{asset_id}", response_model=HTTPAssetDetailResponse)
async def update_http_asset(
    asset_id: int,
    request: HTTPAssetUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTTPAssetDetailResponse:
    """更新 HTTP 资产。"""
    try:
        result = AssetService(db=db).update_http_asset(
            asset_id=asset_id,
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
        return HTTPAssetDetailResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/http-assets/{asset_id}", response_model=AssetDeleteResponse)
async def delete_http_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssetDeleteResponse:
    """删除 HTTP 资产。"""
    try:
        result = AssetService(db=db).delete_http_asset(asset_id, user)
        return AssetDeleteResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/http-assets/{asset_id}/test", response_model=HTTPAssetTestResponse)
async def test_http_asset(
    asset_id: int,
    request: HTTPAssetTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HTTPAssetTestResponse:
    """测试某个 HTTP 资产。"""
    try:
        result = AssetService(db=db).test_http_asset(
            asset_id=asset_id,
            user=user,
            query_params=request.query_params,
            headers=request.headers,
            body=request.body,
            response_extraction_rules=request.response_extraction_rules,
        )
        return HTTPAssetTestResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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


@router.get(
    "/sql-assets/{asset_id}/versions",
    response_model=list[SQLAssetVersionSummaryResponse],
)
async def list_sql_asset_versions(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SQLAssetVersionSummaryResponse]:
    """列出某个 SQL 资产的全部版本。"""
    try:
        result = AssetService(db=db).list_sql_asset_versions(asset_id, user)
        return [SQLAssetVersionSummaryResponse(**item) for item in result]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/sql-assets/{asset_id}/template-references",
    response_model=list[AssetTemplateReferenceResponse],
)
async def list_sql_asset_template_references(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssetTemplateReferenceResponse]:
    """列出引用某个 SQL 逻辑资产的模板版本摘要。"""
    try:
        result = AssetService(db=db).list_sql_asset_template_references(asset_id, user)
        return [AssetTemplateReferenceResponse(**item) for item in result]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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


@router.delete("/sql-assets/{asset_id}", response_model=AssetDeleteResponse)
async def delete_sql_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssetDeleteResponse:
    """删除 SQL 逻辑资产。"""
    try:
        result = AssetService(db=db).delete_sql_asset(asset_id, user)
        return AssetDeleteResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.put("/sql-assets/{asset_id}", response_model=SQLAssetSummaryResponse)
async def update_sql_asset(
    asset_id: int,
    request: SQLAssetUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetSummaryResponse:
    """更新 SQL 逻辑资产元信息。"""
    try:
        result = AssetService(db=db).update_sql_asset(
            asset_id=asset_id,
            user=user,
            name=request.name,
            description=request.description,
            system_short=request.system_short,
        )
        return SQLAssetSummaryResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/sql-assets/{asset_id}/versions",
    response_model=SQLAssetVersionCreateResponse,
)
async def create_sql_asset_version(
    asset_id: int,
    request: SQLAssetVersionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionCreateResponse:
    """为 SQL 资产新增草稿版本。"""
    try:
        result = AssetService(db=db).create_sql_asset_version(
            asset_id=asset_id,
            user=user,
            connection_config=request.connection_config,
            whitelist=request.whitelist,
            blacklist=request.blacklist,
            mutation_enabled=request.mutation_enabled,
        )
        return SQLAssetVersionCreateResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/sql-asset-versions/{version_id}",
    response_model=SQLAssetVersionDetailResponse,
)
async def get_sql_asset_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionDetailResponse:
    """读取单个 SQL 资产版本详情。"""
    try:
        result = AssetService(db=db).get_sql_asset_version_detail(version_id, user)
        return SQLAssetVersionDetailResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch(
    "/sql-asset-versions/{version_id}",
    response_model=SQLAssetVersionDetailResponse,
)
async def update_sql_asset_version(
    version_id: int,
    request: SQLAssetVersionUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionDetailResponse:
    """更新 SQL 资产草稿版本。"""
    try:
        result = AssetService(db=db).update_sql_asset_version(
            version_id=version_id,
            user=user,
            connection_config=request.connection_config,
            whitelist=request.whitelist,
            blacklist=request.blacklist,
            mutation_enabled=request.mutation_enabled,
        )
        return SQLAssetVersionDetailResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/sql-asset-versions/{version_id}/copy",
    response_model=SQLAssetVersionCreateResponse,
)
async def copy_sql_asset_version(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionCreateResponse:
    """基于已有 SQL 资产版本复制一个新草稿版本。"""
    try:
        result = AssetService(db=db).copy_sql_asset_version(version_id, user)
        return SQLAssetVersionCreateResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/sql-asset-versions/{version_id}/test",
    response_model=SQLAssetVersionTestResponse,
)
async def test_sql_asset_version(
    version_id: int,
    request: SQLAssetVersionTestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SQLAssetVersionTestResponse:
    """测试 SQL 资产版本连接或查询。"""
    try:
        result = AssetService(db=db).test_sql_asset_version(
            version_id=version_id,
            user=user,
            test_mode=request.test_mode,
            sql=request.sql,
            params=request.params,
        )
        return SQLAssetVersionTestResponse(**result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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
