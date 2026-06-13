"""GDP 造数运行时的领域模型定义。

本文件定义了用户一次造数任务从创建到完成的全部数据结构，涵盖：
- 任务账本（TaskRun）：用户造数目标的完整生命周期记录
- 步骤与动作（PlanStep / Action / ActionAttempt）：目标拆解、场景执行、重试记录
- 证据与判定（Observation / Evidence / Verdict）：从原始响应到结构化结论的判定链
- 变量（Variable）：造数过程中产出和消费的业务数据
- 资源缺口与候选（Requirement / RequirementProposal / SceneCandidate）：为用户目标匹配合适场景的搜索过程
- 审计记录（DecisionRecord）：让用户和运维人员理解"系统为什么这样选择"
- 安全边界（LMProposal）：隔离 AI 模型输出与事实数据，防止模型直接操控任务状态

所有状态机枚举均附带中文语义说明，确保业务含义不被内部编码淹没。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

# 领域对象身份标识类型。
# 每个标识符对应运行时中一类核心实体，用于全链路追踪和审计。
TaskRunId = str       # 一次造数任务的唯一标识
StepId = str          # 造数目标拆解出的业务步骤标识
ActionId = str        # 系统为满足用户需求而执行的动作标识
AttemptId = str       # 动作的每次执行尝试标识（支持重试）
VariableId = str      # 造数过程中产出或消费的业务数据标识
EvidenceId = str      # 判定造数是否成功的证据链标识
VerdictId = str       # 最终判定结论标识
StorageRef = str      # 敏感或大体积数据的安全存储引用（避免明文落库）
HashValue = str       # 数据完整性校验哈希

T = TypeVar("T")


class LMProposal(BaseModel, Generic[T]):  # noqa: UP046
    """AI 模型输出的候选建议，是系统安全边界的核心机制。

    业务目标：防止 AI 模型的"幻觉"或错误输出直接操控造数任务状态。
    所有模型输出必须包装为 LMProposal，经过规则校验和事实接口过滤后，
    才能被采纳为系统中的可信数据。未经校验的 Proposal 只能被丢弃或重新生成。
    """

    proposal_id: str = Field(description="建议唯一标识，用于审计追踪模型输出到最终采纳的完整链路。")
    payload: T = Field(description="模型给出的结构化建议内容，例如场景排序、参数推荐等，尚未被验证为事实。")
    prompt_hash: HashValue = Field(description="生成该建议时所用 Prompt 的哈希，用于复现和审计模型的决策上下文。")
    model_name: str = Field(description="生成该建议的模型名称，用于区分不同模型的建议质量和追溯问题来源。")
    confidence: float = Field(ge=0.0, le=1.0, description="模型自评分数，仅用于候选排序参考，绝不可作为事实依据或直接展示给用户。")


def reject_lm_proposal(value: object) -> None:
    """事实写入接口的安全守卫。

    在所有事实写入路径上拦截 LMProposal 类型，阻止 AI 模型的未验证输出
    绕过安全边界直接写入系统账本。一旦发现 LMProposal 试图写入，立即抛出异常。
    """
    if isinstance(value, LMProposal):
        raise TypeError("LMProposal 不能作为事实写入。")


# ---------- 造数任务生命周期 ----------


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


# ---------- 业务步骤 ----------


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


# ---------- 动作与执行尝试 ----------


class ActionType(StrEnum):
    """动作类型，定义系统为满足用户造数需求可以采取的操作。

    当前仅支持执行已发布的造数场景（EXECUTE_SCENE），
    未来可扩展为查询数据源、调用外部接口等动作类型。
    """

    EXECUTE_SCENE = "EXECUTE_SCENE"  # 执行一个已发布的造数场景，这是当前唯一支持的造数手段


class ActionStatus(StrEnum):
    """动作的执行状态，反映系统为满足用户造数需求而执行的一次操作的进展。

    PLANNED → RUNNING → SUCCEEDED / FAILED / UNKNOWN_STATE
    UNKNOWN_STATE 表示操作已发出但无法确认结果（如网络超时），可能需要用户介入。
    """

    PLANNED = "PLANNED"          # 动作已规划但尚未执行，系统正在准备输入参数
    RUNNING = "RUNNING"          # 场景正在执行中，用户可看到"正在造数"状态
    SUCCEEDED = "SUCCEEDED"      # 场景执行成功，产出数据已可用于后续步骤或证据收集
    FAILED = "FAILED"            # 场景执行失败，系统记录了失败原因，可能触发重试或任务失败
    UNKNOWN_STATE = "UNKNOWN_STATE"  # 场景执行状态不确定（如请求超时），需要用户确认实际结果后才能继续


class Action(BaseModel):
    """系统为满足用户造数需求而规划的一次场景执行动作。

    业务目标：记录"系统准备调用哪个造数场景、用什么参数、是否需要用户审批"。
    当前动作：在步骤执行链路中，Action 介于"计划执行"和"实际调用"之间，
    承载输入参数快照、幂等键（防止重复造数）和审批标记。
    预期结果：Action 创建后进入 RUNNING 状态，驱动后续的 Attempt 执行和证据收集。
    """

    action_id: ActionId = Field(description="动作唯一标识，用于关联该动作下的所有执行尝试和观察结果。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID，标识该动作服务于哪个用户造数目标。")
    step_id: StepId = Field(description="所属业务步骤 ID，标识该动作属于目标拆解的哪一步。")
    action_type: ActionType = Field(description="动作类型，当前仅支持 EXECUTE_SCENE（执行造数场景）。")
    status: ActionStatus = Field(description="动作执行状态，用户可在时间线中看到动作的进展。")
    scene_code: str = Field(min_length=1, description="要执行的造数场景编码，标识系统选择用哪个场景来满足用户需求。")
    input_ref: StorageRef = Field(description="完整输入参数的安全存储引用，避免敏感参数明文落库。")
    input_preview: dict[str, Any] = Field(default_factory=dict, description="可展示的输入摘要，前端展示给用户确认（敏感字段已脱敏）。")
    input_hash: HashValue = Field(description="输入参数哈希，与 task_run_id 和 scene_code 组合构成幂等键。")
    idempotency_key: str = Field(min_length=1, description="幂等键，确保相同参数的造数请求不会被重复执行，防止用户误操作导致重复创建数据。")
    approval_required: bool = Field(description="该场景是否有写副作用需要用户审批，为 true 时系统会在执行前暂停等用户确认。")
    attempt_ids: list[AttemptId] = Field(default_factory=list, description="该动作的所有执行尝试 ID，每次重试会产生一个新的尝试记录。")


class AttemptStatus(StrEnum):
    """场景调用尝试的结果状态。

    每次执行造数场景都会产生一次尝试记录，状态反映本次调用的实际结果：
    RUNNING=正在调用中，SUCCEEDED=调用成功拿到结果，FAILED=调用失败（业务拒绝或技术异常），
    UNKNOWN_STATE=调用发出后无法确认结果（超时/断连），用户可能需要介入确认。
    """

    RUNNING = "RUNNING"          # 场景调用正在进行中
    SUCCEEDED = "SUCCEEDED"      # 本次场景调用成功，已拿到执行结果
    FAILED = "FAILED"            # 本次场景调用失败，可能是业务规则拒绝或技术异常
    UNKNOWN_STATE = "UNKNOWN_STATE"  # 调用发出后结果未知（如超时），禁止盲目重试，需用户或系统确认


class ActionAttempt(BaseModel):
    """Action 的一次实际执行尝试记录，采用 append-only 模式追加。

    业务目标：完整记录每次场景调用的请求快照、响应结果和关联的场景运行记录，
    让用户和运维人员能追溯"第 N 次调用时发生了什么"。
    当前动作：由 execution.py 的 run_action() 创建，是产生外部副作用的唯一出口。
    预期结果：尝试完成后，状态同步到 Action，响应数据供后续 Evidence 抽取事实。
    """

    attempt_id: AttemptId = Field(description="尝试唯一标识，用于关联请求快照和响应结果。")
    action_id: ActionId = Field(description="所属动作 ID，标识该尝试是为哪个执行计划发起的。")
    attempt_no: int = Field(ge=1, description="尝试序号（从 1 开始），同一动作可能因重试产生多次尝试。")
    status: AttemptStatus = Field(description="本次尝试的执行结果状态。")
    request_ref: StorageRef = Field(description="完整请求快照的安全存储引用，供审计追溯"当时发了什么请求"。")
    response_ref: StorageRef | None = Field(default=None, description="完整响应快照的安全存储引用，供审计追溯"返回了什么"。")
    response_preview: dict[str, Any] = Field(default_factory=dict, description="可展示的响应摘要，前端展示执行结果时使用。")
    scene_run_id: str | None = Field(default=None, description="关联的场景执行记录 ID，用户可通过此 ID 下钻查看场景运行的详细步骤和每步请求响应。")
    error_type: str | None = Field(default=None, description="错误类型分类（如 SCENE_FAILED、TIMEOUT、CONNECTION_ERROR），用于前端分类展示和统计。")
    error_message: str | None = Field(default=None, description="人可读的错误摘要，优先取业务规则原因或步骤级友好提示，避免展示机器味堆栈。")
    started_at: datetime = Field(description="本次调用开始时间。")
    finished_at: datetime | None = Field(default=None, description="本次调用结束时间，用于计算单次调用耗时。")


# ---------- 判定链：原始观察 → 可判定证据 → 结果判定 ----------
# 这条链路回答用户最关心的问题：”我的造数目标达成了吗？”
# Observation 保存场景返回的原始数据，Evidence 从中抽取结构化事实，Verdict 基于事实做出判定。


class Observation(BaseModel):
    “””场景执行后的原始观察数据，是证据链的起点。

    业务目标：完整保存场景调用的原始返回结果（HTTP 状态、响应体、错误信息等），
    作为后续证据抽取的唯一数据源，确保判定基于真实观察而非推测。
    “””

    observation_id: str = Field(description=”观察唯一标识。”)
    task_run_id: TaskRunId = Field(description=”所属造数任务 ID。”)
    action_id: ActionId = Field(description=”所属动作 ID。”)
    attempt_id: AttemptId = Field(description=”所属执行尝试 ID，标识这次观察来自哪次调用。”)
    raw_ref: StorageRef = Field(description=”完整原始响应的安全存储引用，供审计人员查看原始返回数据。”)
    preview: dict[str, Any] = Field(default_factory=dict, description=”可展示的观察摘要，包含场景状态码、业务结果和输出数据。”)
    created_at: datetime = Field(description=”观察生成时间。”)


class FactPredicate(StrEnum):
    “””证据事实的判定方式，定义如何验证一个事实是否成立。”””

    EXISTS = “EXISTS”        # 判定某个值是否存在（如”订单号是否存在”）
    EQUALS = “EQUALS”        # 判定某个值是否等于期望值（如”支付状态是否等于 PAID”）
    IN = “IN”                # 判定某个值是否属于某个集合
    NON_EMPTY = “NON_EMPTY”  # 判定某个值是否非空


class EvidenceFact(BaseModel):
    “””一条可判定的事实，是 Verdict 做出判定的最小单元。

    业务目标：把场景执行的原始结果转化为结构化的”预期 vs 实际”对比，
    让用户和系统都能清晰看到”哪里通过了、哪里没通过、为什么没通过”。
    “””

    subject: str = Field(description=”事实主体标识，如 order.pay_status，指明这条事实在检查什么。”)
    predicate: FactPredicate = Field(description=”判定方式，如 EQUALS 表示”期望等于某值”。”)
    expected: Any = Field(description=”期望值，如 PAID 表示期望支付状态为已支付。”)
    actual: Any = Field(description=”实际值，从场景执行结果中提取的真实数据。”)
    passed: bool = Field(description=”是否通过判定，true 表示实际值满足期望。”)
    # detail 承载场景自己算出的精确原因（如命中的失败规则描述）。
    # 业务失败时 Scene 把原因放在 businessResult 里，必须透传到这里，
    # 否则 Verdict 只能给出”执行失败”这种无信息量的结论。
    detail: str | None = Field(default=None, description=”事实的补充说明，如命中的业务规则描述或步骤级友好错误提示，让用户看到'为什么没通过'。”)
    source_observation_id: str = Field(description=”事实来源的观察 ID，确保每条事实都能追溯到原始数据。”)


class Evidence(BaseModel):
    “””从观察中抽取的可判定证据集合，是 Verdict 的唯一输入。

    业务目标：把原始执行结果结构化为”已知事实””缺失事实””未知事实”三类，
    确保判定结论完全基于证据，杜绝 LLM 凭感觉宣布造数成功或失败。
    当前动作：由 evidence.py 的 build_evidence() 从 Observation 中抽取。
    预期结果：Evidence 产出后交给 judge() 做出最终判定。
    “””

    evidence_id: EvidenceId = Field(description=”证据集合唯一标识。”)
    task_run_id: TaskRunId = Field(description=”所属造数任务 ID。”)
    step_id: StepId = Field(description=”所属业务步骤 ID。”)
    action_id: ActionId = Field(description=”所属动作 ID。”)
    facts: list[EvidenceFact] = Field(default_factory=list, description=”已抽取的已知事实，每条事实包含预期值和实际值的对比。”)
    missing_facts: list[str] = Field(default_factory=list, description=”无法抽取的事实（如场景没有返回某字段），缺失将导致判定为 NEED_USER。”)
    unknown_facts: list[str] = Field(default_factory=list, description=”结果不确定的事实（如超时导致不知道执行是否成功），将导致判定为 UNKNOWN_STATE。”)
    created_at: datetime = Field(description=”证据生成时间。”)


class VerdictType(StrEnum):
    “””造数结果判定类型，回答”用户的造数目标达成了吗”。

    DONE：证据充分证明造数成功，用户可看到生成的数据。
    FAILED：证据充分证明造数失败，用户可看到失败原因。
    UNKNOWN_STATE：执行结果不确定（如写操作超时），需用户确认实际状态。
    NEED_USER：证据不足以判定，需用户补充信息。
    “””

    DONE = “DONE”
    FAILED = “FAILED”
    UNKNOWN_STATE = “UNKNOWN_STATE”
    NEED_USER = “NEED_USER”


class Verdict(BaseModel):
    “””基于证据的最终判定结论，驱动任务进入终态或等待状态。

    业务目标：给出用户造数任务的明确结论——成功、失败、结果未知或需要补充信息。
    当前动作：由 verdict.py 的 judge() 基于 Evidence 产出，随后 apply_verdict() 联动更新任务状态。
    预期结果：
      DONE → 任务 COMPLETED，用户看到造数结果
      FAILED → 任务 FAILED，用户看到失败原因
      UNKNOWN_STATE → 任务 WAITING_USER，等用户确认实际状态
      NEED_USER → 任务 WAITING_USER，等用户补充信息
    “””

    verdict_id: VerdictId = Field(description=”判定唯一标识。”)
    task_run_id: TaskRunId = Field(description=”所属造数任务 ID。”)
    step_id: StepId = Field(description=”所属业务步骤 ID。”)
    evidence_id: EvidenceId = Field(description=”引用的证据集合 ID，确保判定结论可追溯到具体证据。”)
    verdict_type: VerdictType = Field(description=”判定类型，决定任务后续走向。”)
    reason: str = Field(description=”人可读的判定原因，如'所有事实通过'或具体失败原因，直接展示给用户。”)
    tainted_variable_ids: list[VariableId] = Field(default_factory=list, description=”被污染的变量 ID 列表，标识因错误资源产出而不可复用的数据。”)
    created_at: datetime = Field(description=”判定生成时间。”)


# ---------- 造数变量：过程中产出和消费的业务数据 ----------


class VariableSource(StrEnum):
    """变量来源类型，标识造数过程中的数据从哪来。

    USER_INPUT：用户手动输入（如金额、卡号）。
    SCENE_OUTPUT：场景执行后产出（如订单号、支付流水号）。
    CONTEXT：从历史造数任务中复用的上下文数据。
    """

    USER_INPUT = "USER_INPUT"
    SCENE_OUTPUT = "SCENE_OUTPUT"
    CONTEXT = "CONTEXT"


class VariableProvenance(BaseModel):
    """变量来源追踪，回答"这个数据是怎么来的"。

    业务目标：让系统能追溯每个变量的产出源头，当下游步骤失败时，
    可以通过 provenance 找到是哪个上游步骤产出了错误数据，精准定位问题。
    """

    source_type: VariableSource = Field(description="变量来源类型：用户输入、场景产出或历史上下文。")
    source_id: str = Field(description="来源对象 ID，如用户 ID（用户输入）或场景运行 ID（场景产出）。")
    action_id: ActionId | None = Field(default=None, description="产出该变量的动作 ID，仅 SCENE_OUTPUT 类型有值。")
    evidence_id: EvidenceId | None = Field(default=None, description="支撑该变量可信性的证据 ID，确保变量值有判定依据。")


class Variable(BaseModel):
    """造数过程中的业务数据变量，在步骤间传递和复用。

    业务目标：记录造数过程中每个关键数据项（订单号、卡号、金额等）的值、来源和可信状态。
    当上游步骤产出的数据被下游步骤消费时，变量是数据传递的桥梁。
    变量可被标记为 tainted（污染），表示该数据来自错误资源、不可再被下游使用。
    """

    variable_id: VariableId = Field(description="变量唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    name: str = Field(description="变量名，如 order_id、card_no。")
    semantic_type: str = Field(description="语义类型，如 ORDER_ID、CARD_NO，用于跨任务复用时的类型匹配。")
    value_ref: StorageRef = Field(description="完整值的安全存储引用，避免敏感数据明文暴露。")
    value_preview: str = Field(description="可展示的值摘要，如卡号尾号或订单号前缀，供前端展示。")
    sensitive: bool = Field(description="是否敏感数据，敏感值在日志和前端展示中会被脱敏。")
    tainted: bool = Field(default=False, description="是否已被污染，污染后的变量禁止被下游步骤自动使用。")
    provenance: VariableProvenance = Field(description="变量来源追踪信息，支持下游失败时回溯定位问题。")
    consumed_by: list[StepId] = Field(default_factory=list, description="消费该变量的步骤列表，标识数据流向。")
    created_at: datetime = Field(description="变量创建时间。")


# ---------- 资源缺口与候选场景（第二阶段：Catalog 驱动的 Scene 选择） ----------


class RequirementLayer(StrEnum):
    """资源缺口层级，定义系统为用户寻找的资源类型。

    当前仅支持 SCENE（已发布造数场景），未来扩展 SOURCE（数据源）和 INFRA（基础设施配置）。
    """

    SCENE = "SCENE"  # 寻找已发布的造数场景来满足用户需求


class RequirementStatus(StrEnum):
    """资源缺口状态，反映系统为用户找到合适场景的进展。

    PENDING：缺口刚创建，尚未开始搜索候选场景。
    RESOLVING：已搜索到候选场景，等待系统自动选定或用户手动选择。
    SATISFIED：已选定场景编码，缺口已满足，可以进入执行阶段。
    FAILED：无法满足缺口（零候选或用户放弃），可能导致任务失败。
    """

    PENDING = "PENDING"
    RESOLVING = "RESOLVING"
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"


class Requirement(BaseModel):
    """用户造数步骤的资源缺口——"为了完成这一步，系统需要找到一个合适的造数场景"。

    业务目标：结构化表达当前步骤需要什么资源，追踪搜索进度和选定结果。
    当前动作：在 runner.py 的 run_task 中创建，驱动 catalog 搜索和候选选择流程。
    预期结果：缺口被满足（SATISFIED）后进入场景执行阶段；无法满足（FAILED）则任务收口。
    """

    requirement_id: str = Field(description="缺口唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId = Field(description="所属业务步骤 ID，标识这个缺口是为了完成哪个步骤。")
    layer: RequirementLayer = Field(description="缺口层级，当前固定 SCENE（寻找已发布场景）。")
    goal: str = Field(min_length=1, description="缺口要满足的目标描述，通常继承步骤的业务目标。")
    status: RequirementStatus = Field(description="缺口当前状态，决定流程走向。")
    proposal_id: str | None = Field(default=None, description="当前候选集 Proposal ID，关联到本次搜索结果。")
    selected_scene_code: str | None = Field(default=None, description="已选定的场景编码，SATISFIED 时必有值。")
    blacklist: list[str] = Field(default_factory=list, description="已失败或被拒的场景编码黑名单，重搜时自动排除。")
    created_at: datetime = Field(description="缺口创建时间。")
    updated_at: datetime = Field(description="缺口最近更新时间。")


# ---------- 候选集与场景候选 ----------


class SceneCandidate(BaseModel):
    """搜索结果中的一个候选造数场景，来自 Catalog 的确定性检索。

    业务目标：为用户展示"系统找到了哪些可用的造数方案"，每个候选包含评分、
    命中理由、缺失入参和是否需要审批等信息，帮助用户或系统做出选择。
    注意：这是事实数据（Catalog 检索结果），不是 LLM 建议。
    """

    scene_code: str = Field(description="候选场景编码，唯一标识一个已发布的造数场景。")
    scene_name: str = Field(description="候选场景名称，直接展示给用户。")
    score: float = Field(ge=0.0, le=1.0, description="Catalog 综合评分，仅用于排序候选，不作为事实依据。")
    reasons: list[str] = Field(default_factory=list, description="命中理由列表，如'目标语义匹配''环境可用'，可直接展示给用户。")
    missing_inputs: list[str] = Field(default_factory=list, description="当前入参和变量栈尚不能绑定的必填字段，非空时需等用户补充后才能执行。")
    requires_confirmation: bool = Field(description="执行前是否需要用户审批，有写副作用的场景为 true。")
    contract_hash: HashValue = Field(description="候选契约快照哈希，执行前记录，未来用于检测场景契约是否发生漂移。")


class ProposalStatus(StrEnum):
    """候选集状态，反映一次搜索产出的候选方案的选定进展。

    PENDING：候选已生成，等待选定（系统自动或用户手动）。
    SELECTED：某个候选已被选定，即将进入执行准备阶段。
    REJECTED：全部候选被拒或用户放弃，可能导致重新搜索或任务失败。
    """

    PENDING = "PENDING"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


class SelectionSource(StrEnum):
    """选定场景的来源，用于审计"是谁/什么选了这个场景"。

    AUTO：系统规则自动选定（单候选高置信、入参齐全、无需审批）。
    USER：用户在多候选中手动选定。
    LLM：采纳了 AI 模型的排序建议，但仍经规则校验后采纳。
    EXPLICIT：用户启动时直接指定了场景编码。
    """

    AUTO = "AUTO"
    USER = "USER"
    LLM = "LLM"
    EXPLICIT = "EXPLICIT"


class RequirementProposal(BaseModel):
    """一次搜索产出的候选场景集合和选择结果。

    业务目标：记录"系统搜到了哪些场景、最终选了哪个、谁选的"，
    是连接搜索（catalog.search）和选定（apply_selection）的中间账本。
    """

    proposal_id: str = Field(description="候选集唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId = Field(description="所属业务步骤 ID。")
    requirement_id: str = Field(description="所属资源缺口 ID，标识这次搜索是为了满足哪个缺口。")
    candidates: list[SceneCandidate] = Field(default_factory=list, description="按评分倒序排列的候选场景列表。")
    query_terms: list[str] = Field(default_factory=list, description="参与检索的关键词和别名，供用户理解搜索条件。")
    status: ProposalStatus = Field(description="候选集当前状态。")
    selected_scene_code: str | None = Field(default=None, description="被选定的场景编码，SELECTED 时必有值。")
    selection_source: SelectionSource | None = Field(default=None, description="选定来源：AUTO/USER/LLM/EXPLICIT。")
    created_at: datetime = Field(description="候选集创建时间。")


# ---------- AI 模型排序建议（可选，默认关闭） ----------


class SceneSelectionSuggestion(BaseModel):
    """AI 模型在已检索候选中给出的排序建议，只能用于排序参考，不能直接定案。

    这是安全边界的一部分：即使模型给出了排序建议，也必须经过规则校验后才能被采纳。
    """

    ranked_scene_codes: list[str] = Field(default_factory=list, description="AI 建议的候选优先级排序。")
    explanation: str = Field(default="", description="AI 给出的选择解释，供规则校验后参考。")


# ---------- 决策审计账本（回答"系统为什么这样选"） ----------


class DecisionKind(StrEnum):
    """决策类型，标识系统做出的选择属于哪个业务环节。

    SCENE_SEARCH：场景检索决策——记录系统搜到了哪些候选。
    SCENE_SELECTION：场景选择决策——记录系统/用户选了哪个候选、为什么。
    APPROVAL_REQUIREMENT：审批要求决策——记录为什么需要用户审批或审批结果。
    """

    SCENE_SEARCH = "SCENE_SEARCH"
    SCENE_SELECTION = "SCENE_SELECTION"
    APPROVAL_REQUIREMENT = "APPROVAL_REQUIREMENT"


class DecisionSource(StrEnum):
    """决策来源，标识选择是由谁/什么做出的。

    RULE：系统规则自动决策。
    CATALOG：场景目录服务检索结果。
    LLM：AI 模型建议经校验后采纳。
    USER：用户手动选择。
    SYSTEM_DEFAULT：系统默认行为。
    """

    RULE = "RULE"
    CATALOG = "CATALOG"
    LLM = "LLM"
    USER = "USER"
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"


class DecisionStatus(StrEnum):
    """决策记录状态。

    DECIDED：已形成决策，记录了选择结论和理由。
    WAITING_USER：需要用户参与决策，任务暂停等待用户输入。
    SUPERSEDED：已被后续决策取代（如重新搜索后覆盖了旧选择）。
    FAILED：决策过程失败（如搜索无候选）。
    """

    DECIDED = "DECIDED"
    WAITING_USER = "WAITING_USER"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"


class DecisionOption(BaseModel):
    """决策候选项，记录当时有哪些可选方案供用户和审计人员查看。"""

    option_id: str = Field(description="候选项 ID，如 scene_code。")
    option_type: str = Field(description="候选项类型，如 scene、http_source。")
    label: str = Field(description="候选项展示名称，直接展示给用户。")
    score: float | None = Field(default=None, ge=0.0, le=1.0, description="候选项评分，没有评分时为空。")
    reasons: list[str] = Field(default_factory=list, description="候选项进入候选集的理由。")
    metadata: dict[str, Any] = Field(default_factory=dict, description="候选项补充元数据，默认只放非敏感摘要。")


class DecisionRejection(BaseModel):
    """未选候选项及其拒绝原因，让用户理解"为什么没选这个"。"""

    option_id: str = Field(description="未选候选项 ID。")
    reason: str = Field(description="未选择该候选项的原因说明。")


class DecisionRecord(BaseModel):
    """一次关键决策的结构化审计记录。

    业务目标：让用户和运维人员能回答"系统为什么选了这个场景""还有哪些候选"
    "为什么需要审批"等问题，实现造数过程的可解释性和可追溯性。
    注意：决策记录是审计解释账本，不驱动任务状态机流转。
    """

    decision_id: str = Field(description="决策记录唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId | None = Field(default=None, description="关联的业务步骤 ID，无法关联时为空。")
    requirement_id: str | None = Field(default=None, description="关联的资源缺口 ID，无法关联时为空。")
    proposal_id: str | None = Field(default=None, description="关联的候选集 ID，无法关联时为空。")
    action_id: ActionId | None = Field(default=None, description="关联的动作 ID，无法关联时为空。")
    scene_run_id: str | None = Field(default=None, description="关联的场景运行 ID，决策发生在执行前时为空。")
    decision_kind: DecisionKind = Field(description="决策类型：场景检索/场景选择/审批要求。")
    decision_source: DecisionSource = Field(description="决策来源：规则/目录/模型/用户/系统默认。")
    status: DecisionStatus = Field(description="决策记录状态，不等同于 TaskRunStatus。")
    target_type: str | None = Field(default=None, description="决策目标类型，如 scene。")
    target_id: str | None = Field(default=None, description="决策目标 ID，如被选中的 scene_code。")
    input_ref: StorageRef | None = Field(default=None, description="决策输入快照的存储引用，仅供审计权限读取。")
    options: list[DecisionOption] = Field(default_factory=list, description="本次决策的候选项列表，供审计查看当时有哪些可选方案。")
    selected_option: DecisionOption | None = Field(default=None, description="最终选中的候选项，未决定时为空。")
    selected_reasons: list[str] = Field(default_factory=list, description="选择该候选的理由列表。")
    rejected_reasons: list[DecisionRejection] = Field(default_factory=list, description="未选候选项及拒绝原因。")
    criteria: list[str] = Field(default_factory=list, description="本次决策采用的判断标准。")
    evidence_refs: list[str] = Field(default_factory=list, description="支撑本次决策的账本对象引用。")
    model_info: dict[str, Any] | None = Field(default=None, description="AI 模型参与信息摘要，不包含隐藏思维链。")
    summary: str = Field(description="面向审计展示的一句话中文解释，如'按目标"造已支付订单"检索到 3 个候选场景'。")
    created_at: datetime = Field(description="决策记录创建时间。")
