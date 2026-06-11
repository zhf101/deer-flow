"""GDP Agent Runtime MVP 主循环。

串联 flow → execution → evidence → verdict → apply_verdict 的完整链路。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .flow import create_input_variables, create_single_step, make_scene_action
from .models import ActionStatus, StepStatus, TaskRun, TaskRunStatus
from .store import Store
from .transitions import transition_action, transition_step, transition_task_run

logger = logging.getLogger(__name__)


class StartTaskRunRequestLike(Protocol):
    """启动请求的最小结构，避免 runner 反向依赖 API 层。"""

    scene_code: str
    inputs: dict[str, Any]


async def run_task(task_run: TaskRun, request: StartTaskRunRequestLike, store: Store) -> TaskRun:
    """MVP 主循环：执行单个 Scene 并判定结果。"""
    from .evidence import build_evidence
    from .execution import run_action
    from .verdict import apply_verdict, judge

    logger.info(
        "GDP Agent Runtime TaskRun 开始运行: task_run_id=%s from_status=%s scene_code=%s input_keys=%s input_count=%s",
        task_run.task_run_id,
        task_run.status,
        request.scene_code,
        sorted(request.inputs.keys()),
        len(request.inputs),
    )

    task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
    logger.info(
        "GDP Agent Runtime TaskRun 状态已推进: task_run_id=%s status=%s",
        task_run.task_run_id,
        task_run.status,
    )

    step = create_single_step(task_run)
    logger.info(
        "GDP Agent Runtime PlanStep 已创建: task_run_id=%s step_id=%s step_no=%s goal_length=%s",
        task_run.task_run_id,
        step.step_id,
        step.step_no,
        len(step.goal),
    )

    action = make_scene_action(step, request.scene_code, request.inputs)
    logger.info(
        "GDP Agent Runtime Action 已计划: task_run_id=%s step_id=%s action_id=%s scene_code=%s input_hash=%s approval_required=%s",
        task_run.task_run_id,
        step.step_id,
        action.action_id,
        action.scene_code,
        action.input_hash,
        action.approval_required,
    )

    variables = create_input_variables(task_run, step, request.inputs)
    logger.info(
        "GDP Agent Runtime 输入变量已生成: task_run_id=%s step_id=%s variable_count=%s variable_names=%s",
        task_run.task_run_id,
        step.step_id,
        len(variables),
        [variable.name for variable in variables],
    )

    store.save_payload(action.input_ref, request.inputs)
    logger.info(
        "GDP Agent Runtime 输入载荷已保存: task_run_id=%s action_id=%s input_ref=%s",
        task_run.task_run_id,
        action.action_id,
        action.input_ref,
    )

    step = transition_step(step, StepStatus.RUNNING)
    action = transition_action(action, ActionStatus.RUNNING)
    logger.info(
        "GDP Agent Runtime Step/Action 进入 RUNNING: task_run_id=%s step_id=%s step_status=%s action_id=%s action_status=%s",
        task_run.task_run_id,
        step.step_id,
        step.status,
        action.action_id,
        action.status,
    )

    store.save_task_run(task_run)
    store.save_step(step)
    store.save_action(action)
    for variable in variables:
        store.save_variable(variable)
    logger.info(
        "GDP Agent Runtime 初始账本已落库: task_run_id=%s step_id=%s action_id=%s variable_count=%s",
        task_run.task_run_id,
        step.step_id,
        action.action_id,
        len(variables),
    )

    attempt, observation = await run_action(action, store)
    store.save_attempt(attempt)
    store.save_observation(observation)
    logger.info(
        "GDP Agent Runtime Action 执行完成: task_run_id=%s action_id=%s attempt_id=%s attempt_status=%s observation_id=%s raw_ref=%s error_type=%s error_message=%s",
        task_run.task_run_id,
        action.action_id,
        attempt.attempt_id,
        attempt.status,
        observation.observation_id,
        observation.raw_ref,
        attempt.error_type,
        attempt.error_message,
    )

    evidence = build_evidence(step, action, observation, attempt)
    store.save_evidence(evidence)
    logger.info(
        "GDP Agent Runtime Evidence 已生成: task_run_id=%s evidence_id=%s facts=%s missing_facts=%s unknown_facts=%s",
        task_run.task_run_id,
        evidence.evidence_id,
        len(evidence.facts),
        evidence.missing_facts,
        evidence.unknown_facts,
    )

    verdict = judge(evidence, action)
    store.save_verdict(verdict)
    logger.info(
        "GDP Agent Runtime Verdict 已生成: task_run_id=%s verdict_id=%s verdict_type=%s reason=%s",
        task_run.task_run_id,
        verdict.verdict_id,
        verdict.verdict_type,
        verdict.reason,
    )

    task_run, step, action = apply_verdict(task_run, step, action, verdict)
    store.save_task_run(task_run)
    store.save_step(step)
    store.save_action(action)
    logger.info(
        "GDP Agent Runtime TaskRun 运行结束: task_run_id=%s status=%s step_id=%s step_status=%s action_id=%s action_status=%s final_verdict_id=%s pending_question=%s failure_reason=%s",
        task_run.task_run_id,
        task_run.status,
        step.step_id,
        step.status,
        action.action_id,
        action.status,
        task_run.final_verdict_id,
        task_run.pending_question,
        task_run.failure_reason,
    )

    return task_run
