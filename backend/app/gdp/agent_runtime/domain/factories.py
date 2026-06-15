"""GDP 造数 Agent 运行时——执行计划构建模块。

本模块负责为用户的造数目标建立执行计划——创建任务账本、拆解业务步骤、
准备执行动作和追踪输入变量，是造数流程的起点。

所有函数均为纯函数，不产生外部副作用；它们只做"排兵布阵"，
真正把计划落地执行的工作交给 execution.py。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .action import Action, ActionStatus, ActionType
from .step import PlanStep, StepStatus
from .task import TaskRun, TaskRunStatus
from .variable import Variable, VariableProvenance, VariableSource


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
    """为用户的造数目标创建根账本。

    业务目标：用户提出一个造数需求（如"造一笔已支付订单"），系统需要一本账本
    来记录这个需求的全生命周期。
    当前动作：创建 TaskRun 实例，把用户原话、环境、身份写入账本。
    预期结果：得到一个可追踪的任务根节点，后续所有步骤和动作都挂在它下面。
    """
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
    """把用户目标拆解成可执行的业务步骤。

    业务目标：用户的造数需求需要被拆成一个个可独立执行的步骤，
    每个步骤对应一个具体的业务动作（如"创建订单"、"发起支付"）。
    当前动作：MVP 阶段只创建一个唯一步骤，直接复用任务级目标。
    预期结果：产出一个挂在该任务下的 PlanStep，并更新任务的活跃步骤指针。
    """
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
    """为步骤创建一个待执行的场景动作，准备输入参数和幂等保护。

    业务目标：步骤需要知道"执行哪个场景、用什么参数"才能动手造数；
    同时要防止同一组参数被重复执行，避免用户误操作导致重复创建数据。
    当前动作：组装 Action 实例，把场景编码、输入摘要、输入哈希和幂等键
    一并写入；敏感字段在展示摘要时自动脱敏。
    预期结果：产出一个状态为 PLANNED 的 Action，等待执行引擎调度。
    """
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
    """记录用户提供的输入数据，追踪来源便于后续排查。

    业务目标：造数过程中的每个参数都需要有据可查——谁提供的、什么值、
    是否敏感，这样出问题时能快速定位"是不是入参就错了"。
    当前动作：遍历用户输入，为每个字段创建一个 Variable，标记来源为
    USER_INPUT，敏感字段只存脱敏预览。
    预期结果：产出一组 Variable 记录，并把它们的 ID 挂到步骤的 consumes 列表上。
    """
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
