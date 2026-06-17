"""GDP Agent Runtime 步骤入参绑定测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.gdp.agent_runtime.bindings import StepInputBinding, resolve_step_inputs
from app.gdp.agent_runtime.domain.factories import create_task_run
from app.gdp.agent_runtime.ledger.memory import Store
from app.gdp.agent_runtime.models import (
    PlanStep,
    StepEdge,
    StepStatus,
    Variable,
    VariableProvenance,
    VariableSource,
)


def _step(step_id: str = "step-2") -> PlanStep:
    return PlanStep(
        step_id=step_id,
        task_run_id="tr-1",
        step_no=2,
        goal="支付订单",
        status=StepStatus.PENDING,
        depends_on=["step-1"],
    )


def _variable(*, tainted: bool = False) -> Variable:
    return Variable(
        variable_id="var-order-id",
        task_run_id="tr-1",
        name="order_id",
        semantic_type="ORDER_ID",
        value_ref="ref:vars/var-order-id",
        value_preview="ORDER-1",
        sensitive=False,
        tainted=tainted,
        provenance=VariableProvenance(
            source_type=VariableSource.SCENE_OUTPUT,
            source_id="step-1",
            action_id="act-1",
            evidence_id="evi-1",
        ),
        created_at=datetime.now(UTC),
    )


def test_resolve_step_inputs_reads_user_input_const_and_variable() -> None:
    """入参绑定能同时消费用户输入、常量和上游变量。"""
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    task_run.task_run_id = "tr-1"
    task_run.step_edges = [StepEdge(from_step_id="step-1", to_step_id="step-2")]
    step = _step()
    store = Store()
    store.save_task_run(task_run)
    store.save_step(step)
    store.save_variable(_variable())
    store.save_payload("tr-1", "ref:vars/var-order-id", "ORDER-1")

    result = resolve_step_inputs(
        task_run,
        step,
        [
            StepInputBinding(input_name="buyer_id", source="USER_INPUT", source_name="buyer_id"),
            StepInputBinding(input_name="order_id", source="VARIABLE", source_name="order_id"),
            StepInputBinding(input_name="channel", source="CONST", source_name="AUTO"),
        ],
        {"buyer_id": "U1"},
        store,
    )

    assert result.inputs == {"buyer_id": "U1", "order_id": "ORDER-1", "channel": "AUTO"}
    assert result.consumed_variable_ids == ["var-order-id"]
    assert step.consumes == ["var-order-id"]
    assert store.get_variable("var-order-id").consumed_by == ["step-2"]
    assert task_run.step_edges[0].variable_ids == ["var-order-id"]


def test_resolve_step_inputs_reports_missing_user_input_without_variable_failure() -> None:
    """缺用户输入进入可恢复缺参，不应伪装成变量缺失。"""
    task_run = create_task_run("创建订单并支付")
    task_run.task_run_id = "tr-1"
    result = resolve_step_inputs(
        task_run,
        _step(),
        [StepInputBinding(input_name="buyer_id", source="USER_INPUT", source_name="buyer_id")],
        {},
        Store(),
    )

    assert result.inputs == {}
    assert result.missing_inputs == ["buyer_id"]
    assert result.missing_variables == []


def test_resolve_step_inputs_reports_missing_or_tainted_variables() -> None:
    """缺失或污染变量不能自动绑定到下游步骤。"""
    task_run = create_task_run("创建订单并支付")
    task_run.task_run_id = "tr-1"
    store = Store()
    store.save_variable(_variable(tainted=True))

    result = resolve_step_inputs(
        task_run,
        _step(),
        [StepInputBinding(input_name="order_id", source="VARIABLE", source_name="order_id")],
        {},
        store,
    )

    assert result.inputs == {}
    assert result.missing_variables == ["order_id"]
