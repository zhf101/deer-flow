"""GDP 造数工厂 Pydantic 数据模型。

定义场景编排、步骤配置、输入参数、响应处理等所有 API 层数据结构。
所有模型均用于配置管理（设计时），不用于运行时执行状态。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── 枚举类型 ──────────────────────────────────────────────────────────


# 场景状态：草稿 → 已发布 → 已停用
class SceneStatus(StrEnum):
    DRAFT = "DRAFT"          # 草稿，可编辑
    PUBLISHED = "PUBLISHED"  # 已发布，可执行
    DISABLED = "DISABLED"    # 已停用，不可执行


# 版本状态：草稿版本 / 已发布版本
class VersionStatus(StrEnum):
    DRAFT = "DRAFT"          # 草稿版本，仍可修改
    PUBLISHED = "PUBLISHED"  # 已发布版本，不可变快照


# 配置项启用状态（环境、服务端点、数据源、SQL 模板通用）
class ConfigStatus(StrEnum):
    ENABLED = "ENABLED"      # 启用
    DISABLED = "DISABLED"    # 停用


# 步骤类型——决定执行引擎走哪条分支
class StepType(StrEnum):
    HTTP = "HTTP"            # HTTP 请求
    SQL = "SQL"              # SQL 数据库操作
    ASSERT = "ASSERT"        # 断言校验（不产生外部调用）
    TRANSFORM = "TRANSFORM"  # 变量转换（不产生外部调用）


# 输入字段类型——用于前端动态渲染表单控件
class InputFieldType(StrEnum):
    STRING = "string"        # 文本输入框
    NUMBER = "number"        # 数字输入框
    BOOLEAN = "boolean"      # 开关/复选框
    DATE = "date"            # 日期选择器
    ENUM = "enum"            # 下拉选择（选项来自 optionsSource）
    OBJECT = "object"        # 嵌套对象（有 children 子字段）
    ARRAY = "array"          # 数组类型


# HTTP 请求方法（仅支持 GET 和 POST）
class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"


# SQL 操作类型——影响执行引擎的返回值结构
class SqlOperation(StrEnum):
    SELECT = "SELECT"        # 查询，返回 rows
    INSERT = "INSERT"        # 插入，返回 affectedRows
    UPDATE = "UPDATE"        # 更新，返回 affectedRows
    DELETE = "DELETE"        # 删除，返回 affectedRows


# 条件判断操作符——用于业务成功/失败规则和断言
class ConditionOperator(StrEnum):
    EQ = "EQ"                # 等于
    NE = "NE"                # 不等于
    GT = "GT"                # 大于
    GTE = "GTE"              # 大于等于
    LT = "LT"                # 小于
    LTE = "LTE"              # 小于等于
    IN = "IN"                # 在列表中
    NOT_IN = "NOT_IN"        # 不在列表中
    EXISTS = "EXISTS"        # 字段存在
    NOT_EXISTS = "NOT_EXISTS"  # 字段不存在
    EMPTY = "EMPTY"          # 空值（null / "" / [] / {}）
    NOT_EMPTY = "NOT_EMPTY"  # 非空
    CONTAINS = "CONTAINS"    # 包含子串/元素
    REGEX = "REGEX"          # 正则匹配


# 可重试的错误类型——决定 HTTP 步骤在什么错误下触发重试
class RetryErrorType(StrEnum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"    # 网络超时
    CONNECTION_RESET = "CONNECTION_RESET"  # 连接被重置
    HTTP_5XX = "HTTP_5XX"                  # 服务端错误（5xx）
    RATE_LIMIT = "RATE_LIMIT"              # 限流（429）


# ── 子结构模型 ────────────────────────────────────────────────────────


# 输入字段校验规则（正则、长度、范围等）
class InputFieldValidation(BaseModel):
    minLength: int | None = None       # 最小长度（string 类型）
    maxLength: int | None = None       # 最大长度（string 类型）
    pattern: str | None = None         # 正则校验（string 类型）
    minimum: float | None = None       # 最小值（number 类型）
    maximum: float | None = None       # 最大值（number 类型）


# 输入字段定义——描述场景的一个输入参数（支持嵌套 object/array）
class InputFieldDefinition(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)  # 字段标识（变量引用名）
    label: str | None = None          # 中文显示标签
    remark: str | None = None         # 备注说明
    type: InputFieldType              # 字段类型
    required: bool = False            # 是否必填
    defaultValue: Any = None          # 默认值
    optionsSource: str | None = None  # 枚举选项来源（如字典编码）
    validation: InputFieldValidation | None = None  # 校验规则
    batchEnabled: bool = False        # 是否参与批量执行（批量时此字段按行变化）
    children: list[InputFieldDefinition] | None = None  # 子字段（object/array 类型时有值）


# 画布节点坐标（仅服务前端可视化，不影响执行）
class Position(BaseModel):
    x: float = 0
    y: float = 0


# 单条条件规则——由 JSONPath 路径 + 操作符 + 期望值组成
class ConditionRule(BaseModel):
    path: str = Field(..., min_length=1)  # JSONPath 路径，如 "$.body.code"
    op: ConditionOperator                 # 比较操作符
    value: Any = None                     # 期望值


# HTTP 状态码成功判定规则
class StatusCodeRule(BaseModel):
    success: list[int] = Field(default_factory=lambda: [200])  # 视为成功的状态码列表


# 业务成功规则——allOf 中所有条件必须满足
class BusinessSuccessRule(BaseModel):
    allOf: list[ConditionRule] = Field(default_factory=list)


# 业务失败规则——anyOf 中任一条件满足即判定为业务失败
class BusinessFailureRule(BaseModel):
    anyOf: list[ConditionRule] = Field(default_factory=list)


# HTTP 响应处理策略——综合状态码和业务规则判定请求是否成功
class ResponseHandling(BaseModel):
    expectedContentType: Literal["JSON", "TEXT", "XML", "ANY"] = "JSON"  # 期望的响应内容类型
    statusCode: StatusCodeRule = Field(default_factory=StatusCodeRule)     # 状态码规则
    businessSuccess: BusinessSuccessRule = Field(default_factory=BusinessSuccessRule)  # 业务成功规则
    businessFailure: BusinessFailureRule = Field(default_factory=BusinessFailureRule)  # 业务失败规则


# 错误信息映射——将原始响应中的错误字段映射为人类友好的错误提示
class ErrorMapping(BaseModel):
    messageTemplate: str | None = None  # 错误消息模板，如 "创建失败：${error.bizCode}"
    fields: dict[str, str] = Field(default_factory=dict)  # 从响应中提取的错误字段（key→JSONPath）
    fallbackMessage: str | None = None  # 兜底错误消息（模板解析失败时使用）
    exposeRawResponse: bool = False     # 是否暴露原始响应体给调用方


# 重试策略——控制 HTTP 步骤失败时的重试行为
class RetryPolicy(BaseModel):
    enabled: bool = False               # 是否启用重试
    maxAttempts: int = Field(default=1, ge=1, le=10)  # 最大尝试次数（含首次）
    intervalMs: int = Field(default=1000, ge=0, le=60000)  # 重试间隔（毫秒）
    retryOn: list[RetryErrorType] = Field(default_factory=list)  # 触发重试的错误类型


# 断言定义——用于 ASSERT 步骤和 SQL 步骤的后置校验
class AssertionDefinition(BaseModel):
    expression: str = Field(..., min_length=1)  # 断言表达式，如 "${steps.createOrder.outputs.orderNo} NOT_EMPTY"
    message: str | None = None                  # 断言失败时的提示信息


# ── 核心模型 ──────────────────────────────────────────────────────────


# 步骤定义——所有步骤类型共用的扁平结构
# HTTP 使用 method/url/requestMapping/responseHandling 等字段
# SQL 使用 datasource/sqlTemplateCode/paramMapping 等字段
# ASSERT 使用 assertions 字段
# TRANSFORM 使用 assignments 字段
# 未使用的字段为 None 或空集合
class StepDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    # ── 公共字段 ──
    stepId: str = Field(..., min_length=1, max_length=128)  # 步骤唯一标识（场景内唯一）
    stepName: str | None = None       # 步骤中文名称
    type: StepType                    # 步骤类型
    enabled: bool = True              # 是否启用（禁用则执行时跳过）
    dependsOn: list[str] = Field(default_factory=list)  # 依赖的前置步骤 ID（仅用于校验和可视化）
    description: str | None = None    # 步骤描述
    position: Position | None = None  # 画布坐标（仅前端使用）

    # ── HTTP 专属字段 ──
    method: HttpMethod | None = None  # HTTP 方法
    url: str | None = None            # 请求 URL（支持 ${env.services.xxx.baseUrl} 变量）
    requestMapping: dict[str, Any] = Field(default_factory=dict)  # 请求映射（headers/query/body）
    bodySchema: list[InputFieldDefinition] | None = None  # 请求体字段 Schema（前端渲染用）
    bodyMapping: dict[str, Any] | None = None             # 请求体映射（兼容字段）
    responseSchema: list[InputFieldDefinition] | None = None  # 响应体字段 Schema（前端渲染用）
    responseHandling: ResponseHandling | None = None  # 响应处理策略
    errorMapping: ErrorMapping | None = None            # 错误信息映射
    outputMapping: dict[str, str] = Field(default_factory=dict)  # 输出提取（key→JSONPath）
    outputMeta: dict[str, dict[str, str | None]] | None = None   # 输出字段元信息（label/remark）
    retryPolicy: RetryPolicy | None = None   # 重试策略

    # ── SQL 专属字段 ──
    datasource: str | None = None           # 数据源引用（如 "${env.datasources.tradeDb}"）
    sqlTemplateCode: str | None = None      # SQL 模板编码
    operation: SqlOperation | None = None   # SQL 操作类型
    paramMapping: dict[str, Any] = Field(default_factory=dict)  # SQL 参数映射（参数名→变量引用）
    assertions: list[AssertionDefinition] = Field(default_factory=list)  # 后置断言

    # ── TRANSFORM 专属字段 ──
    assignments: dict[str, str] = Field(default_factory=dict)  # 变量赋值（目标变量→表达式）


# 批量执行配置
class BatchConfig(BaseModel):
    enabled: bool = False                                # 是否启用批量
    failurePolicy: Literal["STOP_ON_ERROR", "CONTINUE_ON_ERROR"] = "STOP_ON_ERROR"  # 失败策略
    maxConcurrency: int = Field(default=1, ge=1, le=20)  # 最大并发数


# 场景定义——顶层配置，包含输入参数、步骤列表、结果映射
# 这是 GDP 系统的核心数据模型，前端编排和后端执行都基于此结构
class SceneDefinition(BaseModel):
    sceneCode: str = Field(..., min_length=1, max_length=128)   # 场景编码（全局唯一）
    sceneName: str = Field(..., min_length=1, max_length=256)   # 场景名称
    sceneRemark: str | None = None          # 场景备注
    sceneType: str | None = None            # 场景分类（如 "credit_card"）
    environmentField: str = "env"           # 环境字段名（V1 固定为 "env"）
    inputSchema: list[InputFieldDefinition] = Field(default_factory=list)  # 输入参数定义
    steps: list[StepDefinition] = Field(default_factory=list)  # 步骤列表（按数组顺序执行）
    resultMapping: dict[str, Any] = Field(default_factory=dict)  # 最终输出映射（key→变量引用）
    batchConfig: BatchConfig = Field(default_factory=BatchConfig)  # 批量配置
    status: SceneStatus = SceneStatus.DRAFT  # 当前状态

    @field_validator("environmentField")
    @classmethod
    def environment_field_must_be_env(cls, value: str) -> str:
        if value != "env":
            raise ValueError("environmentField V1 fixed to env")
        return value


# 场景摘要——列表查询时返回的轻量信息（不含完整配置）
class SceneSummary(BaseModel):
    id: str
    sceneCode: str
    sceneName: str
    sceneRemark: str | None = None
    sceneType: str | None = None
    status: SceneStatus
    currentVersionNo: int | None = None  # 当前发布版本号
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


# 场景版本——包含完整定义快照的版本记录
class SceneVersion(BaseModel):
    id: str
    sceneCode: str
    versionNo: int                      # 版本号（从 1 递增）
    versionStatus: VersionStatus        # 版本状态
    definition: SceneDefinition         # 该版本的完整场景定义
    validationResult: dict[str, Any] | None = None  # 发布时的校验结果
    createdBy: str | None = None
    createdAt: datetime
    publishedBy: str | None = None      # 发布操作人
    publishedAt: datetime | None = None # 发布时间


# ── 校验相关 ──────────────────────────────────────────────────────────


# 单条校验问题
class ValidationIssue(BaseModel):
    field: str     # 问题字段路径
    message: str   # 问题描述
    level: Literal["ERROR", "WARNING"] = "ERROR"  # 严重程度


# 校验结果
class ValidationResult(BaseModel):
    valid: bool                                     # 是否通过校验
    issues: list[ValidationIssue] = Field(default_factory=list)  # 问题列表


# ── 基础配置模型 ──────────────────────────────────────────────────────


# 环境配置（如测试环境、生产环境）
class EnvironmentConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)   # 环境编码
    envName: str = Field(..., min_length=1, max_length=256)  # 环境名称
    status: ConfigStatus = ConfigStatus.ENABLED
    remark: str | None = None


# 环境配置（含 ID 和时间戳的完整响应）
class EnvironmentResponse(EnvironmentConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


# 服务端点配置——指定某个环境下的服务基础 URL
class ServiceEndpointConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)       # 所属环境编码
    serviceCode: str = Field(..., min_length=1, max_length=128)  # 服务编码（如 "auth"、"order"）
    serviceName: str = Field(..., min_length=1, max_length=256)  # 服务名称
    baseUrl: str = Field(..., min_length=1, max_length=1024)     # 基础 URL
    status: ConfigStatus = ConfigStatus.ENABLED


# 服务端点（含 ID 和时间戳的完整响应）
class ServiceEndpointResponse(ServiceEndpointConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


# 数据源配置——指定某个环境下的数据库连接信息
class DatasourceConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)            # 所属环境编码
    datasourceCode: str = Field(..., min_length=1, max_length=128)    # 数据源编码
    datasourceName: str = Field(..., min_length=1, max_length=256)    # 数据源名称
    dbType: str = Field(..., min_length=1, max_length=64)             # 数据库类型（MYSQL/POSTGRESQL）
    host: str = Field(..., min_length=1, max_length=256)              # 主机地址
    port: int = Field(..., ge=1, le=65535)                            # 端口号
    databaseName: str = Field(..., min_length=1, max_length=256)      # 数据库名
    username: str | None = None     # 用户名
    password: str | None = None     # 密码
    status: ConfigStatus = ConfigStatus.ENABLED


# 数据源（含 ID 和时间戳的完整响应）
class DatasourceResponse(DatasourceConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


# SQL 模板参数定义
class SqlTemplateParameter(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)  # 参数名
    type: InputFieldType | str                             # 参数类型
    required: bool = True                                  # 是否必填
    defaultValue: Any = None                               # 默认值


# SQL 模板安全约束
class SqlTemplateSafety(BaseModel):
    requireWhere: bool = True                    # 是否要求 WHERE 子句（防止全表操作）
    maxAffectedRows: int | None = Field(default=None, ge=1)  # 最大影响行数


# SQL 模板配置——预定义的参数化 SQL 语句
class SqlTemplateConfig(BaseModel):
    templateCode: str = Field(..., min_length=1, max_length=128)  # 模板编码
    templateName: str = Field(..., min_length=1, max_length=256)  # 模板名称
    operation: SqlOperation                     # SQL 操作类型
    datasourceType: str = Field(..., min_length=1, max_length=64)  # 目标数据库类型
    sqlText: str = Field(..., min_length=1)     # SQL 文本（支持 :paramName 命名参数）
    parameters: list[SqlTemplateParameter] = Field(default_factory=list)  # 参数定义
    safety: SqlTemplateSafety = Field(default_factory=SqlTemplateSafety)  # 安全约束
    status: ConfigStatus = ConfigStatus.ENABLED


# SQL 模板（含 ID 和时间戳的完整响应）
class SqlTemplateResponse(SqlTemplateConfig):
    id: str
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


# 通用操作结果（停用/删除等操作）
class DisableResponse(BaseModel):
    success: bool = True
