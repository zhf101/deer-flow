from fastapi import APIRouter

router = APIRouter(prefix="/api/datamakepool/flowdrafts", tags=["datamakepool"])


@router.get("/{flowdraft_id}")
async def get_flowdraft(flowdraft_id: int) -> dict:
    """获取单个 FlowDraft。

    当前只返回骨架响应，后续会接入 FlowDraftService 和真实数据库查询。
    """
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/resolve")
async def resolve_flowdraft(flowdraft_id: int) -> dict:
    """触发整份 FlowDraft 的收敛流程。"""
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/preflight")
async def preflight_flowdraft(flowdraft_id: int) -> dict:
    """执行 FlowDraft 试跑前预检。"""
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/trial")
async def trial_flowdraft(flowdraft_id: int) -> dict:
    """触发 FlowDraft 的 trial run。"""
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.get("/{flowdraft_id}/snapshots")
async def list_flowdraft_snapshots(flowdraft_id: int) -> dict:
    """列出 FlowDraft 的关键版本快照。"""
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.get("/{flowdraft_id}/diff")
async def diff_flowdraft(flowdraft_id: int) -> dict:
    """查看 FlowDraft 版本差异。"""
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.patch("/{flowdraft_id}/steps/{step_id}")
async def patch_flowdraft_step(flowdraft_id: int, step_id: str) -> dict:
    """更新单个步骤的可编辑字段。

    后续这里会按 editable_fields 规则区分：直接编辑还是标记 needs_resolution。
    """
    return {
        "flowdraft_id": flowdraft_id,
        "step_id": step_id,
        "status": "not_implemented",
    }


@router.post("/{flowdraft_id}/steps/{step_id}/resolve")
async def resolve_flowdraft_step(flowdraft_id: int, step_id: str) -> dict:
    """只对单个步骤触发局部重收敛。"""
    return {
        "flowdraft_id": flowdraft_id,
        "step_id": step_id,
        "status": "not_implemented",
    }
