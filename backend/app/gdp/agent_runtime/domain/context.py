"""跨任务上下文领域模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .identifiers import StorageRef, TaskRunId, VariableId


class ContextItem(BaseModel):
    """可跨任务显式复用的历史上下文事实。

    业务目标：把已完成任务中可信的场景输出变量沉淀为可查询、可选择、
    可追溯的上下文项，让后续任务能在安全校验后复用这些业务值。
    """

    context_item_id: str = Field(description="上下文项唯一标识。")
    source_task_run_id: TaskRunId = Field(description="产出该上下文项的来源任务 ID。")
    source_variable_id: VariableId = Field(description="产出该上下文项的来源变量 ID。")
    thread_id: str = Field(description="上下文项所属线程 ID，用于限定同一会话内复用。")
    user_id: str = Field(description="上下文项所属用户 ID，用于隔离不同用户数据。")
    env_code: str | None = Field(default=None, description="上下文项所属环境编码，导入时需与目标任务环境兼容。")
    name: str = Field(description="上下文变量名，如 order_id、card_no。")
    semantic_type: str = Field(description="上下文语义类型，如 ORDER_ID、CARD_NO。")
    value_ref: StorageRef = Field(description="完整值的安全存储引用，仅内部账本使用，不向普通查询接口暴露。")
    value_preview: str = Field(description="可向用户展示的值摘要。")
    sensitive: bool = Field(description="是否为敏感值，敏感值只展示脱敏摘要。")
    tainted: bool = Field(description="是否已被污染，污染上下文禁止复用。")
    reusable: bool = Field(description="是否允许被后续任务显式复用。")
    expires_at: datetime | None = Field(default=None, description="过期时间。为空表示当前不过期。")
    created_at: datetime = Field(description="上下文项创建时间。")
