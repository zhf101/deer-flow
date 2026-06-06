"""HTTP 接口配置 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.gdp.models import (
    ConfigStatus,
    ErrorMapping,
    HttpMethod,
    InputFieldDefinition,
    ResponseHandling,
    RetryPolicy,
)


class HttpSourceConfig(BaseModel):
    """可复用的 HTTP 接口配置，引用 baseconfig 的服务端点。"""

    sourceCode: str = Field(..., min_length=1, max_length=128)
    sourceName: str = Field(..., min_length=1, max_length=256)
    serviceCode: str = Field(..., min_length=1, max_length=128)
    path: str = Field(..., min_length=1, max_length=1024)
    method: HttpMethod = HttpMethod.GET
    requestMapping: dict[str, Any] = Field(default_factory=dict)
    bodySchema: list[InputFieldDefinition] | None = None
    responseHandling: ResponseHandling | None = None
    errorMapping: ErrorMapping | None = None
    outputMapping: dict[str, str] = Field(default_factory=dict)
    outputMeta: dict[str, dict[str, str | None]] | None = None
    retryPolicy: RetryPolicy | None = None
    status: ConfigStatus = ConfigStatus.ENABLED


class HttpSourceResponse(HttpSourceConfig):
    id: str
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


class DisableResponse(BaseModel):
    success: bool = True
