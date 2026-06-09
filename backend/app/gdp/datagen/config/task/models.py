"""造数任务控制面 Pydantic 数据模型。

本模块描述用户级造数任务的前后端契约。Task 记录自然语言目标、
执行阶段、计划、变量栈、步骤历史和审计事件，是 Agent 编排过程的
业务权威状态。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DatagenTaskStatus(StrEnum):
    """造数任务运行状态。"""

    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DatagenTaskPhase(StrEnum):
    """造数任务当前 Agent 阶段。"""

    INTAKE = "INTAKE"
    SCENE_FULFILLMENT = "SCENE_FULFILLMENT"
    SCENE_EXECUTING = "SCENE_EXECUTING"
    PROGRESS_REFLECTION = "PROGRESS_REFLECTION"
    SCENE_DESIGN = "SCENE_DESIGN"
    SOURCE_CONFIG = "SOURCE_CONFIG"
    INFRA_CONFIG = "INFRA_CONFIG"
    WAITING_USER = "WAITING_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DatagenTaskStepType(StrEnum):
    """造数任务步骤类型。"""

    RUN_SCENE = "RUN_SCENE"
    DESIGN_SCENE = "DESIGN_SCENE"
    CONFIG_HTTP_SOURCE = "CONFIG_HTTP_SOURCE"
    CONFIG_SQL_SOURCE = "CONFIG_SQL_SOURCE"
    CONFIG_INFRA = "CONFIG_INFRA"
    ASK_USER = "ASK_USER"
    REFLECT = "REFLECT"


class DatagenTaskStepStatus(StrEnum):
    """造数任务步骤状态。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    WAITING_USER = "WAITING_USER"


class DatagenTaskEnvSource(StrEnum):
    """任务环境来源。"""

    USER_EXPLICIT = "USER_EXPLICIT"
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"


class GoalStackItem(BaseModel):
    """递归目标栈条目。"""

    goalType: str = Field(..., min_length=1, max_length=128, description="目标类型，例如 DATAGEN_TASK、DESIGN_SCENE、CONFIG_HTTP_SOURCE。")
    goal: str = Field(..., min_length=1, description="目标描述，用于回到父目标时继续推进。")
    phase: DatagenTaskPhase = Field(..., description="该目标对应的 Agent 阶段。")


class VisibleVariableValueSize(BaseModel):
    """变量全量值规模摘要。"""

    charCount: int | None = Field(default=None, ge=0, description="字符串化后的字符数。")
    itemCount: int | None = Field(default=None, ge=0, description="数组或行集元素数量。")


class VisibleVariable(BaseModel):
    """Agent 可见变量。"""

    name: str = Field(..., min_length=1, max_length=128, description="变量名，供后续步骤引用。")
    source: str = Field(..., min_length=1, description="变量来源表达式或存储引用。")
    semanticType: str | None = Field(default=None, max_length=128, description="变量业务语义类型，例如 ORDER_ID、USER_ID。")
    label: str | None = Field(default=None, description="变量中文名或展示名。")
    value: Any = Field(default=None, description="变量全量值，落库保存，默认不直接注入 Agent Prompt。")
    valueSchema: dict[str, Any] | None = Field(default=None, description="变量结构摘要，用于 Agent 理解值结构。")
    valuePreview: Any = Field(default=None, description="变量短预览，用于注入 Agent Prompt。")
    valueSize: VisibleVariableValueSize | None = Field(default=None, description="变量全量值规模摘要。")
    storageRef: str | None = Field(default=None, description="大对象外置存储引用。")
    sensitive: bool = Field(default=False, description="是否敏感。敏感值不应注入 Agent Prompt。")
    confidence: float = Field(default=1.0, ge=0, le=1, description="变量语义识别置信度。")


class DatagenTaskPlanStep(BaseModel):
    """造数任务计划步骤。"""

    stepNo: int = Field(..., ge=1, description="计划步骤序号。")
    stepType: DatagenTaskStepType = Field(..., description="计划步骤类型。")
    goal: str = Field(..., min_length=1, description="该步骤要完成的子目标。")
    status: DatagenTaskStepStatus = Field(default=DatagenTaskStepStatus.PENDING, description="计划步骤当前状态。")


class DatagenTaskPlan(BaseModel):
    """造数任务总体计划。"""

    summary: str | None = Field(default=None, description="总体计划摘要。")
    steps: list[DatagenTaskPlanStep] = Field(default_factory=list, description="计划步骤列表。")


class DatagenTaskRunCreateRequest(BaseModel):
    """创建造数任务请求。"""

    userIntent: str = Field(..., min_length=1, description="用户原始自然语言造数目标。")
    envCode: str | None = Field(default=None, min_length=1, max_length=64, description="用户明确指定或前端已解析出的环境编码。为空时后端默认 DEV。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="用户随任务一起提供的结构化输入。")


class DatagenTaskRunResponse(BaseModel):
    """造数任务运行响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    taskRunId: str = Field(..., description="任务运行业务 ID。")
    deerflowThreadId: str | None = Field(default=None, description="绑定的 DeerFlow thread ID。")
    deerflowRunId: str | None = Field(default=None, description="最近一次 DeerFlow run ID。")
    lastCheckpointId: str | None = Field(default=None, description="最近一次 LangGraph checkpoint ID。")
    userIntent: str = Field(..., description="用户原始自然语言造数目标。")
    normalizedGoal: dict[str, Any] = Field(default_factory=dict, description="Agent 归一化后的结构化任务目标。")
    envCode: str = Field(..., description="本任务使用的目标环境编码。")
    envSource: DatagenTaskEnvSource = Field(..., description="任务环境来源。")
    status: DatagenTaskStatus = Field(..., description="任务运行状态。")
    phase: DatagenTaskPhase = Field(..., description="任务当前阶段。")
    pendingInterrupts: dict[str, Any] | None = Field(default=None, description="等待用户输入时的中断上下文。")
    goalStack: list[GoalStackItem] = Field(default_factory=list, description="递归目标栈。")
    plan: DatagenTaskPlan | None = Field(default=None, description="当前任务计划。")
    visibleVariables: list[VisibleVariable] = Field(default_factory=list, description="当前变量栈。")
    reflection: dict[str, Any] | None = Field(default=None, description="当前阶段反思结果。")
    failureType: str | None = Field(default=None, description="失败类型。")
    failureMessage: str | None = Field(default=None, description="失败说明。")
    finalSummary: str | None = Field(default=None, description="最终总结。")
    createdBy: str | None = Field(default=None, description="创建人标识。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")
    finishedAt: datetime | None = Field(default=None, description="任务结束时间。")


class DatagenTaskStepResponse(BaseModel):
    """造数任务步骤响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    taskRunId: str = Field(..., description="所属任务运行 ID。")
    taskStepId: str = Field(..., description="任务步骤业务 ID。")
    stepNo: int = Field(..., description="步骤序号。")
    phase: DatagenTaskPhase = Field(..., description="步骤所在阶段。")
    stepType: DatagenTaskStepType = Field(..., description="步骤类型。")
    goal: str = Field(..., description="步骤目标。")
    status: DatagenTaskStepStatus = Field(..., description="步骤状态。")
    selectedResource: dict[str, Any] | None = Field(default=None, description="选中的场景、Source 或基础配置。")
    inputBinding: dict[str, Any] | None = Field(default=None, description="步骤入参绑定。")
    output: dict[str, Any] | None = Field(default=None, description="步骤输出。")
    sceneRunId: str | None = Field(default=None, description="如果调用了场景，对应的场景运行 ID。")
    errorType: str | None = Field(default=None, description="步骤错误类型。")
    errorMessage: str | None = Field(default=None, description="步骤错误说明。")
    startedAt: datetime | None = Field(default=None, description="步骤开始时间。")
    finishedAt: datetime | None = Field(default=None, description="步骤结束时间。")


class DatagenTaskEventResponse(BaseModel):
    """造数任务审计事件响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    taskRunId: str = Field(..., description="所属任务运行 ID。")
    eventId: str = Field(..., description="事件业务 ID。")
    eventNo: int = Field(..., ge=1, description="任务内事件序号，用于稳定还原审计事件发生顺序。")
    eventType: str = Field(..., description="事件类型。")
    phase: DatagenTaskPhase = Field(..., description="事件发生阶段。")
    message: str = Field(..., description="人类可读事件说明。")
    payload: dict[str, Any] = Field(default_factory=dict, description="事件结构化详情。")
    createdAt: datetime = Field(..., description="事件发生时间。")


class DatagenTaskUserReplyRequest(BaseModel):
    """用户回复任务中断请求。"""

    reply: Any = Field(..., description="用户回复内容。任务绑定 DeerFlow thread 且处于 WAITING_USER 时会用于 Command(resume=...)。")


class DatagenTaskContinueResponse(BaseModel):
    """造数任务推进响应。"""

    taskRun: DatagenTaskRunResponse = Field(..., description="推进后的任务状态。")
    message: str = Field(..., description="本次推进结果说明。")


class DatagenTaskSummaryResponse(BaseModel):
    """造数任务摘要响应。"""

    taskRunId: str = Field(..., description="任务运行业务 ID。")
    status: DatagenTaskStatus = Field(..., description="任务状态。")
    phase: DatagenTaskPhase = Field(..., description="任务阶段。")
    finalSummary: str | None = Field(default=None, description="最终总结。")
    failureType: str | None = Field(default=None, description="失败类型。")
    failureMessage: str | None = Field(default=None, description="失败说明。")
