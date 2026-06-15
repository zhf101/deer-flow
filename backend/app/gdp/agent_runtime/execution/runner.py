"""场景动作执行。"""

from __future__ import annotations

import logging

from ..ledger.memory import MemoryLedger
from ..models import Action, ActionAttempt, AttemptStatus, Observation
from ..ports.idempotency import IdempotencyGate
from ..support.log_text import describe_code, describe_content, describe_optional
from .failure_reason import extract_failure_reason
from .ids import gen_id, now
from .observation import build_observation

logger = logging.getLogger(__name__)


async def run_action(
    action: Action,
    store: MemoryLedger,
    idempotency_gate: IdempotencyGate | None = None,
) -> tuple[ActionAttempt, Observation]:
    """执行一次造数场景调用，记录尝试过程和观察结果。"""
    from ..adapters.scene import call_scene

    attempt_id = gen_id("att")
    attempt_no = len(action.attempt_ids) + 1
    logger.info(
        "GDP Agent 运行时动作尝试开始：任务ID=%s，动作ID=%s，尝试ID=%s，第几次尝试=%s，场景编码=%s，输入引用=%s",
        action.task_run_id,
        action.action_id,
        attempt_id,
        attempt_no,
        action.scene_code,
        action.input_ref,
    )

    attempt = ActionAttempt(
        attempt_id=attempt_id,
        action_id=action.action_id,
        attempt_no=attempt_no,
        status=AttemptStatus.RUNNING,
        request_ref=f"ref:requests/{attempt_id}",
        started_at=now(),
    )
    action.attempt_ids.append(attempt_id)

    try:
        has_memory_conflict = store.has_started_idempotency_key(action.idempotency_key, exclude_action_id=action.action_id)
        has_external_conflict = False
        if idempotency_gate is not None:
            has_external_conflict = await idempotency_gate(action.task_run_id, action.action_id, action.idempotency_key)

        if has_memory_conflict or has_external_conflict:
            logger.warning(
                "GDP Agent 运行时幂等检查失败，拒绝重复执行：任务ID=%s，动作ID=%s，幂等键=%s",
                action.task_run_id,
                action.action_id,
                action.idempotency_key,
            )
            raise IdempotencyConflictError(f"幂等键已发起过写请求：{action.idempotency_key}")

        task_run = store.get_task_run(action.task_run_id)
        if not task_run.env_code:
            logger.warning(
                "GDP Agent 运行时场景调用前校验失败，缺少环境：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s",
                action.task_run_id,
                action.action_id,
                attempt_id,
                action.scene_code,
            )
            raise ValueError("任务缺少环境编码，不能执行场景")

        inputs = store.get_payload(action.task_run_id, action.input_ref)
        store.save_payload(
            action.task_run_id,
            attempt.request_ref,
            {
                "scene_code": action.scene_code,
                "env_code": task_run.env_code,
                "inputs": inputs,
            },
        )
        logger.info(
            "GDP Agent 运行时场景调用开始：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，环境=%s，输入内容=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            describe_optional(task_run.env_code),
            describe_content(inputs),
        )
        result = await call_scene(action.scene_code, task_run.env_code, inputs)
        _apply_scene_result(action, attempt, result, store)
        logger.info(
            "GDP Agent 运行时场景调用完成：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，场景状态=%s，尝试状态=%s，响应摘要=%s，错误类型=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            describe_code(str(result.get("status", "")).upper()),
            describe_code(attempt.status),
            describe_content(result),
            describe_optional(attempt.error_type),
            describe_optional(attempt.error_message),
        )
    except IdempotencyConflictError as exc:
        _mark_failed_attempt(attempt, "IDEMPOTENCY_CONFLICT", str(exc))
        logger.warning(
            "GDP Agent 运行时幂等冲突已转为失败尝试：任务ID=%s，动作ID=%s，尝试ID=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            attempt.error_message,
        )
    except TimeoutError:
        _mark_unknown_attempt(attempt, "TIMEOUT", "请求超时，副作用未知")
        logger.warning(
            "GDP Agent 运行时场景调用超时，状态转为结果未知：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
        )
    except ConnectionError:
        _mark_unknown_attempt(attempt, "CONNECTION_ERROR", "连接断开，副作用未知")
        logger.warning(
            "GDP Agent 运行时场景连接断开，状态转为结果未知：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
        )
    except ValueError as exc:
        _mark_failed_attempt(attempt, type(exc).__name__, str(exc))
        logger.warning(
            "GDP Agent 运行时场景调用校验失败，状态转为失败：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            attempt.error_message,
        )
    except Exception as exc:
        _mark_failed_attempt(attempt, type(exc).__name__, str(exc))
        logger.exception(
            "GDP Agent 运行时场景调用异常，状态转为失败：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，错误类型=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            describe_optional(attempt.error_type),
            describe_optional(attempt.error_message),
        )

    observation = build_observation(action, attempt, store)
    return attempt, observation


def _apply_scene_result(action: Action, attempt: ActionAttempt, result: dict, store: MemoryLedger) -> None:
    """把场景响应写回尝试记录和 payload。"""

    status = str(result.get("status", "")).upper()
    attempt.status = AttemptStatus.SUCCEEDED if status == "SUCCESS" else AttemptStatus.FAILED
    attempt.response_ref = f"ref:responses/{attempt.attempt_id}"
    scene_run_id = result.get("runId")
    if isinstance(scene_run_id, str) and scene_run_id:
        attempt.scene_run_id = scene_run_id
    attempt.response_preview = result
    store.save_payload(action.task_run_id, attempt.response_ref, result)
    if attempt.status == AttemptStatus.FAILED:
        attempt.error_type = "SCENE_FAILED"
        # 造数失败时，用户最需要看到的是一句说得清的中文原因（如”余额不足”），
        # 而不是一段英文堆栈。extract_failure_reason 会按友好程度逐层取值。
        attempt.error_message = extract_failure_reason(result)[:256]
    attempt.finished_at = now()


def _mark_failed_attempt(attempt: ActionAttempt, error_type: str, message: str) -> None:
    """把尝试标记为确定失败。"""

    attempt.status = AttemptStatus.FAILED
    attempt.error_type = error_type
    attempt.error_message = message[:256]
    attempt.finished_at = now()


def _mark_unknown_attempt(attempt: ActionAttempt, error_type: str, message: str) -> None:
    """把尝试标记为结果未知。"""

    attempt.status = AttemptStatus.UNKNOWN_STATE
    attempt.error_type = error_type
    attempt.error_message = message
    attempt.finished_at = now()


class IdempotencyConflictError(RuntimeError):
    """幂等键冲突——防止重复造数。"""
