"""GDP Agent Runtime 执行层。

run_action() 是唯一允许产生外部副作用的函数。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

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


async def run_action(action: Action, store: Store) -> tuple[ActionAttempt, Observation]:
    """调用 datagen Scene 并记录原始观察。

    MVP 阶段通过 adapters/scene.py 调用已有 Scene 执行器。
    """
    from .adapters.scene import call_scene

    if store.has_started_idempotency_key(action.idempotency_key, exclude_action_id=action.action_id):
        logger.warning(
            "GDP Agent Runtime 幂等检查失败，拒绝重复执行: task_run_id=%s action_id=%s idempotency_key=%s",
            action.task_run_id,
            action.action_id,
            action.idempotency_key,
        )
        raise RuntimeError(f"幂等键已发起过写请求: {action.idempotency_key}")

    attempt_id = _gen_id("att")
    attempt_no = len(action.attempt_ids) + 1
    started_at = _now()
    logger.info(
        "GDP Agent Runtime Action Attempt 开始: task_run_id=%s action_id=%s attempt_id=%s attempt_no=%s scene_code=%s input_ref=%s",
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
        task_run = store.get_task_run(action.task_run_id)
        if not task_run.env_code:
            logger.warning(
                "GDP Agent Runtime Scene 调用前校验失败，缺少环境: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s",
                action.task_run_id,
                action.action_id,
                attempt_id,
                action.scene_code,
            )
            raise ValueError("TaskRun 缺少 env_code，不能执行 Scene")

        inputs = store.get_payload(action.input_ref)
        logger.info(
            "GDP Agent Runtime Scene 调用开始: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s env_code=%s input_keys=%s input_count=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            task_run.env_code,
            sorted(inputs.keys()) if isinstance(inputs, dict) else [],
            len(inputs) if isinstance(inputs, dict) else 0,
        )
        result = await call_scene(action.scene_code, task_run.env_code, inputs)
        status = str(result.get("status", "")).upper()
        attempt.status = AttemptStatus.SUCCEEDED if status == "SUCCESS" else AttemptStatus.FAILED
        attempt.response_ref = f"ref:responses/{attempt_id}"
        attempt.response_preview = result
        if attempt.status == AttemptStatus.FAILED:
            errors = result.get("errors") or []
            attempt.error_type = "SCENE_FAILED"
            attempt.error_message = "; ".join(str(item) for item in errors)[:256] or "Scene 执行失败"
        attempt.finished_at = _now()
        logger.info(
            "GDP Agent Runtime Scene 调用完成: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s scene_status=%s attempt_status=%s error_type=%s error_message=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            status,
            attempt.status,
            attempt.error_type,
            attempt.error_message,
        )
    except TimeoutError:
        attempt.status = AttemptStatus.UNKNOWN_STATE
        attempt.error_type = "TIMEOUT"
        attempt.error_message = "请求超时，副作用未知"
        attempt.finished_at = _now()
        logger.warning(
            "GDP Agent Runtime Scene 调用超时，进入 UNKNOWN_STATE: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s",
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
            "GDP Agent Runtime Scene 连接断开，进入 UNKNOWN_STATE: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s",
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
            "GDP Agent Runtime Scene 调用校验失败，进入 FAILED: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s error_message=%s",
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
            "GDP Agent Runtime Scene 调用异常，进入 FAILED: task_run_id=%s action_id=%s attempt_id=%s scene_code=%s error_type=%s error_message=%s",
            action.task_run_id,
            action.action_id,
            attempt_id,
            action.scene_code,
            attempt.error_type,
            attempt.error_message,
        )

    observation = Observation(
        observation_id=_gen_id("obs"),
        task_run_id=action.task_run_id,
        action_id=action.action_id,
        attempt_id=attempt_id,
        raw_ref=attempt.response_ref or f"ref:errors/{attempt_id}",
        preview=attempt.response_preview if attempt.status == AttemptStatus.SUCCEEDED else {"error": attempt.error_message},
        created_at=_now(),
    )
    logger.info(
        "GDP Agent Runtime Observation 已生成: task_run_id=%s action_id=%s attempt_id=%s observation_id=%s raw_ref=%s preview_keys=%s",
        action.task_run_id,
        action.action_id,
        attempt_id,
        observation.observation_id,
        observation.raw_ref,
        sorted(observation.preview.keys()) if isinstance(observation.preview, dict) else [],
    )

    return attempt, observation
