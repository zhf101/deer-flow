from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models.database import get_db
from ...schemas.datamakepool import (
    FlowDraftDiffResponse,
    FlowDraftResponse,
    FlowDraftSnapshotResponse,
    FlowDraftStepPatchRequest,
    FlowDraftStepPatchResponse,
    FlowDraftStepResolveResponse,
    TrialRequest,
    TrialResponse,
)
from ...auth_dependencies import get_current_user
from ...models.user import User
from ....core.datamakepool.governance import GovernanceService
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
    try:
        data = FlowDraftService(db=db).get_flowdraft(flowdraft_id, user)
        return FlowDraftResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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
    try:
        return FlowDraftService(db=db).get_preflight(flowdraft_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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
        governance_service = GovernanceService(db=db)
        initiator_user_id = governance_service.assert_initiator_override_allowed(
            request.initiator_user_id,
            user,
        )
        flowdraft = flowdraft_service.get_flowdraft(flowdraft_id, user)
        preflight_result = flowdraft_service.get_preflight(flowdraft_id, user)
        if not preflight_result.get("is_runnable", False):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "FlowDraft preflight blocked trial execution",
                    "preflight": preflight_result,
                },
            )
        run_service = RunService(db=db, runtime_bridge=RunRuntimeBridge())
        created = run_service.create_run(
            entry_type=request.entry_type,
            initiator_user_id=initiator_user_id,
            task_id=flowdraft["task_id"],
            system_short=request.system_short,
            objective=flowdraft.get("objective"),
            input_payload=flowdraft.get("input_schema_draft"),
            resolved_input=flowdraft.get("output_mapping_draft"),
            technical_graph=flowdraft.get("technical_graph"),
        )
        executed = run_service.execute_trial(
            run_id=created["run_id"],
            technical_graph=flowdraft.get("technical_graph") or {},
            input_payload=flowdraft.get("input_schema_draft"),
            resolved_input=flowdraft.get("output_mapping_draft"),
        )
        result = {
            **created,
            **executed,
            "entry_type": created["entry_type"],
            "created_steps": created["created_steps"],
            "runtime": created["runtime"],
        }
        return TrialResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{flowdraft_id}/snapshots", response_model=list[FlowDraftSnapshotResponse])
async def list_flowdraft_snapshots(
    flowdraft_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FlowDraftSnapshotResponse]:
    """列出 FlowDraft 的关键版本快照。"""
    try:
        result = FlowDraftService(db=db).list_snapshots(flowdraft_id, user)
        return [FlowDraftSnapshotResponse(**item) for item in result]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{flowdraft_id}/diff", response_model=FlowDraftDiffResponse)
async def diff_flowdraft(
    flowdraft_id: int,
    before_snapshot_id: int | None = None,
    after_snapshot_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlowDraftDiffResponse:
    """查看 FlowDraft 版本差异。"""
    try:
        result = FlowDraftService(db=db).diff_flowdraft(
            flowdraft_id=flowdraft_id,
            user=user,
            before_snapshot_id=before_snapshot_id,
            after_snapshot_id=after_snapshot_id,
        )
        return FlowDraftDiffResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/{flowdraft_id}/steps/{step_id}", response_model=FlowDraftStepPatchResponse)
async def patch_flowdraft_step(
    flowdraft_id: int,
    step_id: str,
    request: FlowDraftStepPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlowDraftStepPatchResponse:
    """更新单个步骤的可编辑字段。

    后续这里会按 editable_fields 规则区分：直接编辑还是标记 needs_resolution。
    """
    try:
        result = FlowDraftService(db=db).patch_flowdraft_step(
            flowdraft_id=flowdraft_id,
            step_id=step_id,
            changes=request.changes,
            user=user,
        )
        return FlowDraftStepPatchResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/{flowdraft_id}/steps/{step_id}/resolve",
    response_model=FlowDraftStepResolveResponse,
)
async def resolve_flowdraft_step(
    flowdraft_id: int,
    step_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FlowDraftStepResolveResponse:
    """只对单个步骤触发局部重收敛。"""
    try:
        result = FlowDraftService(db=db).resolve_flowdraft_step(
            flowdraft_id=flowdraft_id,
            step_id=step_id,
            user=user,
        )
        return FlowDraftStepResolveResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
