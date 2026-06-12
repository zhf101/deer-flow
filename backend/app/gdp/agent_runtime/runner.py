"""GDP Agent Runtime MVP 主循环。

串联 flow → execution → evidence → verdict → apply_verdict 的完整链路。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .flow import create_input_variables, create_single_step, make_scene_action
from .log_text import (
    describe_bool,
    describe_code,
    describe_content,
    describe_facts,
    describe_name_list,
    describe_optional,
    describe_variables,
)
from .models import Action, ActionAttempt, ActionStatus, AttemptStatus, StepStatus, TaskRun, TaskRunStatus
from .store import Store
from .transitions import transition_action, transition_step, transition_task_run

logger = logging.getLogger(__name__)

_PENDING_START_REF_PREFIX = "ref:agent-runtime/pending-start"
_REQUIRED_INPUTS_BY_SCENE: dict[str, tuple[str, ...]] = {
    "create_paid_order": ("buyer_id",),
}


class StartTaskRunRequestLike(Protocol):
    """启动请求的最小结构，避免 runner 反向依赖 API 层。"""

    scene_code: str
    inputs: dict[str, Any]


def pending_start_ref(task_run_id: str) -> str:
    """返回待补充启动请求的固定存储引用。"""
    return f"{_PENDING_START_REF_PREFIX}/{task_run_id}"


async def run_task(task_run: TaskRun, request: StartTaskRunRequestLike, store: Store) -> TaskRun:
    """MVP 主循环：执行单个 Scene 并判定结果。"""
    from .evidence import build_evidence
    from .execution import run_action
    from .verdict import apply_verdict, judge

    logger.info(
        "GDP Agent 运行时任务开始运行：任务ID=%s，原状态=%s，场景编码=%s，输入内容=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        request.scene_code,
        describe_content(request.inputs),
    )

    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    logger.info(
        "GDP Agent 运行时任务状态已推进：任务ID=%s，状态=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
    )

    store.save_payload(
        pending_start_ref(task_run.task_run_id),
        {"scene_code": request.scene_code, "inputs": request.inputs},
    )
    missing_fields = _missing_required_start_fields(task_run, request)
    if missing_fields:
        task_run.pending_question = _format_missing_required_question(missing_fields)
        task_run = transition_task_run(task_run, TaskRunStatus.WAITING_USER)
        store.save_task_run(task_run)
        logger.info(
            "GDP Agent 运行时启动前置校验未通过，等待用户补充：任务ID=%s，缺失字段=%s，待用户确认=%s",
            task_run.task_run_id,
            describe_name_list(missing_fields),
            describe_optional(task_run.pending_question),
        )
        return task_run

    task_run.pending_question = None

    step = create_single_step(task_run)
    logger.info(
        "GDP Agent 运行时计划步骤已创建：任务ID=%s，步骤ID=%s，步骤序号=%s，任务目标=%s，形成依据=%s",
        task_run.task_run_id,
        step.step_id,
        step.step_no,
        step.goal,
        "MVP 单步骤规划，直接继承用户原始目标",
    )

    action = make_scene_action(step, request.scene_code, request.inputs)
    logger.info(
        "GDP Agent 运行时执行动作已计划：任务ID=%s，步骤ID=%s，动作ID=%s，动作类型=%s，场景编码=%s，输入摘要=%s，是否需要审批=%s，形成依据=%s",
        task_run.task_run_id,
        step.step_id,
        action.action_id,
        describe_code(action.action_type),
        action.scene_code,
        describe_content(action.input_preview),
        describe_bool(action.approval_required),
        "启动请求显式指定场景编码和输入参数",
    )

    variables = create_input_variables(task_run, step, request.inputs)
    logger.info(
        "GDP Agent 运行时输入变量已生成：任务ID=%s，步骤ID=%s，变量=%s",
        task_run.task_run_id,
        step.step_id,
        describe_variables(variables),
    )

    store.save_payload(action.input_ref, request.inputs)
    # TODO 这里输入载荷是什么意思？
    logger.info(
        "GDP Agent 运行时输入载荷已保存：任务ID=%s，动作ID=%s，输入引用=%s",
        task_run.task_run_id,
        action.action_id,
        action.input_ref,
    )

    step = transition_step(step, StepStatus.RUNNING)
    action = transition_action(action, ActionStatus.RUNNING)
    logger.info(
        "GDP Agent 运行时步骤和动作已进入运行中：任务ID=%s，步骤ID=%s，步骤状态=%s，动作ID=%s，动作状态=%s",
        task_run.task_run_id,
        step.step_id,
        describe_code(step.status),
        action.action_id,
        describe_code(action.status),
    )

    store.save_task_run(task_run)
    store.save_step(step)
    store.save_action(action)
    for variable in variables:
        store.save_variable(variable)
    logger.info(
        "GDP Agent 运行时初始账本已写入存储：任务ID=%s，步骤ID=%s，动作ID=%s，变量=%s",
        task_run.task_run_id,
        step.step_id,
        action.action_id,
        describe_variables(variables),
    )

    attempt, observation = await run_action(action, store)
    action = _sync_action_status_with_attempt(action, attempt)
    store.save_attempt(attempt)
    store.save_observation(observation)
    store.save_action(action)
    logger.info(
        "GDP Agent 运行时动作执行完成：任务ID=%s，动作ID=%s，尝试ID=%s，尝试状态=%s，观察ID=%s，原始结果引用=%s，错误类型=%s，错误信息=%s",
        task_run.task_run_id,
        action.action_id,
        attempt.attempt_id,
        describe_code(attempt.status),
        observation.observation_id,
        observation.raw_ref,
        describe_optional(attempt.error_type),
        describe_optional(attempt.error_message),
    )

    evidence = build_evidence(step, action, observation, attempt)
    store.save_evidence(evidence)
    logger.info(
        "GDP Agent 运行时判定证据已生成：任务ID=%s，证据ID=%s，事实=%s，缺失事实=%s，未知事实=%s",
        task_run.task_run_id,
        evidence.evidence_id,
        describe_facts(evidence.facts),
        describe_name_list(evidence.missing_facts),
        describe_name_list(evidence.unknown_facts),
    )

    verdict = judge(evidence, action)
    store.save_verdict(verdict)
    logger.info(
        "GDP Agent 运行时判定结果已生成：任务ID=%s，判定ID=%s，判定类型=%s，原因=%s",
        task_run.task_run_id,
        verdict.verdict_id,
        describe_code(verdict.verdict_type),
        verdict.reason,
    )

    task_run, step, action = apply_verdict(task_run, step, action, verdict)
    store.save_task_run(task_run)
    store.save_step(step)
    store.save_action(action)
    logger.info(
        "GDP Agent 运行时任务运行结束：任务ID=%s，任务状态=%s，步骤ID=%s，步骤状态=%s，动作ID=%s，动作状态=%s，步骤判定ID=%s，最终判定ID=%s，待用户确认=%s，失败原因=%s",
        task_run.task_run_id,
        describe_code(task_run.status),
        step.step_id,
        describe_code(step.status),
        action.action_id,
        describe_code(action.status),
        describe_optional(step.verdict_id),
        describe_optional(task_run.final_verdict_id),
        describe_optional(task_run.pending_question),
        describe_optional(task_run.failure_reason),
    )

    return task_run


def _missing_required_start_fields(task_run: TaskRun, request: StartTaskRunRequestLike) -> list[str]:
    missing_fields: list[str] = []
    if _is_blank(task_run.env_code):
        missing_fields.append("env_code")

    required_inputs = _REQUIRED_INPUTS_BY_SCENE.get(request.scene_code, ())
    for field_name in required_inputs:
        if _is_blank(request.inputs.get(field_name)):
            missing_fields.append(f"inputs.{field_name}")

    return missing_fields


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _format_missing_required_question(missing_fields: list[str]) -> str:
    return "缺少必填信息：" + "，".join(missing_fields) + "。请补充后继续。"


def _sync_action_status_with_attempt(action: Action, attempt: ActionAttempt) -> Action:
    if action.status != ActionStatus.RUNNING:
        return action
    if attempt.status == AttemptStatus.SUCCEEDED:
        return transition_action(action, ActionStatus.SUCCEEDED)
    if attempt.status == AttemptStatus.FAILED:
        return transition_action(action, ActionStatus.FAILED)
    if attempt.status == AttemptStatus.UNKNOWN_STATE:
        return transition_action(action, ActionStatus.UNKNOWN_STATE)
    return action
