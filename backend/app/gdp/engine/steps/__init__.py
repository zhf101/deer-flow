"""GDP 步骤执行器分发入口。

根据步骤类型（HTTP / SQL / ASSERT / TRANSFORM）
分发到对应的执行器模块。
"""

from __future__ import annotations

from app.gdp.engine.context import ExecutionContext
from app.gdp.engine.models import StepResult
from app.gdp.engine.steps.assert_executor import execute_assert_step
from app.gdp.engine.steps.http_executor import execute_http_step
from app.gdp.engine.steps.sql_executor import execute_sql_step
from app.gdp.engine.steps.transform_executor import execute_transform_step
from app.gdp.models import StepDefinition, StepType


async def execute_step(
    step: StepDefinition,
    ctx: ExecutionContext,
    *,
    sql_template_resolver=None,
    datasource_resolver=None,
) -> StepResult:
    """统一入口——根据 step.type 分发到具体执行器。

    Args:
        step: 步骤定义
        ctx: 执行上下文
        sql_template_resolver: SQL 模板解析回调（可选）
        datasource_resolver: 数据源解析回调（可选）

    Returns:
        该步骤的执行结果。
    """
    if step.type == StepType.HTTP:
        return await execute_http_step(step, ctx)
    if step.type == StepType.SQL:
        return await execute_sql_step(
            step, ctx,
            template_resolver=sql_template_resolver,
            datasource_resolver=datasource_resolver,
        )
    if step.type == StepType.ASSERT:
        return await execute_assert_step(step, ctx)
    if step.type == StepType.TRANSFORM:
        return await execute_transform_step(step, ctx)

    # 未知步骤类型
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    return StepResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=step.type,
        status="FAILED",
        startedAt=now,
        finishedAt=now,
        durationMs=0,
        error=f"未知的步骤类型: {step.type}",
    )
