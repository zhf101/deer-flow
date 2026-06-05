"""TRANSFORM 步骤执行器。

遍历 assignments 字典，对每个表达式做变量解析后将结果写入上下文变量。
TRANSFORM 步骤不产生任何外部调用，纯粹用于数据转换和变量计算。

示例：
    assignments = {
        "vars.orderRemark": "AUTO_${steps.createOrder.outputs.orderNo}_${system.now}"
    }
    → 解析后写入 ctx.vars["orderRemark"]
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.gdp.engine.context import ExecutionContext
from app.gdp.engine.models import StepResult
from app.gdp.engine.variable_resolver import resolve_value
from app.gdp.models import StepDefinition, StepType


async def execute_transform_step(step: StepDefinition, ctx: ExecutionContext) -> StepResult:
    """执行转换步骤——计算 assignments 并写入 vars 上下文。"""
    started_at = datetime.now(UTC)

    outputs: dict[str, object] = {}
    for var_name, expression in step.assignments.items():
        # 解析表达式中的变量引用
        value = resolve_value(expression, ctx)
        # 写入上下文变量
        ctx.set_var(var_name, value)
        # 同时记录到步骤输出
        outputs[var_name] = value

    # 将输出也写入 step_outputs（方便后续步骤通过 ${steps.xxx.outputs.xxx} 引用）
    ctx.set_step_output(step.stepId, outputs)

    finished_at = datetime.now(UTC)
    return StepResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=StepType.TRANSFORM,
        status="SUCCESS",
        startedAt=started_at,
        finishedAt=finished_at,
        durationMs=int((finished_at - started_at).total_seconds() * 1000),
        outputs=outputs,
    )
