"""造数任务 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gdp.models import InputFieldDefinition, SceneStatus, VersionStatus


# ── 任务步骤定义 ──────────────────────────────────────────────────────


class TaskStepDefinition(BaseModel):
    """任务步骤——引用一个已发布的造数场景。"""
    model_config = ConfigDict(extra="allow")

    stepId: str = Field(..., min_length=1, max_length=128)
    sceneCode: str = Field(..., min_length=1, max_length=128)
    stepName: str | None = None
    enabled: bool = True
    dependsOn: list[str] = Field(default_factory=list)
    inputMapping: dict[str, Any] = Field(default_factory=dict)
    outputMapping: dict[str, str] = Field(default_factory=dict)


# ── 任务定义 ──────────────────────────────────────────────────────────


class TaskDefinition(BaseModel):
    taskCode: str = Field(..., min_length=1, max_length=128)
    taskName: str = Field(..., min_length=1, max_length=256)
    taskRemark: str | None = None
    environmentField: str = "env"
    inputSchema: list[InputFieldDefinition] = Field(default_factory=list)
    steps: list[TaskStepDefinition] = Field(default_factory=list)
    resultMapping: dict[str, Any] = Field(default_factory=dict)
    status: SceneStatus = SceneStatus.DRAFT

    @field_validator("environmentField")
    @classmethod
    def environment_field_must_be_env(cls, value: str) -> str:
        if value != "env":
            raise ValueError("environmentField V1 fixed to env")
        return value


# ── 摘要与版本 ────────────────────────────────────────────────────────


class TaskSummary(BaseModel):
    id: str
    taskCode: str
    taskName: str
    taskRemark: str | None = None
    status: SceneStatus
    currentVersionNo: int | None = None
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


class TaskVersion(BaseModel):
    id: str
    taskCode: str
    versionNo: int
    versionStatus: VersionStatus
    definition: TaskDefinition
    validationResult: dict[str, Any] | None = None
    createdBy: str | None = None
    createdAt: datetime
    publishedBy: str | None = None
    publishedAt: datetime | None = None


# ── 校验相关 ──────────────────────────────────────────────────────────


class TaskValidationIssue(BaseModel):
    field: str
    message: str
    level: Literal["ERROR", "WARNING"] = "ERROR"


class TaskValidationResult(BaseModel):
    valid: bool
    issues: list[TaskValidationIssue] = Field(default_factory=list)


class DisableResponse(BaseModel):
    success: bool = True
