from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models.database import get_db
from ...schemas.datamakepool import FlowDraftResponse, TrialRequest, TrialResponse
from ...auth_dependencies import get_current_user
from ...models.user import User
from ....core.datamakepool.flowdraft import FlowDraftService
from ....core.datamakepool.orchestration import RunRuntimeBridge
from ....core.datamakepool.runs import RunService

router = APIRouter(prefix="/api/datamakepool/flowdrafts", tags=["datamakepool"])


@router.get("/{flowdraft_id}", response_model=FlowDraftResponse)
async def get_flowdraft(
    flowdraft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlowDraftResponse:
    """获取单个 FlowDraft。

    当前只返回骨架响应，后续会接入 FlowDraftService 和真实数据库查询。
    """
    del user
    try:
        data = FlowDraftService(db=db).get_flowdraft(flowdraft_id)
        return FlowDraftResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{flowdraft_id}/resolve")
async def resolve_flowdraft(flowdraft_id: int) -> dict:
    """触发整份 FlowDraft 的收敛流程。"""
    return {"flowdraft_id": flowdraft_id, "status": "not_implemented"}


@router.post("/{flowdraft_id}/preflight")
async def preflight_flowdraft(
    flowdraft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """执行 FlowDraft 试跑前预检。"""
    del user
    try:
        return FlowDraftService(db=db).get_preflight(flowdraft_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{flowdraft_id}/trial", response_model=TrialResponse)
async def trial_flowdraft(
    flowdraft_id: int,
    request: TrialRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TrialResponse:
    """触发 FlowDraft 的 trial run。"""
    try:
        flowdraft_service = FlowDraftService(db=db)
        flowdraft = flowdraft_service.get_flowdraft(flowdraft_id)
        run_service = RunService(db=db, runtime_bridge=RunRuntimeBridge())
        result = run_service.create_run(
            entry_type=request.entry_type,
            initiator_user_id=request.initiator_user_id or int(user.id),
            task_id=flowdraft["task_id"],
            system_short=request.system_short,
            objective=flowdraft.get("objective"),
            input_payload=flowdraft.get("input_schema_draft"),
            resolved_input=flowdraft.get("output_mapping_draft"),
            technical_graph=flowdraft.get("technical_graph"),
        )
        return TrialResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
