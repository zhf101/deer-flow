from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth_dependencies import get_current_user
from ...models.database import get_db
from ...models.user import User
from ...schemas.datamakepool import (
    CreateTemplateFromRunRequest,
    ReviewResponse,
    TemplateRevisionResponse,
)
from ....core.datamakepool.templates import TemplateService

router = APIRouter(prefix="/api/datamakepool/templates", tags=["datamakepool"])


@router.post("/from-run", response_model=TemplateRevisionResponse)
async def create_template_from_run(
    request: CreateTemplateFromRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateRevisionResponse:
    """从成功 Run 生成模板草稿。"""
    del user
    try:
        result = TemplateService(db=db).create_revision_from_run(
            run_id=request.run_id,
            template_id=request.template_id,
            template_name=request.template_name,
            description=request.description,
            system_short=request.system_short,
            business_graph_snapshot=request.business_graph_snapshot,
            technical_graph=request.technical_graph,
            input_schema=request.input_schema,
            output_mapping=request.output_mapping,
        )
        return TemplateRevisionResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
async def list_templates() -> dict:
    """列出模板逻辑对象。"""
    return {"status": "not_implemented"}


@router.get("/{template_id}/revisions")
async def list_template_revisions(template_id: int) -> dict:
    """列出某个模板的全部版本。"""
    return {"template_id": template_id, "status": "not_implemented"}


@router.post("/revisions/{revision_id}/submit-review", response_model=ReviewResponse)
async def submit_template_review(
    revision_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewResponse:
    """提交模板版本审核。"""
    del user
    try:
        result = TemplateService(db=db).submit_review(revision_id)
        return ReviewResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/revisions/{revision_id}/approve")
async def approve_template_revision(revision_id: int) -> dict:
    """审批通过模板版本。"""
    return {"revision_id": revision_id, "status": "not_implemented"}
