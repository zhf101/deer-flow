"""造数配置公共数据模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConfigStatus(StrEnum):
    """配置状态。"""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class HttpMethod(StrEnum):
    """HTTP 请求方法。"""

    GET = "GET"
    POST = "POST"


class InputFieldType(StrEnum):
    """输入、输出字段类型。"""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ENUM = "enum"
    OBJECT = "object"
    ARRAY = "array"


class SqlOperation(StrEnum):
    """SQL 操作类型。"""

    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class RetryErrorType(StrEnum):
    """触发 HTTP 重试的错误类型。"""

    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_RESET = "CONNECTION_RESET"
    HTTP_5XX = "HTTP_5XX"
    RATE_LIMIT = "RATE_LIMIT"


class InputFieldValidation(BaseModel):
    """字段校验规则。"""

    minLength: int | None = Field(default=None, description="字符串最小长度。")
    maxLength: int | None = Field(default=None, description="字符串最大长度。")
    pattern: str | None = Field(default=None, description="正则表达式校验规则。")
    minimum: float | None = Field(default=None, description="数值最小值。")
    maximum: float | None = Field(default=None, description="数值最大值。")


class InputFieldDefinition(BaseModel):
    """输入或输出字段结构定义。

    用于描述场景入参、HTTP 请求/响应字段、SQL 参数和结构化对象字段。
    """

    name: str = Field(..., min_length=1, max_length=128, description="字段编码或变量名。")
    label: str | None = Field(default=None, description="字段中文名或展示名称。")
    remark: str | None = Field(default=None, description="字段备注说明。")
    type: InputFieldType = Field(..., description="字段类型。")
    required: bool = Field(default=True, description="是否必填。")
    defaultValue: Any = Field(default=None, description="默认值。")
    optionsSource: str | None = Field(default=None, description="枚举选项来源或静态选项配置。")
    validation: InputFieldValidation | None = Field(default=None, description="字段校验规则。")
    batchEnabled: bool = Field(default=False, description="是否支持批量输入。")
    children: list["InputFieldDefinition"] | None = Field(default=None, description="对象或数组子字段定义。")


class ConditionRule(BaseModel):
    """响应业务条件规则。"""

    path: str = Field(..., description="待判断字段路径，例如 data.code。")
    op: str = Field(..., description="判断操作符，例如 eq、ne、exists、contains。")
    value: Any = Field(default=None, description="用于比较的目标值。")


class ResponseStatusCodeRule(BaseModel):
    """HTTP 状态码判定规则。"""

    success: list[int] = Field(default_factory=lambda: [200], description="认为请求成功的 HTTP 状态码列表。")


class ResponseConditionGroup(BaseModel):
    """响应业务条件组合。"""

    allOf: list[ConditionRule] = Field(default_factory=list, description="全部满足才成立的条件列表。")
    anyOf: list[ConditionRule] = Field(default_factory=list, description="任一满足即成立的条件列表。")


class ResponseHandling(BaseModel):
    """HTTP 响应处理规则。"""

    expectedContentType: str = Field(default="JSON", description="预期响应内容类型，例如 JSON、TEXT、XML。")
    statusCode: ResponseStatusCodeRule = Field(default_factory=ResponseStatusCodeRule, description="HTTP 状态码成功规则。")
    businessSuccess: ResponseConditionGroup = Field(default_factory=ResponseConditionGroup, description="业务成功条件。")
    businessFailure: ResponseConditionGroup = Field(default_factory=ResponseConditionGroup, description="业务失败条件。")


class ErrorMapping(BaseModel):
    """HTTP 错误信息映射规则。"""

    messageTemplate: str | None = Field(default=None, description="错误消息模板，可引用 fields 中提取的变量。")
    fields: dict[str, str] = Field(default_factory=dict, description="错误字段提取映射，key 为变量名，value 为响应路径。")
    fallbackMessage: str | None = Field(default=None, description="无法按模板生成错误时使用的兜底消息。")
    exposeRawResponse: bool = Field(default=False, description="是否在错误信息中暴露原始响应内容。")


class RetryPolicy(BaseModel):
    """HTTP 重试策略。"""

    enabled: bool = Field(default=False, description="是否启用重试。")
    maxAttempts: int = Field(default=1, ge=1, description="最大尝试次数，包含首次请求。")
    intervalMs: int = Field(default=1000, ge=0, description="两次尝试之间的间隔毫秒数。")
    retryOn: list[RetryErrorType] = Field(default_factory=list, description="触发重试的错误类型列表。")


class SqlSourceSafety(BaseModel):
    """SQL 执行安全策略。"""

    requireWhere: bool = Field(default=True, description="UPDATE/DELETE 是否必须包含 WHERE 条件。")
    maxAffectedRows: int | None = Field(default=None, description="允许影响的最大行数，None 表示不限制。")
