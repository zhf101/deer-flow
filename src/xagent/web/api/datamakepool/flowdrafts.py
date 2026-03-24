from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/flowdrafts", tags=["datamakepool"])


@router.get("/{flowdraft_id}")
async def get_flowdraft(flowdraft_id: int) -> dict:
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/resolve")
async def resolve_flowdraft(flowdraft_id: int) -> dict:
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/preflight")
async def preflight_flowdraft(flowdraft_id: int) -> dict:
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/trial")
async def trial_flowdraft(flowdraft_id: int) -> dict:
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.get("/{flowdraft_id}/snapshots")
async def list_flowdraft_snapshots(flowdraft_id: int) -> dict:
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.get("/{flowdraft_id}/diff")
async def diff_flowdraft(flowdraft_id: int) -> dict:
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.patch("/{flowdraft_id}/steps/{step_id}")
async def patch_flowdraft_step(flowdraft_id: int, step_id: str) -> dict:
    return {
        "flowdraft_id": flowdraft_id,
        "step_id": step_id,
        "status": "not_implemented",
    }


@router.post("/{flowdraft_id}/steps/{step_id}/resolve")
async def resolve_flowdraft_step(flowdraft_id: int, step_id: str) -> dict:
    return {
        "flowdraft_id": flowdraft_id,
        "step_id": step_id,
        "status": "not_implemented",
    }
