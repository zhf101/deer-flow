from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/templates", tags=["datamakepool"])


@router.post("/from-run")
async def create_template_from_run() -> dict:
    return {"status": "not_implemented"}


@router.get("")
async def list_templates() -> dict:
    return {"status": "not_implemented"}


@router.get("/{template_id}/revisions")
async def list_template_revisions(template_id: int) -> dict:
    return {"template_id": template_id, "status": "not_implemented"}


@router.post("/revisions/{revision_id}/submit-review")
async def submit_template_review(revision_id: int) -> dict:
    return {"revision_id": revision_id, "status": "not_implemented"}


@router.post("/revisions/{revision_id}/approve")
async def approve_template_revision(revision_id: int) -> dict:
    return {"revision_id": revision_id, "status": "not_implemented"}
