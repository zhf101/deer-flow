"""场景编排数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.gdp.datagen.config.common.models import (
    ErrorMapping,
    HttpMethod,
    HttpTimeoutConfig,
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

    expression: str = Field(default="", description="断言表达式。草稿阶段允许为空，发布前必须填写。")
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


class BaseStepDefinition(BaseModel):
    """场景编排步骤公共数据。

    保存所有步骤类型共同具备的身份、展示、依赖、启停、画布位置和输出映射信息。
    具体执行配置由 HTTP、SQL、断言、转换等子模型分别声明。
    """

    model_config = ConfigDict(extra="forbid")

    stepId: str = Field(..., min_length=1, max_length=128, description="步骤唯一 ID。")
    stepName: str | None = Field(default=None, max_length=256, description="步骤名称。")
    type: StepType = Field(..., description="步骤类型。")
    executionOrder: int | None = Field(default=None, ge=1, description="步骤执行顺序，从 1 开始。后端按该字段审计和确定同级依赖的执行优先级。")
    enabled: bool = Field(default=True, description="是否启用。")
    dependsOn: list[str] = Field(default_factory=list, description="前置依赖 stepId 列表。")
    description: str | None = Field(default=None, description="步骤说明。")
    position: Position | None = Field(default=None, description="画布坐标。")

    templateRef: StepTemplateRef | None = Field(default=None, description="模板来源快照信息。")
    outputMapping: dict[str, str] = Field(default_factory=dict, description="步骤输出映射。")
    outputMeta: dict[str, dict[str, str | None]] | None = Field(default=None, description="输出变量元数据。")


class HttpStepDefinition(BaseStepDefinition):
    """HTTP 请求步骤配置。

    描述场景运行时发起一次 HTTP GET/POST 请求所需的请求构造、超时、响应解析、
    错误映射和重试策略。草稿阶段允许系统编码和路径暂未填写。
    """

    type: Literal[StepType.HTTP] = Field(StepType.HTTP, description="固定为 HTTP，表示该步骤按 HTTP 请求执行。")
    sourceName: str | None = Field(default=None, max_length=256, description="步骤快照名称。")
    sysCode: str | None = Field(default=None, max_length=64, description="所属系统编码。草稿阶段可为空，发布、测试或执行前必须填写。")
    method: HttpMethod = Field(default=HttpMethod.POST, description="HTTP 方法。datagen 场景内仅允许 GET 或 POST。")
    path: str | None = Field(default=None, max_length=1024, description="HTTP 相对路径。草稿阶段可为空，发布、测试或执行前必须填写。")
    timeoutConfig: HttpTimeoutConfig = Field(default_factory=HttpTimeoutConfig, description="HTTP 请求分阶段超时配置。运行时分别控制连接、读取、写入和连接池等待超时。")
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


class SqlStepDefinition(BaseStepDefinition):
    """SQL 执行步骤配置。

    描述场景运行时执行一段 SQL 所需的系统、数据源、SQL 文本、参数映射、
    字段元数据和安全策略。草稿阶段允许运行必填项暂未填写。
    """

    type: Literal[StepType.SQL] = Field(StepType.SQL, description="固定为 SQL，表示该步骤按 SQL 执行。")
    sourceName: str | None = Field(default=None, max_length=256, description="步骤快照名称。")
    sysCode: str | None = Field(default=None, max_length=64, description="所属系统编码。草稿阶段可为空，发布、测试或执行前必须填写。")
    datasourceCode: str | None = Field(default=None, max_length=128, description="数据源编码。草稿阶段可为空，发布、测试或执行前必须填写。")
    operation: SqlOperation | None = Field(default=None, description="SQL 操作类型。草稿阶段可为空，发布、测试或执行前必须填写。")
    sqlText: str | None = Field(default=None, description="用户原始 SQL。草稿阶段可为空，发布、测试或执行前必须填写。")
    normalizedSql: str | None = Field(default=None, description="解析后的标准 SQL。")
    tables: list[dict[str, Any]] = Field(default_factory=list, description="SQL 表元数据。")
    resultFields: list[dict[str, Any]] = Field(default_factory=list, description="SQL 结果字段元数据。")
    conditionFields: list[dict[str, Any]] = Field(default_factory=list, description="SQL 条件字段元数据。")
    parameters: list[dict[str, Any]] = Field(default_factory=list, description="SQL 参数定义。")
    safety: SqlSourceSafety = Field(default_factory=SqlSourceSafety, description="SQL 安全策略。")
    paramMapping: dict[str, Any] = Field(default_factory=dict, description="SQL 参数映射。")


class AssertStepDefinition(BaseStepDefinition):
    """断言步骤配置。

    用于在编排流程中显式校验变量、上游步骤输出或表达式结果。
    """

    type: Literal[StepType.ASSERT] = Field(StepType.ASSERT, description="固定为 ASSERT，表示该步骤按断言逻辑执行。")
    assertions: list[AssertionDefinition] = Field(default_factory=list, description="步骤断言。")


class TransformStepDefinition(BaseStepDefinition):
    """变量转换步骤配置。

    用于在编排流程中生成或改写变量。
    """

    type: Literal[StepType.TRANSFORM] = Field(StepType.TRANSFORM, description="固定为 TRANSFORM，表示该步骤按变量转换逻辑执行。")
    assignments: dict[str, str] = Field(default_factory=dict, description="变量赋值。")


StepDefinition = Annotated[
    HttpStepDefinition | SqlStepDefinition | AssertStepDefinition | TransformStepDefinition,
    Field(discriminator="type"),
]
StepDefinitionAdapter = TypeAdapter(StepDefinition)


def parse_step_definition_payload(payload: dict[str, Any]) -> StepDefinition:
    """将步骤 payload 解析为具体步骤子模型。

    该函数只接收已经反序列化后的 Python 字典，例如 repository 从 ORM 行和
    JSON 字段组装出来的数据。FastAPI 接收前端 JSON 时会自动处理多态模型。
    """

    return StepDefinitionAdapter.validate_python(payload)


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
    stepOrder: int | None = Field(default=None, description="节点在场景编排步骤列表中的顺序，从 1 开始。")
    timelineOrder: int | None = Field(default=None, description="节点本次执行时间线顺序，从 1 开始。")
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

    runId: str | None = Field(default=None, description="本次场景执行记录 ID。执行结果持久化后由后端生成。")
    sceneCode: str
    versionNo: int
    envCode: str
    inputs: dict[str, Any] = Field(default_factory=dict, description="本次执行使用的场景入参。")
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]
    startedAt: datetime
    finishedAt: datetime
    durationMs: float
    stepResults: list[StepExecutionResult] = Field(default_factory=list)
    finalOutput: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class SceneRunSummary(BaseModel):
    """场景执行记录摘要（列表用），不含步骤明细。"""

    runId: str
    sceneCode: str
    versionNo: int
    envCode: str
    status: Literal["SUCCESS", "FAILED", "PARTIAL"]
    startedAt: datetime
    finishedAt: datetime
    durationMs: float
    inputs: dict[str, Any] = Field(default_factory=dict)
    finalOutput: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    stepCount: int = Field(default=0, description="步骤总数")
    successCount: int = Field(default=0, description="成功步骤数")
    failedCount: int = Field(default=0, description="失败步骤数")
