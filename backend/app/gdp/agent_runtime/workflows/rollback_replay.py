"""MVP6-C 用户选择回退点后的替代任务重放。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..domain.factories import create_task_run
from ..ledger.refs import pending_start_ref
from ..models import TaskRun, TaskRunStatus
from ..store import EntityNotFoundError, Store
from ..support.errors import RuntimeConflictError
from .rollback_plan import build_rollback_plan


class PreparedRollbackReplay(BaseModel):
    """替代任务重放的准备结果。"""

    source_task_run_id: str = Field(description="来源失败任务 ID。")
    replacement_task_run: TaskRun = Field(description="新创建的替代任务。")
    selected_rollback_step_id: str = Field(description="用户选择的回退候选步骤 ID。")
    failed_step_id: str = Field(description="触发回退分析的失败步骤 ID。")
    tainted_variable_ids: list[str] = Field(description="污染变量 ID。")
    affected_step_ids: list[str] = Field(description="受影响步骤 ID。")
    carried_input_names: list[str] = Field(description="从来源启动请求沿用的输入字段名。")
    replay_inputs: dict[str, Any] = Field(description="替代任务启动时使用的输入。")
    scene_code: str | None = Field(default=None, description="替代任务显式场景编码。")
    replay_mode: Literal["REPLACEMENT_TASK_RUN"] = Field(
        default="REPLACEMENT_TASK_RUN",
        description="回退执行模式，当前只支持替代任务重放。",
    )


def prepare_replacement_replay(
    *,
    source_task_run: TaskRun,
    source_store: Store,
    rollback_step_id: str,
    failed_step_id: str | None,
    inputs: dict[str, Any],
    scene_code: str | None,
) -> PreparedRollbackReplay:
    """校验回退计划并创建替代任务；不修改来源失败任务。"""

    if source_task_run.status != TaskRunStatus.FAILED:
        raise RuntimeConflictError("只有 FAILED 任务可以创建回退重放")

    plan = build_rollback_plan(source_task_run, source_store, failed_step_id)
    if rollback_step_id not in plan.rollback_candidate_step_ids:
        raise RuntimeConflictError("rollback_step_id 不在可选回退候选步骤中")

    pending_start = _get_pending_start(source_task_run, source_store)
    base_inputs = dict(pending_start.get("inputs") or {})
    replay_inputs = {**base_inputs, **inputs}
    effective_scene_code = scene_code if scene_code is not None else pending_start.get("scene_code")

    replacement = create_task_run(
        user_goal=source_task_run.user_goal,
        env_code=source_task_run.env_code,
        user_id=source_task_run.user_id,
        thread_id=source_task_run.thread_id,
        recovery_source_task_run_id=source_task_run.task_run_id,
        recovery_selected_step_id=rollback_step_id,
        recovery_failed_step_id=plan.failed_step_id,
    )
    source_store.save_task_run(replacement)

    return PreparedRollbackReplay(
        source_task_run_id=source_task_run.task_run_id,
        replacement_task_run=replacement,
        selected_rollback_step_id=rollback_step_id,
        failed_step_id=plan.failed_step_id,
        tainted_variable_ids=plan.tainted_variable_ids,
        affected_step_ids=plan.affected_step_ids,
        carried_input_names=list(base_inputs.keys()),
        replay_inputs=replay_inputs,
        scene_code=effective_scene_code,
    )


def _get_pending_start(source_task_run: TaskRun, source_store: Store) -> dict[str, Any]:
    try:
        pending_start = source_store.get_payload(
            source_task_run.task_run_id,
            pending_start_ref(source_task_run.task_run_id),
        )
    except EntityNotFoundError as exc:
        raise RuntimeConflictError("来源任务缺少可恢复的启动请求快照") from exc
    if not isinstance(pending_start, dict):
        raise RuntimeConflictError("来源任务启动请求快照格式无效")
    return pending_start
