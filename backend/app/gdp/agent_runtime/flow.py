"""GDP Agent Runtime 核心流程函数。

纯函数，负责创建 TaskRun、PlanStep、Action 和 Variable。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .models import (
    Action,
    ActionStatus,
    ActionType,
    PlanStep,
    StepStatus,
    TaskRun,
    TaskRunStatus,
    Variable,
    VariableProvenance,
    VariableSource,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _hash_inputs(inputs: dict[str, Any]) -> str:
    raw = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _make_input_preview(inputs: dict[str, Any], sensitive_keys: set[str] | None = None) -> dict[str, Any]:
    """生成可展示的输入摘要，敏感字段脱敏。"""
    sensitive_keys = sensitive_keys or set()
    preview: dict[str, Any] = {}
    for key, value in inputs.items():
        if key in sensitive_keys:
            preview[key] = "***"
        else:
            preview[key] = value
    return preview


def create_task_run(
    user_goal: str,
    env_code: str | None = None,
    user_id: str = "anonymous",
    thread_id: str | None = None,
) -> TaskRun:
    """创建 TaskRun 根账本。"""
    now = _now()
    return TaskRun(
        task_run_id=_gen_id("tr"),
        thread_id=thread_id or _gen_id("thread"),
        user_id=user_id,
        user_goal=user_goal,
        env_code=env_code,
        status=TaskRunStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def create_single_step(task_run: TaskRun, goal: str | None = None) -> PlanStep:
    """为 MVP 创建唯一业务步骤。"""
    step_id = _gen_id("step")
    step = PlanStep(
        step_id=step_id,
        task_run_id=task_run.task_run_id,
        step_no=1,
        goal=goal or task_run.user_goal,
        status=StepStatus.PENDING,
    )
    task_run.step_ids.append(step_id)
    task_run.active_step_id = step_id
    return step


def make_scene_action(
    step: PlanStep,
    scene_code: str,
    inputs: dict[str, Any],
    approval_required: bool = False,
    sensitive_keys: set[str] | None = None,
) -> Action:
    """根据显式 scene_code 和 inputs 创建 EXECUTE_SCENE Action。"""
    action_id = _gen_id("act")
    input_hash = _hash_inputs(inputs)
    idempotency_key = f"{step.task_run_id}:{scene_code}:{input_hash}"

    action = Action(
        action_id=action_id,
        task_run_id=step.task_run_id,
        step_id=step.step_id,
        action_type=ActionType.EXECUTE_SCENE,
        status=ActionStatus.PLANNED,
        scene_code=scene_code,
        input_ref=f"ref:inputs/{action_id}",
        input_preview=_make_input_preview(inputs, sensitive_keys),
        input_hash=input_hash,
        idempotency_key=idempotency_key,
        approval_required=approval_required,
    )
    step.action_ids.append(action_id)
    return action


def create_input_variables(
    task_run: TaskRun,
    step: PlanStep,
    inputs: dict[str, Any],
    sensitive_keys: set[str] | None = None,
) -> list[Variable]:
    """为用户输入创建 Variable，追踪 provenance。"""
    sensitive_keys = sensitive_keys or set()
    variables: list[Variable] = []
    now = _now()

    for name, value in inputs.items():
        is_sensitive = name in sensitive_keys
        var_id = _gen_id("var")
        var = Variable(
            variable_id=var_id,
            task_run_id=task_run.task_run_id,
            name=name,
            semantic_type=name.upper(),
            value_ref=f"ref:vars/{var_id}",
            value_preview="***" if is_sensitive else str(value)[:64],
            sensitive=is_sensitive,
            provenance=VariableProvenance(
                source_type=VariableSource.USER_INPUT,
                source_id=task_run.user_id,
            ),
            created_at=now,
        )
        step.consumes.append(var_id)
        variables.append(var)

    return variables
