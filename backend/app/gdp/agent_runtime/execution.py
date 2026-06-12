"""GDP Agent Runtime 执行层。

run_action() 是唯一允许产生外部副作用的函数。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from .log_text import describe_code, describe_content, describe_optional
from .models import (
    Action,
    ActionAttempt,
    AttemptStatus,
    Observation,
)
from .store import Store

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _extract_failure_reason(result: dict) -> str:
    """从场景结果里挖出对用户最友好的失败原因。

    Scene 的失败原因散在多层，越往里越友好。按“友好度”优先级取：
    1. businessResult.reason —— 业务规则判失败的精确原因（如“命中失败规则: 余额不足”）
    2. 步骤的 rawResponse.error.detail —— 执行器写的中文排查提示
       （如“无法连接到目标服务器，请检查服务器地址、端口是否正确”）
    3. 步骤的 rawResponse.error.message —— 退而求其次的英文原文
    4. errors[] —— 顶层错误摘要，通常是机器味的英文
    5. 兜底文案
    踩坑点：此前只取了第 4 层，把第 2 层的友好中文白白丢了，用户只能看到
    “All connection attempts failed”这种堆栈味的英文。
    """
    business = result.get("businessResult") or {}
    if business.get("reason"):
        return str(business["reason"])

    for step in result.get("stepResults") or []:
        error = ((step or {}).get("rawResponse") or {}).get("error") or {}
        if error.get("detail"):
            return str(error["detail"])
        if error.get("message"):
            return str(error["message"])

    errors = result.get("errors") or []
    if errors:
        return "；".join(str(item) for item in errors)

    return "场景执行失败"


async def run_action(action: Action, store: Store) -> tuple[ActionAttempt, Observation]:
    """调用 datagen Scene 并记录原始观察。

    MVP 阶段通过 adapters/scene.py 调用已有 Scene 执行器。
    """
    from .adapters.scene import call_scene

    attempt_id = _gen_id("att")
    attempt_no = len(action.attempt_ids) + 1
    started_at = _now()
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
        started_at=started_at,
    )
    action.attempt_ids.append(attempt_id)

    try:
        if store.has_started_idempotency_key(action.idempotency_key, exclude_action_id=action.action_id):
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

        inputs = store.get_payload(action.input_ref)
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
        status = str(result.get("status", "")).upper()
        attempt.status = AttemptStatus.SUCCEEDED if status == "SUCCESS" else AttemptStatus.FAILED
        attempt.response_ref = f"ref:responses/{attempt_id}"
        attempt.response_preview = result
        if attempt.status == AttemptStatus.FAILED:
            attempt.error_type = "SCENE_FAILED"
            # 取“人能看懂”的失败原因，不要把机器味的英文丢给用户。
            # 见 _extract_failure_reason：优先级是 业务规则原因 > 步骤级友好 detail
            # > 步骤名+错误 > 顶层 errors > 兜底。
            attempt.error_message = _extract_failure_reason(result)[:256]
        attempt.finished_at = _now()
        logger.info(
            "GDP Agent 运行时场景调用完成：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，场景状态=%s，尝试状态=%s，响应摘要=%s，错误类型=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            describe_code(status),
            describe_code(attempt.status),
            describe_content(result),
            describe_optional(attempt.error_type),
            describe_optional(attempt.error_message),
        )
    except IdempotencyConflictError as exc:
        attempt.status = AttemptStatus.FAILED
        attempt.error_type = "IDEMPOTENCY_CONFLICT"
        attempt.error_message = str(exc)[:256]
        attempt.finished_at = _now()
        logger.warning(
            "GDP Agent 运行时幂等冲突已转为失败尝试：任务ID=%s，动作ID=%s，尝试ID=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            attempt.error_message,
        )
    except TimeoutError:
        attempt.status = AttemptStatus.UNKNOWN_STATE
        attempt.error_type = "TIMEOUT"
        attempt.error_message = "请求超时，副作用未知"
        attempt.finished_at = _now()
        logger.warning(
            "GDP Agent 运行时场景调用超时，状态转为结果未知：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
        )
    except ConnectionError:
        attempt.status = AttemptStatus.UNKNOWN_STATE
        attempt.error_type = "CONNECTION_ERROR"
        attempt.error_message = "连接断开，副作用未知"
        attempt.finished_at = _now()
        logger.warning(
            "GDP Agent 运行时场景连接断开，状态转为结果未知：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
        )
    except ValueError as exc:
        attempt.status = AttemptStatus.FAILED
        attempt.error_type = type(exc).__name__
        attempt.error_message = str(exc)[:256]
        attempt.finished_at = _now()
        logger.warning(
            "GDP Agent 运行时场景调用校验失败，状态转为失败：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            attempt.error_message,
        )
    except Exception as exc:
        attempt.status = AttemptStatus.FAILED
        attempt.error_type = type(exc).__name__
        attempt.error_message = str(exc)[:256]
        attempt.finished_at = _now()
        logger.exception(
            "GDP Agent 运行时场景调用异常，状态转为失败：任务ID=%s，动作ID=%s，尝试ID=%s，场景编码=%s，错误类型=%s，错误信息=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            describe_optional(attempt.error_type),
            describe_optional(attempt.error_message),
        )

    # 观察摘要要保留场景的结构化结果（含 businessResult / finalOutput），
    # 失败时也不例外：build_evidence 需要凭 businessResult 抽取精确失败事实。
    # 仅当连结构化 result 都没有（超时/连接断开等未知态）时，才退化成纯错误摘要。
    if attempt.response_preview:
        preview = attempt.response_preview
    else:
        preview = {"error": attempt.error_message}

    observation = Observation(
        observation_id=_gen_id("obs"),
        task_run_id=action.task_run_id,
        action_id=action.action_id,
        attempt_id=attempt_id,
        raw_ref=attempt.response_ref or f"ref:errors/{attempt_id}",
        preview=preview,
        created_at=_now(),
    )
    logger.info(
        "GDP Agent 运行时观察结果已生成：任务ID=%s，动作ID=%s，尝试ID=%s，观察ID=%s，原始结果引用=%s，观察摘要=%s",
        action.task_run_id,
        action.action_id,
        attempt_id,
        observation.observation_id,
        observation.raw_ref,
        describe_content(observation.preview),
    )

    return attempt, observation


class IdempotencyConflictError(RuntimeError):
    """幂等键冲突。"""
