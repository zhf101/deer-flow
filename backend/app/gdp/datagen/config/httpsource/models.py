"""HTTP 接口配置 Pydantic 数据模型。

HTTP 接口配置是可复用的接口定义，不绑定具体环境。运行时根据
``envCode + sysCode`` 从基础配置的服务端点表解析 Base URL，再拼接本模型
里的 ``path`` 发起请求。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.gdp.datagen.config.common.models import (
    CapabilitySideEffect,
    CapabilityType,
    ConfigStatus,
    ErrorMapping,
    HttpMethod,
    HttpTimeoutConfig,
    InputFieldDefinition,
    ResponseHandling,
    RetryPolicy,
)


class HttpSourceConfig(BaseModel):
    """可复用 HTTP 接口定义。

    一条配置描述一个业务接口的请求方式、路径、入参映射、响应解析和输出变量。
    它通过 ``sysCode`` 归属到某个系统，但不直接保存环境 Base URL。
    """

    sourceCode: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="HTTP 接口配置唯一编码。编排 HTTP 步骤通过该编码引用接口配置。",
    )
    sourceName: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="接口名称或用途说明，用于列表展示和人工识别。",
    )
    tags: list[str] = Field(default_factory=list, description="HTTP 接口业务标签，用于 Agent 检索和能力聚类。")
    capabilityType: CapabilityType = Field(default=CapabilityType.QUERY, description="HTTP 接口提供的业务能力类型。")
    businessDomain: str | None = Field(default=None, max_length=128, description="HTTP 接口所属业务域，例如交易、支付、库存。")
    sideEffects: list[CapabilitySideEffect] = Field(default_factory=list, description="HTTP 接口调用会造成的业务副作用，用于写操作确认和审计。")
    agentDescription: str | None = Field(default=None, description="面向 Agent 的接口能力说明，描述接口用途、适用范围和关键产出。")
    sysCode: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="所属系统编码，关联基础配置 SysConfig.sysCode。运行时结合 envCode 解析服务端点 Base URL。",
    )
    path: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="接口路径。通常保存 Base URL 之后的相对路径，例如 /api/order/create。",
    )
    method: HttpMethod = Field(
        default=HttpMethod.GET,
        description="HTTP 请求方法，目前前端支持 GET、POST。",
    )
    timeoutConfig: HttpTimeoutConfig = Field(default_factory=HttpTimeoutConfig, description="HTTP 请求分阶段超时配置。运行时分别控制连接、读取、写入和连接池等待超时。")
    requestMapping: dict[str, Any] = Field(
        default_factory=dict,
        description="请求入参映射配置。保存 query、headers、authConfig、bodyType、rawBody、bodyTree、formData、urlEncodedData 等请求构造信息。",
    )
    bodySchema: list[InputFieldDefinition] | None = Field(
        default=None,
        description="请求 Body 字段结构定义，主要用于复杂 JSON/XML Body 的可视化编辑和变量映射。",
    )
    responseSchema: list[InputFieldDefinition] | None = Field(
        default=None,
        description="响应 Body 字段结构定义，用于响应字段展示、结果提取和变量映射。",
    )
    responseHeadersSchema: list[InputFieldDefinition] | None = Field(
        default=None,
        description="响应 Header 字段结构定义，用于从响应头提取 token、traceId 等变量。",
    )
    responseCookiesSchema: list[InputFieldDefinition] | None = Field(
        default=None,
        description="响应 Cookie 字段结构定义，用于从 Set-Cookie 等位置提取会话变量。",
    )
    responseHandling: ResponseHandling | None = Field(
        default=None,
        description="响应判定规则。包含成功状态码、业务成功条件、业务失败条件等。",
    )
    errorMapping: ErrorMapping | None = Field(
        default=None,
        description="传输异常错误信息映射规则。用于把网络超时、连接失败等无响应异常转换成人类可读错误描述。",
    )
    businessErrorMapping: ErrorMapping | None = Field(
        default=None,
        description="业务异常错误信息映射规则。用于把已收到响应但业务判定失败的结果转换成人类可读错误描述。",
    )
    outputMapping: dict[str, str] = Field(
        default_factory=dict,
        description="输出变量映射。key 为输出变量名，value 为响应字段路径或提取表达式。",
    )
    outputMeta: dict[str, dict[str, str | None]] | None = Field(
        default=None,
        description="输出变量的展示元信息，例如中文名、备注等，不参与运行时取值。",
    )
    retryPolicy: RetryPolicy | None = Field(
        default=None,
        description="重试策略。定义是否重试、最大尝试次数、间隔时间和触发重试的错误类型。",
    )
    status: ConfigStatus = Field(
        default=ConfigStatus.ENABLED,
        description="配置状态。只有启用状态的接口配置可用于发布和运行。",
    )


class HttpSourceResponse(HttpSourceConfig):
    """HTTP 接口配置查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdBy: str | None = Field(default=None, description="创建人标识。")
    updatedBy: str | None = Field(default=None, description="最近更新人标识。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class DisableResponse(BaseModel):
    """停用或删除操作响应。"""

    success: bool = Field(default=True, description="操作是否成功。")


class ParsedCookie(BaseModel):
    """从 Set-Cookie 响应头解析出的单个 Cookie。"""

    name: str = Field(..., description="Cookie 名称。")
    value: str = Field(..., description="Cookie 值。")
    domain: str | None = Field(default=None, description="Cookie 所属域名。")
    path: str | None = Field(default="/", description="Cookie 路径。")
    expires: str | None = Field(default=None, description="过期时间字符串。")
    httpOnly: bool = Field(default=False, description="是否仅 HTTP 可访问。")
    secure: bool = Field(default=False, description="是否仅 HTTPS 传输。")
    sameSite: str | None = Field(default=None, description="SameSite 策略：Strict / Lax / None。")
    raw: str = Field(default="", description="原始 Set-Cookie 头内容。")


class BusinessResult(BaseModel):
    """业务条件求值结果。"""

    isSuccess: bool = Field(..., description="业务逻辑是否判定为成功。")
    reason: str = Field(default="", description="判定原因说明。")
    matchedRules: list[str] = Field(default_factory=list, description="命中的规则描述列表。")


class RetryInfo(BaseModel):
    """重试执行信息。"""

    attempts: int = Field(default=1, description="实际执行次数，包含首次请求。")
    lastError: str | None = Field(default=None, description="最后一次失败的错误信息。")


class HttpSourceTestRequest(BaseModel):
    """HTTP 接口配置测试请求。

    前端可提交当前编辑中的配置，不要求配置已经保存。后端会根据 ``envCode``
    和配置里的 ``sysCode`` 解析服务端点，并真实发起一次 HTTP 请求。
    """

    model_config = ConfigDict(extra="forbid")

    envCode: str = Field(..., min_length=1, max_length=64, description="用于测试的环境编码。")
    config: HttpSourceConfig = Field(..., description="待测试的 HTTP 接口配置。")


class HttpSourceTestRequestInfo(BaseModel):
    """HTTP 接口测试时实际发出的请求信息。"""

    url: str = Field(..., description="最终请求 URL，包含 Base URL、接口路径和 query 参数。")
    method: str = Field(..., description="请求方法。")
    headers: dict[str, str] = Field(default_factory=dict, description="实际请求头。")
    query: dict[str, Any] = Field(default_factory=dict, description="实际 Query 参数。")
    body: Any = Field(default=None, description="实际请求报文。")
    bodyType: str = Field(default="none", description="请求 Body 类型。")


class HttpSourceTestResponseInfo(BaseModel):
    """HTTP 接口测试响应信息。"""

    statusCode: int | None = Field(default=None, description="HTTP 响应状态码。异常时为空。")
    headers: dict[str, str] = Field(default_factory=dict, description="响应头。")
    body: Any = Field(default=None, description="响应报文。")
    cookies: list[ParsedCookie] = Field(default_factory=list, description="从响应解析出的 Cookie 列表。")
    elapsedMs: float | None = Field(default=None, description="请求耗时，单位毫秒。")


class HttpSourceTestErrorInfo(BaseModel):
    """HTTP 接口测试异常信息。"""

    type: str = Field(..., description="异常类型。")
    message: str = Field(..., description="异常消息。")
    detail: str | None = Field(default=None, description="异常详情。")


class HttpSourceTestResponse(BaseModel):
    """HTTP 接口配置测试结果。"""

    success: bool = Field(..., description="请求是否成功发出并收到响应。")
    request: HttpSourceTestRequestInfo = Field(..., description="实际请求信息。")
    response: HttpSourceTestResponseInfo | None = Field(default=None, description="响应信息。")
    businessResult: BusinessResult | None = Field(default=None, description="业务条件求值结果。")
    extractedOutputs: dict[str, Any] = Field(default_factory=dict, description="按 outputMapping 提取的输出变量。")
    retryInfo: RetryInfo | None = Field(default=None, description="重试执行信息。")
    error: HttpSourceTestErrorInfo | None = Field(default=None, description="异常信息。")
