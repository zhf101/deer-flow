"""GDP Agent Runtime 多步骤计划测试。"""

from __future__ import annotations

from app.gdp.agent_runtime.domain.factories import create_task_run
from app.gdp.agent_runtime.ledger.memory import Store
from app.gdp.agent_runtime.models import StepStatus
from app.gdp.agent_runtime.planner import (
    build_plan,
    create_plan_steps,
    plan_step_spec_ref,
)


def test_build_plan_matches_create_order_and_pay_recipe():
    """创建订单并支付目标会生成三步确定性计划。"""
    specs = build_plan("帮我创建订单并支付", inputs={"buyer_id": "U1"})

    assert [item.goal for item in specs] == ["创建订单", "支付订单", "查询订单状态"]
    assert specs[0].output_bindings[0].variable_name == "order_id"
    assert specs[1].input_bindings[0].source == "VARIABLE"
    assert specs[1].input_bindings[0].source_name == "order_id"
    assert specs[2].is_final_assertion_step is True


def test_build_plan_falls_back_to_single_step_when_no_recipe_matches():
    """未命中多步骤模板时保持第二阶段单步骤链路。"""
    specs = build_plan("造一张可用会员卡", inputs={})

    assert len(specs) == 1
    assert specs[0].goal == "造一张可用会员卡"
    assert specs[0].is_final_assertion_step is True
    assert specs[0].depends_on_step_nos == []


def test_build_plan_keeps_explicit_scene_code_as_single_step():
    """显式 scene_code 入口必须兼容单步骤快速通道。"""
    specs = build_plan("创建订单并支付", inputs={}, scene_code="create_paid_order")

    assert len(specs) == 1
    assert specs[0].goal == "创建订单并支付"
    assert specs[0].scene_hint == "create_paid_order"


def test_create_plan_steps_persists_specs_and_edges():
    """PlanStepSpec 落账后能恢复快照和依赖边。"""
    task_run = create_task_run("创建订单并支付", env_code="SIT1")
    specs = build_plan(task_run.user_goal, inputs={})
    store = Store()

    steps = create_plan_steps(task_run, specs, store)

    assert [step.step_no for step in steps] == [1, 2, 3]
    assert [step.status for step in steps] == [StepStatus.PENDING, StepStatus.PENDING, StepStatus.PENDING]
    assert task_run.step_ids == [step.step_id for step in steps]
    assert task_run.active_step_id == steps[0].step_id
    assert steps[1].depends_on == [steps[0].step_id]
    assert steps[2].depends_on == [steps[1].step_id]
    assert [(edge.from_step_id, edge.to_step_id) for edge in task_run.step_edges] == [
        (steps[0].step_id, steps[1].step_id),
        (steps[1].step_id, steps[2].step_id),
    ]

    saved_spec = store.get_payload(task_run.task_run_id, plan_step_spec_ref(steps[1].step_id))
    assert saved_spec["goal"] == "支付订单"
    assert saved_spec["input_bindings"][0]["source_name"] == "order_id"
