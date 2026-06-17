"""GDP Agent Runtime 场景输出变量测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.gdp.agent_runtime.domain.factories import create_task_run
from app.gdp.agent_runtime.ledger.memory import Store
from app.gdp.agent_runtime.models import (
    Action,
    ActionStatus,
    ActionType,
    Evidence,
    EvidenceFact,
    FactPredicate,
    Observation,
    PlanStep,
    StepStatus,
    VariableSource,
)
from app.gdp.agent_runtime.variables import SceneOutputBinding, extract_scene_output_variables


def _step() -> PlanStep:
    return PlanStep(
        step_id="step-1",
        task_run_id="tr-1",
        step_no=1,
        goal="创建订单",
        status=StepStatus.DONE,
    )


def _action() -> Action:
    return Action(
        action_id="act-1",
        task_run_id="tr-1",
        step_id="step-1",
        action_type=ActionType.EXECUTE_SCENE,
        status=ActionStatus.SUCCEEDED,
        scene_code="create_order",
        input_ref="ref:inputs/act-1",
        input_preview={},
        input_hash="hash-1",
        idempotency_key="idem-1",
        approval_required=False,
    )


def _observation(final_output: dict[str, object]) -> Observation:
    return Observation(
        observation_id="obs-1",
        task_run_id="tr-1",
        action_id="act-1",
        attempt_id="att-1",
        raw_ref="ref:responses/att-1",
        preview={"finalOutput": final_output},
        created_at=datetime.now(UTC),
    )


def _evidence(subject: str = "finalOutput.order_id") -> Evidence:
    return Evidence(
        evidence_id="evi-1",
        task_run_id="tr-1",
        step_id="step-1",
        action_id="act-1",
        facts=[
            EvidenceFact(
                subject=subject,
                predicate=FactPredicate.NON_EMPTY,
                expected=True,
                actual="ORDER-1",
                passed=True,
                source_observation_id="obs-1",
            )
        ],
        created_at=datetime.now(UTC),
    )


def test_extract_scene_output_variables_records_value_ref_and_provenance() -> None:
    """成功步骤输出能写入变量账本并挂到步骤产出。"""
    task_run = create_task_run("创建订单并支付")
    task_run.task_run_id = "tr-1"
    step = _step()
    action = _action()
    store = Store()
    store.save_task_run(task_run)
    store.save_step(step)

    variables = extract_scene_output_variables(
        task_run,
        step,
        action,
        _evidence(),
        _observation({"order_id": "ORDER-1"}),
        [
            SceneOutputBinding(
                output_path="finalOutput.order_id",
                variable_name="order_id",
                semantic_type="ORDER_ID",
            )
        ],
        store,
    )

    assert len(variables) == 1
    variable = variables[0]
    assert variable.name == "order_id"
    assert variable.value_preview == "ORDER-1"
    assert variable.provenance.source_type == VariableSource.SCENE_OUTPUT
    assert variable.provenance.action_id == "act-1"
    assert variable.provenance.evidence_id == "evi-1"
    assert store.get_payload("tr-1", variable.value_ref) == "ORDER-1"
    assert step.produces == [variable.variable_id]


def test_extract_scene_output_variables_masks_sensitive_preview() -> None:
    """敏感输出变量的 preview 必须脱敏。"""
    task_run = create_task_run("开卡")
    task_run.task_run_id = "tr-1"
    step = _step()
    store = Store()

    variables = extract_scene_output_variables(
        task_run,
        step,
        _action(),
        _evidence("finalOutput.card_no"),
        _observation({"card_no": "6222000011112222"}),
        [
            SceneOutputBinding(
                output_path="finalOutput.card_no",
                variable_name="card_no",
                semantic_type="CARD_NO",
                sensitive=True,
            )
        ],
        store,
    )

    assert variables[0].value_preview == "***"


def test_extract_scene_output_variables_rejects_required_missing_output() -> None:
    """必需输出缺失时不能把步骤当作可继续。"""
    task_run = create_task_run("创建订单")
    task_run.task_run_id = "tr-1"

    with pytest.raises(ValueError, match="缺少必需输出变量"):
        extract_scene_output_variables(
            task_run,
            _step(),
            _action(),
            _evidence(),
            _observation({}),
            [
                SceneOutputBinding(
                    output_path="finalOutput.order_id",
                    variable_name="order_id",
                    semantic_type="ORDER_ID",
                )
            ],
            Store(),
        )


def test_extract_scene_output_variables_requires_evidence_support() -> None:
    """没有证据支撑的输出不能直接写成事实变量。"""
    task_run = create_task_run("创建订单")
    task_run.task_run_id = "tr-1"

    with pytest.raises(ValueError, match="缺少证据支撑"):
        extract_scene_output_variables(
            task_run,
            _step(),
            _action(),
            _evidence("finalOutput.other"),
            _observation({"order_id": "ORDER-1"}),
            [
                SceneOutputBinding(
                    output_path="finalOutput.order_id",
                    variable_name="order_id",
                    semantic_type="ORDER_ID",
                )
            ],
            Store(),
        )
