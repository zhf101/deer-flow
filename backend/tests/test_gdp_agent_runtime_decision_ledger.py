"""GDP Agent Runtime 决策账本测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.gdp.agent_runtime.flow import create_single_step, create_task_run
from app.gdp.agent_runtime.models import (
    DecisionKind,
    DecisionOption,
    DecisionRecord,
    DecisionSource,
    DecisionStatus,
)
from app.gdp.agent_runtime.store import Store


def test_store_exports_decision_records_in_timeline_and_snapshot() -> None:
    """内存 Store 能保存、展示并导出决策记录。"""
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    decision = DecisionRecord(
        decision_id="dec-1",
        task_run_id=task_run.task_run_id,
        step_id=step.step_id,
        requirement_id="req-1",
        proposal_id="prop-1",
        action_id=None,
        scene_run_id=None,
        decision_kind=DecisionKind.SCENE_SELECTION,
        decision_source=DecisionSource.RULE,
        status=DecisionStatus.DECIDED,
        target_type="scene",
        target_id="create_paid_order",
        input_ref="payload://input",
        options=[
            DecisionOption(
                option_id="create_paid_order",
                option_type="scene",
                label="创建已支付订单",
                score=0.91,
                reasons=["命中订单和支付目标"],
                metadata={"requires_confirmation": False},
            )
        ],
        selected_option=DecisionOption(
            option_id="create_paid_order",
            option_type="scene",
            label="创建已支付订单",
            score=0.91,
            reasons=["命中订单和支付目标"],
            metadata={"requires_confirmation": False},
        ),
        selected_reasons=["单候选高置信自动选定"],
        rejected_reasons=[],
        criteria=["单候选", "评分达到自动选择阈值", "无缺参", "无需审批"],
        evidence_refs=["req-1", "prop-1"],
        model_info=None,
        summary="单候选高置信自动选定：创建已支付订单（create_paid_order）。",
        created_at=datetime.now(UTC),
    )

    store.save_task_run(task_run)
    store.save_step(step)
    store.save_decision(decision)

    timeline = store.get_timeline(task_run.task_run_id)
    snapshot = store.export_task_run(task_run.task_run_id)

    assert timeline["decisions"][0]["decision_kind"] == "SCENE_SELECTION"
    assert timeline["decisions"][0]["decision_source"] == "RULE"
    assert timeline["decisions"][0]["target_id"] == "create_paid_order"
    assert timeline["decisions"][0]["selected_reasons"] == ["单候选高置信自动选定"]
    assert snapshot["decisions"][0]["decision_id"] == "dec-1"


def test_timeline_decision_projection_redacts_payload_refs_and_sensitive_metadata() -> None:
    """timeline 决策投影面向前端展示，不能暴露 payload ref 或敏感候选元数据。"""
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    step = create_single_step(task_run)
    decision = DecisionRecord(
        decision_id="dec-sensitive",
        task_run_id=task_run.task_run_id,
        step_id=step.step_id,
        requirement_id="req-1",
        proposal_id="prop-1",
        action_id=None,
        scene_run_id=None,
        decision_kind=DecisionKind.SCENE_SELECTION,
        decision_source=DecisionSource.RULE,
        status=DecisionStatus.DECIDED,
        target_type="scene",
        target_id="create_paid_order",
        input_ref="payload://secret-input",
        options=[
            DecisionOption(
                option_id="create_paid_order",
                option_type="scene",
                label="创建已支付订单",
                score=0.91,
                reasons=["命中订单和支付目标"],
                metadata={
                    "requires_confirmation": False,
                    "password": "p@ss",
                    "nested": {
                        "token": "secret-token",
                        "safe": "visible",
                    },
                    "payload": {"body": {"buyer_id": "U1"}},
                },
            )
        ],
        selected_option=DecisionOption(
            option_id="create_paid_order",
            option_type="scene",
            label="创建已支付订单",
            score=0.91,
            reasons=["命中订单和支付目标"],
            metadata={
                "connectionString": "jdbc:mysql://user:pass@example/db",
                "safe": "visible",
            },
        ),
        selected_reasons=["单候选高置信自动选定"],
        rejected_reasons=[],
        criteria=["单候选"],
        evidence_refs=["req-1", "prop-1"],
        model_info=None,
        summary="单候选高置信自动选定。",
        created_at=datetime.now(UTC),
    )

    store.save_task_run(task_run)
    store.save_step(step)
    store.save_decision(decision)

    timeline_decision = store.get_timeline(task_run.task_run_id)["decisions"][0]
    snapshot_decision = store.export_task_run(task_run.task_run_id)["decisions"][0]

    assert "input_ref" not in timeline_decision
    assert timeline_decision["options"][0]["metadata"] == {
        "requires_confirmation": False,
        "nested": {"safe": "visible"},
    }
    assert timeline_decision["selected_option"]["metadata"] == {"safe": "visible"}
    assert snapshot_decision["input_ref"] == "payload://secret-input"
