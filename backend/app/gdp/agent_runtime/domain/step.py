"""业务步骤领域模型。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .identifiers import ActionId, StepId, TaskRunId, VariableId, VerdictId


class StepStatus(StrEnum):
    """业务步骤的执行状态。

    用户在前端可看到每个步骤的当前状态：
    PENDING → RUNNING → DONE / FAILED / BLOCKED
    """

    PENDING = "PENDING"  # 步骤已创建但尚未开始执行，排在依赖它的步骤之后
    RUNNING = "RUNNING"  # 系统正在执行该步骤对应的造数动作
    DONE = "DONE"        # 步骤已成功完成，其产出的变量可供下游步骤使用
    FAILED = "FAILED"    # 步骤执行失败，可能导致整个造数任务失败
    BLOCKED = "BLOCKED"  # 步骤被上游步骤失败所阻塞，无法继续执行


class PlanStep(BaseModel):
    """用户造数目标拆解出的业务步骤。

    业务目标：将用户的宏观造数目标（如"造一笔已支付订单"）拆解为可独立执行和判定的业务步骤。
    每个步骤有明确的业务目标、输入变量和输出变量，系统按步骤顺序执行，
    上游步骤的产出（如订单号）可以作为下游步骤的输入（如用该订单号触发支付）。

    当前 MVP 阶段每个任务只拆解为一个步骤，但数据模型保留多步骤拓扑能力。
    """

    step_id: StepId = Field(description="步骤唯一标识，用于关联该步骤下的所有动作、变量和判定。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID，标识该步骤属于哪个用户造数目标。")
    step_no: int = Field(ge=1, description="步骤序号，决定执行顺序，前端展示为'第 N 步'。")
    goal: str = Field(min_length=1, description="该步骤需要达成的业务目标，如'创建一笔订单'，是系统选择场景和执行动作的依据。")
    status: StepStatus = Field(description="步骤当前执行状态，决定前端进度展示。")
    depends_on: list[StepId] = Field(default_factory=list, description="前置依赖步骤列表，这些步骤必须全部完成后本步骤才能开始。")
    action_ids: list[ActionId] = Field(default_factory=list, description="该步骤产生的所有动作 ID，每个动作对应一次场景执行。")
    consumes: list[VariableId] = Field(default_factory=list, description="该步骤需要消费的业务数据（如上游产出的订单号）。")
    produces: list[VariableId] = Field(default_factory=list, description="该步骤执行后产出的业务数据（如新生成的订单号、支付流水号）。")
    verdict_id: VerdictId | None = Field(default=None, description="步骤完成后的判定结论 ID，用于判定该步骤的业务目标是否达成。")

