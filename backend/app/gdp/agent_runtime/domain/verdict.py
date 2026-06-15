"""结果判定领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .identifiers import EvidenceId, StepId, TaskRunId, VariableId, VerdictId


class VerdictType(StrEnum):
    """造数结果判定类型，回答"用户的造数目标达成了吗"。

    DONE：证据充分证明造数成功，用户可看到生成的数据。
    FAILED：证据充分证明造数失败，用户可看到失败原因。
    UNKNOWN_STATE：执行结果不确定（如写操作超时），需用户确认实际状态。
    NEED_USER：证据不足以判定，需用户补充信息。
    """

    DONE = "DONE"
    FAILED = "FAILED"
    UNKNOWN_STATE = "UNKNOWN_STATE"
    NEED_USER = "NEED_USER"


class Verdict(BaseModel):
    """基于证据的最终判定结论，驱动任务进入终态或等待状态。

    业务目标：给出用户造数任务的明确结论——成功、失败、结果未知或需要补充信息。
    当前动作：由 verdict.py 的 judge() 基于 Evidence 产出，随后 apply_verdict() 联动更新任务状态。
    预期结果：
      DONE → 任务 COMPLETED，用户看到造数结果
      FAILED → 任务 FAILED，用户看到失败原因
      UNKNOWN_STATE → 任务 WAITING_USER，等用户确认实际状态
      NEED_USER → 任务 WAITING_USER，等用户补充信息
    """

    verdict_id: VerdictId = Field(description="判定唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId = Field(description="所属业务步骤 ID。")
    evidence_id: EvidenceId = Field(description="引用的证据集合 ID，确保判定结论可追溯到具体证据。")
    verdict_type: VerdictType = Field(description="判定类型，决定任务后续走向。")
    reason: str = Field(description="人可读的判定原因，如'所有事实通过'或具体失败原因，直接展示给用户。")
    tainted_variable_ids: list[VariableId] = Field(default_factory=list, description="被污染的变量 ID 列表，标识因错误资源产出而不可复用的数据。")
    created_at: datetime = Field(description="判定生成时间。")
