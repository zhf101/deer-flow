"""Agent Runtime API 请求响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models import ContextItem, ReplyType, TaskRun


class CreateTaskRunRequest(BaseModel):
    """创建造数任务的请求体。

    用户交互契约：用户在此提交造数目标（如"创建一笔已支付的订单"），系统据此搜索匹配的场景。
    """

    user_goal: str = Field(min_length=1, description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")
    thread_id: str | None = Field(default=None, description="所属线程 ID。为空时系统自动创建新线程。")


class StartTaskRunRequest(BaseModel):
    """启动造数任务的请求体。

    用户交互契约：用户可显式指定要执行的场景并提供输入参数；
    不指定时系统将根据造数目标自动搜索并选择场景。
    """

    scene_code: str | None = Field(default=None, description="显式指定 Scene 编码。为空则由系统按目标搜索。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Scene 输入参数。")
    context_item_ids: list[str] = Field(default_factory=list, description="显式选择要导入本次任务的历史上下文项 ID。")


class ContextItemResponse(BaseModel):
    """可复用上下文项安全响应。"""

    context_item_id: str = Field(description="上下文项 ID。")
    source_task_run_id: str = Field(description="来源任务 ID。")
    source_variable_id: str = Field(description="来源变量 ID。")
    thread_id: str = Field(description="所属线程 ID。")
    user_id: str = Field(description="所属用户 ID。")
    env_code: str | None = Field(default=None, description="所属环境编码。")
    name: str = Field(description="变量名。")
    semantic_type: str = Field(description="语义类型。")
    value_preview: str = Field(description="可展示值摘要。")
    sensitive: bool = Field(description="是否敏感。")
    tainted: bool = Field(description="是否已污染。")
    reusable: bool = Field(description="是否可复用。")
    expires_at: str | None = Field(default=None, description="过期时间，ISO 8601 字符串。")
    created_at: str = Field(description="创建时间，ISO 8601 字符串。")


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


class RollbackPlanRequest(BaseModel):
    """生成回退计划的请求体。"""

    failed_step_id: str | None = Field(default=None, description="指定要分析的失败步骤 ID。为空时系统自动选择最近的污染失败步骤。")


class RollbackPlanResponse(BaseModel):
    """用户驱动回退计划响应。"""

    task_run_id: str = Field(description="任务运行 ID。")
    failed_step_id: str = Field(description="触发回退分析的失败步骤 ID。")
    rollback_candidate_step_ids: list[str] = Field(description="建议纳入用户确认的回退步骤 ID。")
    tainted_variable_ids: list[str] = Field(description="被污染变量 ID。")
    affected_step_ids: list[str] = Field(description="受污染变量或失败链路影响的步骤 ID。")
    reasons: list[str] = Field(description="生成该计划的原因说明。")
    safety_warnings: list[str] = Field(description="安全提示。")
    can_auto_replay: bool = Field(description="当前 MVP 是否允许自动重放。")


class RollbackReplayRequest(BaseModel):
    """用户选择回退点后创建替代任务重放的请求体。"""

    rollback_step_id: str = Field(min_length=1, description="用户从回退计划候选中选择的步骤 ID。")
    failed_step_id: str | None = Field(default=None, description="指定要分析的失败步骤 ID。为空时系统自动选择最近的污染失败步骤。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="替代任务重放时覆盖或补充的输入参数。")
    scene_code: str | None = Field(default=None, description="替代任务显式场景编码。为空时沿用来源任务启动请求。")


class RollbackReplayResponse(BaseModel):
    """替代任务重放响应。"""

    source_task_run_id: str = Field(description="来源失败任务 ID。")
    replacement_task_run: TaskRunResponse = Field(description="新创建并启动的替代任务。")
    selected_rollback_step_id: str = Field(description="用户选择的回退候选步骤 ID。")
    failed_step_id: str = Field(description="触发回退分析的失败步骤 ID。")
    tainted_variable_ids: list[str] = Field(description="污染变量 ID。")
    affected_step_ids: list[str] = Field(description="受影响步骤 ID。")
    carried_input_names: list[str] = Field(description="从来源启动请求沿用的输入字段名。")
    replay_mode: str = Field(description="回退执行模式。当前固定为 REPLACEMENT_TASK_RUN。")


class TaskRunResponse(BaseModel):
    """TaskRun 状态响应。"""

    task_run_id: str = Field(description="任务运行 ID。")
    status: str = Field(description="任务当前状态。")
    user_goal: str = Field(description="用户原始造数目标。")
    env_code: str | None = Field(default=None, description="目标环境编码。")
    suspend_reason: str | None = Field(default=None, description="挂起原因。仅 WAITING_USER 时有值，用于前端和审计识别恢复类型。")
    pending_question: str | None = Field(default=None, description="等待用户输入时展示的问题。")
    failure_reason: str | None = Field(default=None, description="终态失败时的可读原因。")
    recovery_source_task_run_id: str | None = Field(default=None, description="替代任务重放的来源任务 ID。普通任务为空。")
    recovery_selected_step_id: str | None = Field(default=None, description="用户选择的回退候选步骤 ID。普通任务为空。")
    recovery_failed_step_id: str | None = Field(default=None, description="触发回退重放的失败步骤 ID。普通任务为空。")
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
        recovery_source_task_run_id=task_run.recovery_source_task_run_id,
        recovery_selected_step_id=task_run.recovery_selected_step_id,
        recovery_failed_step_id=task_run.recovery_failed_step_id,
        created_at=task_run.created_at.isoformat(),
        updated_at=task_run.updated_at.isoformat(),
        finished_at=task_run.finished_at.isoformat() if task_run.finished_at else None,
    )


def to_context_item_response(item: ContextItem) -> ContextItemResponse:
    """将上下文项映射为安全 API 响应。"""

    return ContextItemResponse(
        context_item_id=item.context_item_id,
        source_task_run_id=item.source_task_run_id,
        source_variable_id=item.source_variable_id,
        thread_id=item.thread_id,
        user_id=item.user_id,
        env_code=item.env_code,
        name=item.name,
        semantic_type=item.semantic_type,
        value_preview=item.value_preview,
        sensitive=item.sensitive,
        tainted=item.tainted,
        reusable=item.reusable,
        expires_at=item.expires_at.isoformat() if item.expires_at else None,
        created_at=item.created_at.isoformat(),
    )
