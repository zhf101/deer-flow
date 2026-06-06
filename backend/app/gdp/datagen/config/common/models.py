"""Shared datagen configuration models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConfigStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"


class InputFieldType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ENUM = "enum"
    OBJECT = "object"
    ARRAY = "array"


class SqlOperation(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class RetryErrorType(StrEnum):
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_RESET = "CONNECTION_RESET"
    HTTP_5XX = "HTTP_5XX"
    RATE_LIMIT = "RATE_LIMIT"


class InputFieldValidation(BaseModel):
    minLength: int | None = None
    maxLength: int | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None


class InputFieldDefinition(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    label: str | None = None
    remark: str | None = None
    type: InputFieldType
    required: bool = True
    defaultValue: Any = None
    optionsSource: str | None = None
    validation: InputFieldValidation | None = None
    batchEnabled: bool = False
    children: list["InputFieldDefinition"] | None = None


class ConditionRule(BaseModel):
    path: str
    op: str
    value: Any = None


class ResponseStatusCodeRule(BaseModel):
    success: list[int] = Field(default_factory=lambda: [200])


class ResponseConditionGroup(BaseModel):
    allOf: list[ConditionRule] = Field(default_factory=list)
    anyOf: list[ConditionRule] = Field(default_factory=list)


class ResponseHandling(BaseModel):
    expectedContentType: str = "JSON"
    statusCode: ResponseStatusCodeRule = Field(default_factory=ResponseStatusCodeRule)
    businessSuccess: ResponseConditionGroup = Field(default_factory=ResponseConditionGroup)
    businessFailure: ResponseConditionGroup = Field(default_factory=ResponseConditionGroup)


class ErrorMapping(BaseModel):
    messageTemplate: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    fallbackMessage: str | None = None
    exposeRawResponse: bool = False


class RetryPolicy(BaseModel):
    enabled: bool = False
    maxAttempts: int = Field(default=1, ge=1)
    intervalMs: int = Field(default=1000, ge=0)
    retryOn: list[RetryErrorType] = Field(default_factory=list)


class SqlSourceSafety(BaseModel):
    requireWhere: bool = True
    maxAffectedRows: int | None = None
