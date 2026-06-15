"""Observation 构建。"""

from __future__ import annotations

import logging

from ..ledger.memory import MemoryLedger
from ..models import Action, ActionAttempt, Observation
from ..support.log_text import describe_content
from .ids import gen_id, now

logger = logging.getLogger(__name__)


def build_observation(action: Action, attempt: ActionAttempt, store: MemoryLedger) -> Observation:
    """根据执行尝试构建观察结果，并在需要时保存错误载荷。"""

    # 构建观察摘要：优先保留场景的完整结构化结果（含 businessResult / finalOutput），
    # 因为后续的证据收集环节需要从中提取精确的业务事实（如"命中了哪条失败规则"）。
    # 仅当场景连结构化结果都没返回（超时/连接断开等未知态）时，才退化为纯错误摘要。
    if attempt.response_preview:
        preview = attempt.response_preview
    else:
        preview = {"error": attempt.error_message}

    raw_ref = attempt.response_ref or f"ref:errors/{attempt.attempt_id}"
    if attempt.response_ref is None:
        store.save_payload(
            action.task_run_id,
            raw_ref,
            {
                "error_type": attempt.error_type,
                "error_message": attempt.error_message,
            },
        )

    observation = Observation(
        observation_id=gen_id("obs"),
        task_run_id=action.task_run_id,
        action_id=action.action_id,
        attempt_id=attempt.attempt_id,
        raw_ref=raw_ref,
        preview=preview,
        created_at=now(),
    )
    logger.info(
        "GDP Agent 运行时观察结果已生成：任务ID=%s，动作ID=%s，尝试ID=%s，观察ID=%s，原始结果引用=%s，观察摘要=%s",
        action.task_run_id,
        action.action_id,
        attempt.attempt_id,
        observation.observation_id,
        observation.raw_ref,
        describe_content(observation.preview),
    )
    return observation
