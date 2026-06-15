"""任务生命周期领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from .identifiers import StepId, TaskRunId, VariableId, VerdictId


class TaskRunStatus(StrEnum):
    """用户一次造数任务的生命周期状态。

    从用户提交造数目标到最终拿到结果（或失败），任务经历以下状态流转：
    CREATED → RUNNING → (WAITING_USER ↔ RUNNING) → COMPLETED / FAILED / CANCELLED
    """

    CREATED = "CREATED"           # 用户已提交造数目标，系统正在准备执行计划，尚未开始实际造数
    RUNNING = "RUNNING"           # 系统正在自动执行造数流程（搜索场景、执行动作、收集证据），用户无需操作
    WAITING_USER = "WAITING_USER" # 系统遇到需要用户介入的情况（缺少输入、需要审批、选择场景等），任务暂停等待用户回复
    COMPLETED = "COMPLETED"       # 造数目标已达成，用户可以在结果中看到生成的数据和判定结论
    FAILED = "FAILED"             # 造数目标未能达成，系统记录了失败原因供用户查看和排查
    CANCELLED = "CANCELLED"       # 用户或系统主动取消了本次造数任务


class SuspendReason(StrEnum):
    """任务挂起原因，告诉用户"系统为什么停下来等你"。

    当任务进入 WAITING_USER 状态时，必须附带一个挂起原因，
    让前端展示明确的提示信息，引导用户做出对应操作来恢复任务。
    """

    MISSING_INPUT = "MISSING_INPUT"               # 执行场景所需的必要输入缺失，需要用户补充数据（如金额、卡号等）
    NEED_APPROVAL = "NEED_APPROVAL"                # 即将执行的操作有副作用（如写入真实数据），需要用户确认后才能继续
    NEED_SCENE_SELECTION = "NEED_SCENE_SELECTION"  # 系统找到了多个可用的造数场景，需要用户从中选择一个
    UNKNOWN_STATE_CONFIRMATION = "UNKNOWN_STATE_CONFIRMATION"  # 场景执行后状态不确定（如网络超时），需要用户确认实际结果
    NEED_EVIDENCE = "NEED_EVIDENCE"                # 系统无法自动收集足够的证据来判定造数是否成功，需要用户提供额外信息


class ReplyType(StrEnum):
    """用户回复类型，对应任务挂起时用户可以做出的每种响应。

    每种回复类型与一种挂起原因对应，用户通过回复来恢复被暂停的造数任务：
    - 系统问"缺少什么" → 用户补充输入（SUPPLY_INPUT）
    - 系统问"要不要执行" → 用户确认审批（APPROVE）
    - 系统问"选哪个场景" → 用户选择场景（SELECT_SCENE / SUPPLY_SCENE_CODE）
    - 系统问"实际结果是什么" → 用户确认状态（CONFIRM_UNKNOWN_STATE）
    """

    APPROVE = "APPROVE"                     # 用户确认审批：同意系统执行有副作用的操作（对应 NEED_APPROVAL）
    SUPPLY_INPUT = "SUPPLY_INPUT"           # 用户补充缺失数据：提供场景执行所需的必要输入（对应 MISSING_INPUT）
    CONFIRM_UNKNOWN_STATE = "CONFIRM_UNKNOWN_STATE"  # 用户确认实际结果：告知系统上次不确定执行的真实状态（对应 UNKNOWN_STATE_CONFIRMATION）
    SELECT_SCENE = "SELECT_SCENE"           # 用户从候选列表中选择：在系统推荐的多个造数场景中选定一个（对应 NEED_SCENE_SELECTION）
    SUPPLY_SCENE_CODE = "SUPPLY_SCENE_CODE" # 用户直接指定场景编码：不依赖系统推荐，用户自行输入已知的场景编码（对应 NEED_SCENE_SELECTION 的快捷路径）


class StepEdge(BaseModel):
    """步骤间的依赖关系，定义造数步骤的执行顺序和数据传递方向。

    业务目标：当用户的造数目标需要多个步骤协同完成时（如先创建订单再支付），
    通过依赖边确保步骤按正确顺序执行，上游步骤的输出变量可以传递给下游步骤消费。
    当前 MVP 阶段每个任务只有一个步骤，但保留拓扑结构以支持未来的多步骤编排。
    """

    from_step_id: StepId = Field(description="前置步骤 ID，该步骤必须先完成，后续步骤才能开始。")
    to_step_id: StepId = Field(description="后置步骤 ID，该步骤依赖前置步骤的产出才能执行。")
    variable_ids: list[VariableId] = Field(default_factory=list, description="沿此依赖边传递的变量列表，即前置步骤产出、后置步骤消费的业务数据。")


class TaskRun(BaseModel):
    """用户一次造数目标的完整账本。

    业务目标：记录用户从提出造数目标到最终获得结果的全过程。
    这是用户与造数系统交互的顶层对象，前端展示的"任务卡片"即对应一个 TaskRun。
    用户可以在其中看到：造数目标、当前进度、系统提问、最终结果或失败原因。

    当前动作：作为状态机的根节点，驱动 PlanStep → Action → Attempt 的执行流转，
    并在需要用户介入时暂停任务、展示问题。

    预期结果：任务终态时，用户能看到 COMPLETED（附判定结论）或 FAILED（附失败原因）。
    """

    task_run_id: TaskRunId = Field(description="造数任务唯一标识，用户和系统通过此 ID 追踪和引用本次造数过程。")
    thread_id: str = Field(description="所属对话线程 ID，将造数任务关联到用户的聊天上下文，保持交互连贯性。")
    user_id: str = Field(description="发起造数请求的用户 ID，用于权限控制和数据隔离。")
    user_goal: str = Field(min_length=1, description="用户原始造数目标的自然语言描述，如'造一笔已支付的订单'，是整个任务的业务驱动力。")
    env_code: str | None = Field(default=None, description="目标环境编码，指定在哪个测试/生产环境中执行造数，为空时由系统自动选择。")
    status: TaskRunStatus = Field(description="任务当前所处生命周期状态，决定前端展示样式和用户可执行的操作。")
    step_ids: list[StepId] = Field(default_factory=list, description="本任务包含的所有业务步骤 ID，代表造数目标的拆解结果。")
    step_edges: list[StepEdge] = Field(default_factory=list, description="步骤间的依赖关系图，定义执行顺序和数据传递方向。")
    active_step_id: StepId | None = Field(default=None, description="当前正在推进的步骤 ID，用户可在前端看到'正在执行第几步'。")
    suspend_reason: SuspendReason | None = Field(default=None, description="任务挂起的具体原因，仅 WAITING_USER 状态时使用，告诉用户系统需要什么帮助才能继续。")
    pending_question: str | None = Field(default=None, description="等待用户回复时展示的问题文案，如'请选择造数场景'或'请输入卡号'。")
    final_verdict_id: VerdictId | None = Field(default=None, description="终态时的最终判定 ID，COMPLETED 时必有，用户可通过它查看造数是否真正成功。")
    failure_reason: str | None = Field(default=None, description="任务失败时的可读原因描述，帮助用户理解为什么造数没有成功。")
    created_at: datetime = Field(description="任务创建时间，即用户提交造数目标的时刻。")
    updated_at: datetime = Field(description="任务最近一次状态变更时间，用于前端刷新和超时判断。")
    finished_at: datetime | None = Field(default=None, description="任务到达终态（完成/失败/取消）的时间，用于计算造数耗时。")

    @model_validator(mode="after")
    def check_terminal_fields(self) -> TaskRun:
        # 状态机完整性校验：确保终态任务有完整的收口信息，
        # 挂起任务有明确的用户引导信息，完成任务有判定结论。
        if self.status in {TaskRunStatus.COMPLETED, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED}:
            if self.finished_at is None:
                raise ValueError("终态 TaskRun 必须有 finished_at。")
        if self.status == TaskRunStatus.WAITING_USER and not self.pending_question:
            raise ValueError("WAITING_USER 必须有 pending_question。")
        if self.status == TaskRunStatus.WAITING_USER and self.suspend_reason is None:
            raise ValueError("WAITING_USER 必须有 suspend_reason。")
        if self.status == TaskRunStatus.COMPLETED and not self.final_verdict_id:
            raise ValueError("COMPLETED TaskRun 必须有 final_verdict_id。")
        return self

