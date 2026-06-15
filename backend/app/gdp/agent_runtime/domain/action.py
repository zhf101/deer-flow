"""动作与执行尝试领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .identifiers import ActionId, AttemptId, HashValue, StepId, StorageRef, TaskRunId


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
    request_ref: StorageRef = Field(description="完整请求快照的安全存储引用，供审计追溯当时发了什么请求")
    response_ref: StorageRef | None = Field(default=None, description="完整响应快照的安全存储引用，供审计追溯返回了什么")
    response_preview: dict[str, Any] = Field(default_factory=dict, description="可展示的响应摘要，前端展示执行结果时使用。")
    scene_run_id: str | None = Field(default=None, description="关联的场景执行记录 ID，用户可通过此 ID 下钻查看场景运行的详细步骤和每步请求响应。")
    error_type: str | None = Field(default=None, description="错误类型分类（如 SCENE_FAILED、TIMEOUT、CONNECTION_ERROR），用于前端分类展示和统计。")
    error_message: str | None = Field(default=None, description="人可读的错误摘要，优先取业务规则原因或步骤级友好提示，避免展示机器味堆栈。")
    started_at: datetime = Field(description="本次调用开始时间。")
    finished_at: datetime | None = Field(default=None, description="本次调用结束时间，用于计算单次调用耗时。")
