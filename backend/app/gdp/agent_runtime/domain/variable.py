"""造数变量领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .identifiers import ActionId, EvidenceId, StepId, StorageRef, TaskRunId, VariableId


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
