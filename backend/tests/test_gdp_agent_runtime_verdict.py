"""GDP Agent Runtime Verdict 判定专项测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.gdp.agent_runtime.models import (
    Action,
    ActionStatus,
    ActionType,
    Evidence,
    EvidenceFact,
    FactPredicate,
    VerdictType,
)
from app.gdp.agent_runtime.verdict import judge


def _action() -> Action:
    now = datetime.now(UTC)
    return Action(
        action_id="act-1",
        task_run_id="tr-1",
        step_id="step-1",
        action_type=ActionType.EXECUTE_SCENE,
        status=ActionStatus.SUCCEEDED,
        scene_code="create_paid_order",
        input_ref="ref:inputs/act-1",
        input_preview={},
        input_hash="hash-1",
        idempotency_key="idem-1",
        approval_required=False,
        created_at=now,
        updated_at=now,
    )


def test_missing_facts_need_user_even_when_existing_facts_failed() -> None:
    """缺失事实表示信息不完整，即使已有事实都失败，也不能直接收口为失败。"""

    now = datetime.now(UTC)
    evidence = Evidence(
        evidence_id="evi-1",
        task_run_id="tr-1",
        step_id="step-1",
        action_id="act-1",
        facts=[
            EvidenceFact(
                subject="scene.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCESS",
                actual="FAILED",
                passed=False,
                source_observation_id="obs-1",
            )
        ],
        missing_facts=["order.order_id"],
        unknown_facts=[],
        created_at=now,
    )

    verdict = judge(evidence, _action())

    assert verdict.verdict_type == VerdictType.NEED_USER
