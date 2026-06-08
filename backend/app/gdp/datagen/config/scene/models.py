"""场景编排数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.gdp.datagen.config.common.models import (
    ErrorMapping,
    HttpMethod,
    InputFieldDefinition,
    ResponseHandling,
    RetryPolicy,
    SceneStatus,
    SqlOperation,
    SqlSourceSafety,
    StepType,
    VersionStatus,
)


class Position(BaseModel):
    """编排画布中的节点坐标。"""

    x: float = Field(..., description="横向坐标。")
    y: float = Field(..., description="纵向坐标。")


class BatchConfig(BaseModel):
    """场景批量执行配置。"""

    enabled: bool = Field(default=False, description="是否启用批量执行。")
    failurePolicy: Literal["STOP_ON_ERROR", "CONTINUE_ON_ERROR"] = Field(
        default="STOP_ON_ERROR",
        description="批量执行失败策略。",
    )
    maxConcurrency: int = Field(default=1, ge=1, description="最大并发数。")


class AssertionDefinition(BaseModel):
    """步骤级断言。"""

    expression: str = Field(..., min_length=1, description="断言表达式。")
    message: str | None = Field(default=None, description="断言失败提示。")


class StepTemplateRef(BaseModel):
    """步骤快照来源信息。

    场景内直接配置 HTTP/SQL 时该字段为空。模板导入时该字段只用于展示、
    对比和重新导入，不作为运行期读取基础模板的依据。
    """

    type: Literal["HTTP_SOURCE", "SQL_SOURCE"]
    sourceCode: str = Field(..., min_length=1, max_length=128, description="来源模板编码。")
    sourceNameAtSnapshot: str | None = Field(default=None, description="导入时模板名称。")
    sourceUpdatedAtSnapshot: datetime | None = Field(default=None, description="导入时模板更新时间。")
    sourceHashSnapshot: str | None = Field(default=None, description="导入时模板内容 hash。")
    configHash: str | None = Field(default=None, description="当前步骤快照内容 hash。")
    snapshotAt: datetime | None = Field(default=None, description="快照生成时间。")
    drifted: bool = Field(default=False, description="当前快照是否已偏离导入时模板。")


class StepDefinition(BaseModel):
    """场景步骤数据传输对象。

    DTO 面向前端编辑保持扁平结构；repository 层会拆到
    ``df_scene_step``、``df_scene_step_http_config``、
    ``df_scene_step_sql_config`` 三类物理表。
    """

    stepId: str = Field(..., min_length=1, max_length=128, description="步骤唯一 ID。")
    stepName: str | None = Field(default=None, max_length=256, description="步骤名称。")
    type: StepType = Field(..., description="步骤类型。")
    enabled: bool = Field(default=True, description="是否启用。")
    dependsOn: list[str] = Field(default_factory=list, description="前置依赖 stepId 列表。")
    description: str | None = Field(default=None, description="步骤说明。")
    position: Position | None = Field(default=None, description="画布坐标。")

    # 来源信息。自定义节点为空。
    templateRef: StepTemplateRef | None = Field(default=None, description="模板来源快照信息。")
    httpSourceCode: str | None = Field(default=None, max_length=128, description="来源 HTTP 模板编码，软引用。")
    sqlSourceCode: str | None = Field(default=None, max_length=128, description="来源 SQL 模板编码，软引用。")

    # HTTP 快照字段。
    sourceName: str | None = Field(default=None, max_length=256, description="步骤快照名称。")
    sysCode: str | None = Field(default=None, max_length=64, description="所属系统编码。")
    method: HttpMethod | None = Field(default=None, description="HTTP 方法。")
    path: str | None = Field(default=None, max_length=1024, description="HTTP 相对路径。")
    url: str | None = Field(
        default=None,
        max_length=1024,
        description="path 的别名，仅兼容旧前端入参；响应中与 path 同值，新增代码应使用 path。",
    )
    requestMapping: dict[str, Any] = Field(default_factory=dict, description="HTTP 请求构造配置。")
    httpParamMapping: dict[str, Any] = Field(default_factory=dict, description="HTTP 参数映射。")
    bodySchema: list[InputFieldDefinition] | None = Field(default=None, description="HTTP 请求体结构。")
    responseSchema: list[InputFieldDefinition] | None = Field(default=None, description="响应 body 结构。")
    responseHeadersSchema: list[InputFieldDefinition] | None = Field(default=None, description="响应 header 结构。")
    responseCookiesSchema: list[InputFieldDefinition] | None = Field(default=None, description="响应 cookie 结构。")
    responseHandling: ResponseHandling | None = Field(default=None, description="响应处理规则。")
    errorMapping: ErrorMapping | None = Field(default=None, description="网络/传输异常错误映射。")
    businessErrorMapping: ErrorMapping | None = Field(default=None, description="业务失败错误映射。")
    retryPolicy: RetryPolicy | None = Field(default=None, description="HTTP 重试策略。")

    # SQL 快照字段。
    datasourceCode: str | None = Field(default=None, max_length=128, description="数据源编码。")
    operation: SqlOperation | None = Field(default=None, description="SQL 操作类型。")
    sqlText: str | None = Field(default=None, description="用户原始 SQL。")
    normalizedSql: str | None = Field(default=None, description="解析后的标准 SQL。")
    tables: list[dict[str, Any]] = Field(default_factory=list, description="SQL 表元数据。")
    resultFields: list[dict[str, Any]] = Field(default_factory=list, description="SQL 结果字段元数据。")
    conditionFields: list[dict[str, Any]] = Field(default_factory=list, description="SQL 条件字段元数据。")
    parameters: list[dict[str, Any]] = Field(default_factory=list, description="SQL 参数定义。")
    safety: SqlSourceSafety = Field(default_factory=SqlSourceSafety, description="SQL 安全策略。")
    paramMapping: dict[str, Any] = Field(default_factory=dict, description="SQL 参数映射。")
    sqlParamMapping: dict[str, Any] = Field(default_factory=dict, description="兼容字段，保存时并入 paramMapping。")

    # 公共输出和扩展步骤字段。
    outputMapping: dict[str, str] = Field(default_factory=dict, description="步骤输出映射。")
    outputMeta: dict[str, dict[str, str | None]] | None = Field(default=None, description="输出变量元数据。")
    assertions: list[AssertionDefinition] = Field(default_factory=list, description="步骤断言。")
    assignments: dict[str, str] = Field(default_factory=dict, description="变量赋值。")


class SceneDefinition(BaseModel):
    """场景定义数据传输对象。"""

    sceneCode: str = Field(..., min_length=1, max_length=128, description="场景唯一编码。")
    sceneName: str = Field(..., min_length=1, max_length=256, description="场景名称。")
    sceneRemark: str | None = Field(default=None, description="场景备注。")
    sceneType: str | None = Field(default=None, max_length=128, description="场景分类。")
    environmentField: Literal["env"] = Field(default="env", description="环境字段名。")
    inputSchema: list[InputFieldDefinition] = Field(default_factory=list, description="场景入参定义。")
    steps: list[StepDefinition] = Field(default_factory=list, description="场景步骤。")
    resultSchema: list[InputFieldDefinition] | None = Field(default=None, description="场景最终输出结构。")
    resultMapping: dict[str, str] = Field(default_factory=dict, description="场景最终输出映射。")
    errorPolicy: Literal["STOP_ON_ERROR", "CONTINUE_ON_ERROR"] = Field(default="STOP_ON_ERROR", description="错误策略。")
    batchConfig: BatchConfig = Field(default_factory=BatchConfig, description="批量执行配置。")
    status: SceneStatus = Field(default=SceneStatus.DRAFT, description="场景状态。")


class SceneSummary(BaseModel):
    """场景列表摘要。"""

    id: str
    sceneCode: str
    sceneName: str
    sceneRemark: str | None = None
    sceneType: str | None = None
    status: SceneStatus
    currentVersionNo: int | None = None
    publishedVersionNo: int | None = None
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


class SceneVersion(BaseModel):
    """场景版本响应。"""

    id: str
    sceneCode: str
    versionNo: int
    versionStatus: VersionStatus
    definition: SceneDefinition
    validationResult: dict[str, Any] | None = None
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime
    publishedBy: str | None = None
    publishedAt: datetime | None = None


class ValidationIssue(BaseModel):
    """场景校验问题。"""

    field: str
    message: str
    level: Literal["ERROR", "WARNING"] = "ERROR"


class ValidationResult(BaseModel):
    """场景校验结果。"""

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class DisableResponse(BaseModel):
    """删除、禁用类操作响应。"""

    success: bool = True


class SceneRunRequest(BaseModel):
    """场景执行请求。"""

    sceneCode: str = Field(..., min_length=1, max_length=128, description="待执行的场景编码。")
    envCode: str = Field(..., min_length=1, max_length=64, description="执行环境编码。")
    inputs: dict[str, Any] = Field(default_factory=dict, description="场景入参。")


class StepExecutionResult(BaseModel):
    """单个场景步骤执行结果。"""

    stepId: str
    stepName: str | None = None
    type: StepType
    status: Literal["SUCCESS", "FAILED", "SKIPPED"]
    startedAt: datetime
    finishedAt: datetime
    durationMs: float
    outputs: dict[str, Any] = Field(default_factory=dict)
    rawResponse: Any = None
    error: str | None = None
    statusCode: int | None = None


class SceneExecutionResult(BaseModel):
    """场景执行结果。"""

    sceneCode: str
    versionNo: int
    envCode: str
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]
    startedAt: datetime
    finishedAt: datetime
    durationMs: float
    stepResults: list[StepExecutionResult] = Field(default_factory=list)
    finalOutput: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
