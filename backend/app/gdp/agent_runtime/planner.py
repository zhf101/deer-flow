"""多步骤计划模板。"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .bindings import StepInputBinding
from .models import PlanStep, StepEdge, StepStatus, TaskRun
from .store import Store
from .variables import SceneOutputBinding


class PlanStepSpec(BaseModel):
    """计划中的一个业务步骤定义。

    业务目标：在真正创建账本步骤前，用稳定结构描述该步骤要做什么、
    依赖哪些前置步骤、入参如何绑定以及成功后产出哪些变量。
    """

    step_no: int = Field(ge=1, description="步骤序号。")
    goal: str = Field(min_length=1, description="该步骤要达成的业务目标。")
    scene_hint: str | None = Field(default=None, description="可选场景搜索提示，不等同于最终场景编码。")
    input_bindings: list[StepInputBinding] = Field(default_factory=list, description="步骤执行入参绑定规则。")
    output_bindings: list[SceneOutputBinding] = Field(default_factory=list, description="场景输出变量抽取规则。")
    depends_on_step_nos: list[int] = Field(default_factory=list, description="前置步骤序号。")
    is_final_assertion_step: bool = Field(default=False, description="是否为最终验收步骤。")


class PlanRecipe(BaseModel):
    """一个可复用的多步骤计划模板。

    业务目标：第三阶段先用确定性模板支撑真实 case，避免把计划生成不确定性
    和变量账本问题混在一起。
    """

    recipe_id: str = Field(description="计划模板 ID。")
    goal_patterns: list[str] = Field(description="能命中的用户目标关键词或短语。")
    steps: list[PlanStepSpec] = Field(description="计划模板中的步骤定义。")

    @model_validator(mode="after")
    def check_final_step(self) -> PlanRecipe:
        if not self.steps:
            raise ValueError("PlanRecipe 必须至少包含一个步骤。")
        final_steps = [step for step in self.steps if step.is_final_assertion_step]
        if len(final_steps) > 1:
            raise ValueError("PlanRecipe 只能有一个最终验收步骤。")
        if not final_steps:
            self.steps[-1].is_final_assertion_step = True
        return self


def plan_step_spec_ref(step_id: str) -> str:
    """返回步骤规格快照引用。"""

    return f"ref:agent-runtime/plan-step-spec/{step_id}"


def build_plan(user_goal: str, inputs: dict[str, Any], scene_code: str | None = None) -> list[PlanStepSpec]:
    """根据用户目标生成确定性计划。

    当前动作：显式场景编码保持单步骤兼容；命中内置模板时生成多步骤；
    未命中模板时回退第二阶段单步骤链路。
    """

    normalized_goal = user_goal.strip()
    if scene_code:
        return [
            PlanStepSpec(
                step_no=1,
                goal=normalized_goal,
                scene_hint=scene_code,
                is_final_assertion_step=True,
            )
        ]

    for recipe in _recipes():
        if _matches_recipe(normalized_goal, recipe):
            return [step.model_copy(deep=True) for step in recipe.steps]

    return [PlanStepSpec(step_no=1, goal=normalized_goal, is_final_assertion_step=True)]


def create_plan_steps(task_run: TaskRun, specs: list[PlanStepSpec], store: Store) -> list[PlanStep]:
    """把计划规格落成任务步骤并保存快照。

    业务目标：让 WAITING_USER 和进程重启后的恢复都能读取当时的计划规格，
    而不是重新根据用户目标猜测当前步骤。
    """

    if not specs:
        raise ValueError("至少需要一个 PlanStepSpec。")

    step_by_no: dict[int, PlanStep] = {}
    steps: list[PlanStep] = []
    task_run.step_ids.clear()
    task_run.step_edges.clear()
    task_run.active_step_id = None

    for spec in sorted(specs, key=lambda item: item.step_no):
        step = PlanStep(
            step_id=_gen_id("step"),
            task_run_id=task_run.task_run_id,
            step_no=spec.step_no,
            goal=spec.goal,
            status=StepStatus.PENDING,
        )
        step_by_no[spec.step_no] = step
        steps.append(step)
        task_run.step_ids.append(step.step_id)
        store.save_step(step)
        store.save_payload(task_run.task_run_id, plan_step_spec_ref(step.step_id), spec.model_dump(mode="json"))

    for spec in sorted(specs, key=lambda item: item.step_no):
        step = step_by_no[spec.step_no]
        for depends_on_no in spec.depends_on_step_nos:
            depends_on_step = step_by_no.get(depends_on_no)
            if depends_on_step is None:
                raise ValueError(f"步骤 {spec.step_no} 依赖不存在的步骤 {depends_on_no}。")
            step.depends_on.append(depends_on_step.step_id)
            task_run.step_edges.append(
                StepEdge(from_step_id=depends_on_step.step_id, to_step_id=step.step_id)
            )
        store.save_step(step)

    task_run.active_step_id = steps[0].step_id
    store.save_task_run(task_run)
    return steps


def _recipes() -> list[PlanRecipe]:
    return [
        PlanRecipe(
            recipe_id="create-order-and-pay",
            goal_patterns=["创建订单并支付", "创建订单并完成支付"],
            steps=[
                PlanStepSpec(
                    step_no=1,
                    goal="创建订单",
                    scene_hint="创建订单",
                    input_bindings=[
                        StepInputBinding(input_name="buyer_id", source="USER_INPUT", source_name="buyer_id"),
                    ],
                    output_bindings=[
                        SceneOutputBinding(
                            output_path="finalOutput.order_id",
                            variable_name="order_id",
                            semantic_type="ORDER_ID",
                        )
                    ],
                ),
                PlanStepSpec(
                    step_no=2,
                    goal="支付订单",
                    scene_hint="支付订单",
                    input_bindings=[
                        StepInputBinding(input_name="order_id", source="VARIABLE", source_name="order_id"),
                    ],
                    output_bindings=[
                        SceneOutputBinding(
                            output_path="finalOutput.pay_status",
                            variable_name="pay_status",
                            semantic_type="PAY_STATUS",
                        ),
                        SceneOutputBinding(
                            output_path="finalOutput.payment_id",
                            variable_name="payment_id",
                            semantic_type="PAYMENT_ID",
                            required=False,
                        ),
                    ],
                    depends_on_step_nos=[1],
                ),
                PlanStepSpec(
                    step_no=3,
                    goal="查询订单状态",
                    scene_hint="查询订单状态",
                    input_bindings=[
                        StepInputBinding(input_name="order_id", source="VARIABLE", source_name="order_id"),
                    ],
                    depends_on_step_nos=[2],
                    is_final_assertion_step=True,
                ),
            ],
        ),
        PlanRecipe(
            recipe_id="pay-existing-order-and-query",
            goal_patterns=["支付已有订单", "支付历史订单"],
            steps=[
                PlanStepSpec(
                    step_no=1,
                    goal="支付已有订单",
                    scene_hint="支付订单",
                    input_bindings=[
                        StepInputBinding(input_name="order_id", source="VARIABLE", source_name="order_id"),
                    ],
                    output_bindings=[
                        SceneOutputBinding(
                            output_path="finalOutput.pay_status",
                            variable_name="pay_status",
                            semantic_type="PAY_STATUS",
                        )
                    ],
                ),
                PlanStepSpec(
                    step_no=2,
                    goal="查询订单状态",
                    scene_hint="查询订单状态",
                    input_bindings=[
                        StepInputBinding(input_name="order_id", source="VARIABLE", source_name="order_id"),
                    ],
                    depends_on_step_nos=[1],
                    is_final_assertion_step=True,
                ),
            ],
        )
    ]


def _matches_recipe(user_goal: str, recipe: PlanRecipe) -> bool:
    normalized = user_goal.lower()
    return any(pattern.lower() in normalized for pattern in recipe.goal_patterns)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
