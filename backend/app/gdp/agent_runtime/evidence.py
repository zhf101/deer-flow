"""GDP Agent Runtime Evidence(依据事实) 构建。

从 Observation 中按 Scene 契约抽取事实。确定性逻辑，不调 LLM。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .models import (
    Action,
    ActionAttempt,
    AttemptStatus,
    Evidence,
    EvidenceFact,
    FactPredicate,
    Observation,
    PlanStep,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def build_evidence(
    step: PlanStep,
    action: Action,
    observation: Observation,
    attempt: ActionAttempt,
) -> Evidence:
    """从 observation 中按 scene 契约抽取事实。

    优先复用 Scene 执行器已经根据业务成功规则算出的整体状态。
    create_paid_order 作为 MVP 专用纵切片，额外检查订单字段。
    """
    evidence_id = _gen_id("evi")
    facts: list[EvidenceFact] = []
    missing_facts: list[str] = []
    unknown_facts: list[str] = []

    if attempt.status == AttemptStatus.UNKNOWN_STATE:
        unknown_facts.append("attempt_result_unknown")
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    if attempt.status == AttemptStatus.FAILED:
        facts.append(
            EvidenceFact(
                subject="attempt.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCEEDED",
                actual="FAILED",
                passed=False,
                source_observation_id=observation.observation_id,
            )
        )
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    preview = observation.preview or {}
    scene_status = str(preview.get("status", "")).upper()
    if scene_status:
        facts.append(
            EvidenceFact(
                subject="scene.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCESS",
                actual=scene_status,
                passed=(scene_status == "SUCCESS"),
                source_observation_id=observation.observation_id,
            )
        )
    else:
        missing_facts.append("scene.status")

    if action.scene_code != "create_paid_order":
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    final_output = preview.get("finalOutput", preview)

    order_id = final_output.get("order_id")
    if order_id is not None:
        facts.append(
            EvidenceFact(
                subject="order.order_id",
                predicate=FactPredicate.EXISTS,
                expected=True,
                actual=order_id,
                passed=True,
                source_observation_id=observation.observation_id,
            )
        )
    else:
        missing_facts.append("order.order_id")

    pay_status = final_output.get("pay_status")
    if pay_status is not None:
        facts.append(
            EvidenceFact(
                subject="order.pay_status",
                predicate=FactPredicate.EQUALS,
                expected="PAID",
                actual=pay_status,
                passed=(pay_status == "PAID"),
                source_observation_id=observation.observation_id,
            )
        )
    else:
        missing_facts.append("order.pay_status")

    return Evidence(
        evidence_id=evidence_id,
        task_run_id=action.task_run_id,
        step_id=step.step_id,
        action_id=action.action_id,
        facts=facts,
        missing_facts=missing_facts,
        unknown_facts=unknown_facts,
        created_at=_now(),
    )
