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
    PlanStep,
    StepStatus,
    TaskRun,
    TaskRunStatus,
    Verdict,
    VerdictType,
)
from app.gdp.agent_runtime.verdict import apply_verdict, judge


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


def test_apply_verdict_does_not_drive_action_status() -> None:
    """Verdict 只收口 TaskRun/PlanStep，不改 Action 技术执行状态。"""

    now = datetime.now(UTC)
    task_run = TaskRun(
        task_run_id="tr-1",
        thread_id="thread-1",
        user_id="user-1",
        user_goal="造一笔已支付订单",
        status=TaskRunStatus.RUNNING,
        created_at=now,
        updated_at=now,
    )
    step = PlanStep(
        step_id="step-1",
        task_run_id="tr-1",
        step_no=1,
        goal="造一笔已支付订单",
        status=StepStatus.RUNNING,
    )
    action = _action()
    action.status = ActionStatus.RUNNING
    verdict = Verdict(
        verdict_id="vrd-1",
        task_run_id="tr-1",
        step_id="step-1",
        evidence_id="evi-1",
        verdict_type=VerdictType.DONE,
        reason="所有事实通过",
        created_at=now,
    )

    updated_task_run, updated_step, updated_action = apply_verdict(task_run, step, action, verdict)

    assert updated_task_run.status == TaskRunStatus.COMPLETED
    assert updated_step.status == StepStatus.DONE
    assert updated_action.status == ActionStatus.RUNNING
