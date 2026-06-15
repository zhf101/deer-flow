"""Agent Runtime API 请求响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models import ReplyType, TaskRun


class CreateTaskRunRequest(BaseModel):
    """创建造数任务的请求体。

    用户交互契约：用户在此提交造数目标（如"创建一笔已支付的订单"），系统据此搜索匹配的场景。
    """

    user_goal: str = Field(min_length=1, description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")


class StartTaskRunRequest(BaseModel):
    """启动造数任务的请求体。

    用户交互契约：用户可显式指定要执行的场景并提供输入参数；
    不指定时系统将根据造数目标自动搜索并选择场景。
    """

    scene_code: str | None = Field(default=None, description="显式指定 Scene 编码。为空则由系统按目标搜索。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Scene 输入参数。")


class ReplyTaskRunRequest(BaseModel):
    """恢复被暂停的任务的请求体。

    用户交互契约：当任务因等待用户操作（审批、补充输入、选择场景等）而挂起时，
    用户通过此接口提交回复，驱动任务继续执行。
    """

    reply_type: ReplyType = Field(
        description=(
            "回复类型。APPROVE：批准已选定且待审批的场景。"
            "SUPPLY_INPUT：补充缺失输入。"
            "CONFIRM_UNKNOWN_STATE：确认执行结果未知并停止。"
            "SELECT_SCENE：在候选中选定场景，可携带 approved=true 表示选择并批准。"
            "SUPPLY_SCENE_CODE：零候选时手动补 scene_code。"
        )
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="回复内容。SELECT_SCENE / SUPPLY_SCENE_CODE 需含 scene_code；选择可带 approved。",
    )


class TaskRunResponse(BaseModel):
    """TaskRun 状态响应。"""

    task_run_id: str = Field(description="任务运行 ID。")
    status: str = Field(description="任务当前状态。")
    user_goal: str = Field(description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")
    suspend_reason: str | None = Field(default=None, description="挂起原因。仅 WAITING_USER 时有值，用于前端和审计识别恢复类型。")
    pending_question: str | None = Field(default=None, description="等待用户输入时展示的问题。")
    failure_reason: str | None = Field(default=None, description="终态失败时的可读原因。")
    created_at: str = Field(description="创建时间，ISO 8601 字符串。")
    updated_at: str = Field(description="更新时间，ISO 8601 字符串。")
    finished_at: str | None = Field(default=None, description="结束时间，非终态为空。")


class RuntimePayloadResponse(BaseModel):
    """Runtime payload 详情响应。"""

    ref: str = Field(description="payload 引用。")
    payload: Any = Field(description="payload 完整内容。")


def to_response(task_run: TaskRun) -> TaskRunResponse:
    """将领域 TaskRun 映射为 API 响应模型。"""

    return TaskRunResponse(
        task_run_id=task_run.task_run_id,
        status=task_run.status,
        user_goal=task_run.user_goal,
        env_code=task_run.env_code,
        suspend_reason=task_run.suspend_reason,
        pending_question=task_run.pending_question,
        failure_reason=task_run.failure_reason,
        created_at=task_run.created_at.isoformat(),
        updated_at=task_run.updated_at.isoformat(),
        finished_at=task_run.finished_at.isoformat() if task_run.finished_at else None,
    )
