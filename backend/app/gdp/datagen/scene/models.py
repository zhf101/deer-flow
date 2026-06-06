"""造数场景 Pydantic 数据模型（步骤引用 httpsource/sqlsource 模式）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gdp.models import (
    AssertionDefinition,
    InputFieldDefinition,
    Position,
    SceneStatus,
    StepType,
    VersionStatus,
)


# ── 步骤定义（引用模式） ──────────────────────────────────────────────


class StepDefinition(BaseModel):
    """场景步骤定义——通过 sourceCode 引用 httpsource/sqlsource。

    HTTP 步骤引用 httpSourceCode，SQL 步骤引用 sqlSourceCode，
    ASSERT 和 TRANSFORM 步骤保持内联配置。
    """
    model_config = ConfigDict(extra="allow")

    # ── 公共字段 ──
    stepId: str = Field(..., min_length=1, max_length=128)
    stepName: str | None = None
    type: StepType
    enabled: bool = True
    dependsOn: list[str] = Field(default_factory=list)
    description: str | None = None
    position: Position | None = None

    # ── HTTP 步骤：引用 httpsource ──
    httpSourceCode: str | None = None
    httpParamMapping: dict[str, Any] = Field(default_factory=dict)

    # ── SQL 步骤：引用 sqlsource ──
    sqlSourceCode: str | None = None
    sqlParamMapping: dict[str, Any] = Field(default_factory=dict)

    # ── ASSERT 步骤 ──
    assertions: list[AssertionDefinition] = Field(default_factory=list)

    # ── TRANSFORM 步骤 ──
    assignments: dict[str, str] = Field(default_factory=dict)


# ── 批量配置 ──────────────────────────────────────────────────────────


class BatchConfig(BaseModel):
    enabled: bool = False
    failurePolicy: Literal["STOP_ON_ERROR", "CONTINUE_ON_ERROR"] = "STOP_ON_ERROR"
    maxConcurrency: int = Field(default=1, ge=1, le=20)


# ── 场景定义 ──────────────────────────────────────────────────────────


class SceneDefinition(BaseModel):
    sceneCode: str = Field(..., min_length=1, max_length=128)
    sceneName: str = Field(..., min_length=1, max_length=256)
    sceneRemark: str | None = None
    sceneType: str | None = None
    environmentField: str = "env"
    inputSchema: list[InputFieldDefinition] = Field(default_factory=list)
    steps: list[StepDefinition] = Field(default_factory=list)
    resultMapping: dict[str, Any] = Field(default_factory=dict)
    batchConfig: BatchConfig = Field(default_factory=BatchConfig)
    status: SceneStatus = SceneStatus.DRAFT

    @field_validator("environmentField")
    @classmethod
    def environment_field_must_be_env(cls, value: str) -> str:
        if value != "env":
            raise ValueError("environmentField V1 fixed to env")
        return value


# ── 摘要与版本 ────────────────────────────────────────────────────────


class SceneSummary(BaseModel):
    id: str
    sceneCode: str
    sceneName: str
    sceneRemark: str | None = None
    sceneType: str | None = None
    status: SceneStatus
    currentVersionNo: int | None = None
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


class SceneVersion(BaseModel):
    id: str
    sceneCode: str
    versionNo: int
    versionStatus: VersionStatus
    definition: SceneDefinition
    validationResult: dict[str, Any] | None = None
    createdBy: str | None = None
    createdAt: datetime
    publishedBy: str | None = None
    publishedAt: datetime | None = None


# ── 校验相关 ──────────────────────────────────────────────────────────


class ValidationIssue(BaseModel):
    field: str
    message: str
    level: Literal["ERROR", "WARNING"] = "ERROR"


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
