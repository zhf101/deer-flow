"""Pydantic models for GDP data-factory configuration APIs."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SceneStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DISABLED = "DISABLED"


class VersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class ConfigStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class StepType(StrEnum):
    HTTP = "HTTP"
    AUTH_HTTP = "AUTH_HTTP"
    SQL = "SQL"
    ASSERT = "ASSERT"
    TRANSFORM = "TRANSFORM"


class InputFieldType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ENUM = "enum"
    OBJECT = "object"
    ARRAY = "array"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class SqlOperation(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class ConditionOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    EMPTY = "EMPTY"
    NOT_EMPTY = "NOT_EMPTY"
    CONTAINS = "CONTAINS"
    REGEX = "REGEX"


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
    required: bool = False
    defaultValue: Any = None
    optionsSource: str | None = None
    validation: InputFieldValidation | None = None
    batchEnabled: bool = False
    children: list[InputFieldDefinition] | None = None


class Position(BaseModel):
    x: float = 0
    y: float = 0


class ConditionRule(BaseModel):
    path: str = Field(..., min_length=1)
    op: ConditionOperator
    value: Any = None


class StatusCodeRule(BaseModel):
    success: list[int] = Field(default_factory=lambda: [200])


class BusinessSuccessRule(BaseModel):
    allOf: list[ConditionRule] = Field(default_factory=list)


class BusinessFailureRule(BaseModel):
    anyOf: list[ConditionRule] = Field(default_factory=list)


class ResponseHandling(BaseModel):
    expectedContentType: Literal["JSON", "TEXT", "XML", "ANY"] = "JSON"
    statusCode: StatusCodeRule = Field(default_factory=StatusCodeRule)
    businessSuccess: BusinessSuccessRule = Field(default_factory=BusinessSuccessRule)
    businessFailure: BusinessFailureRule = Field(default_factory=BusinessFailureRule)


class ErrorMapping(BaseModel):
    messageTemplate: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    fallbackMessage: str | None = None
    exposeRawResponse: bool = False


class RetryPolicy(BaseModel):
    enabled: bool = False
    maxAttempts: int = Field(default=1, ge=1, le=10)
    intervalMs: int = Field(default=1000, ge=0, le=60000)
    retryOn: list[RetryErrorType] = Field(default_factory=list)


class AuthMapping(BaseModel):
    token: str | None = None
    tokenType: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)


class AssertionDefinition(BaseModel):
    expression: str = Field(..., min_length=1)
    message: str | None = None


class StepDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    stepId: str = Field(..., min_length=1, max_length=128)
    stepName: str | None = None
    type: StepType
    enabled: bool = True
    dependsOn: list[str] = Field(default_factory=list)
    description: str | None = None
    position: Position | None = None

    method: HttpMethod | None = None
    url: str | None = None
    requestMapping: dict[str, Any] = Field(default_factory=dict)
    bodySchema: list[InputFieldDefinition] | None = None
    bodyMapping: dict[str, Any] | None = None
    responseSchema: list[InputFieldDefinition] | None = None
    responseHandling: ResponseHandling | None = None
    errorMapping: ErrorMapping | None = None
    outputMapping: dict[str, str] = Field(default_factory=dict)
    outputMeta: dict[str, dict[str, str | None]] | None = None
    retryPolicy: RetryPolicy | None = None
    authMapping: AuthMapping | None = None

    datasource: str | None = None
    sqlTemplateCode: str | None = None
    operation: SqlOperation | None = None
    paramMapping: dict[str, Any] = Field(default_factory=dict)
    assertions: list[AssertionDefinition] = Field(default_factory=list)

    assignments: dict[str, str] = Field(default_factory=dict)


class BatchConfig(BaseModel):
    enabled: bool = False
    failurePolicy: Literal["STOP_ON_ERROR", "CONTINUE_ON_ERROR"] = "STOP_ON_ERROR"
    maxConcurrency: int = Field(default=1, ge=1, le=20)


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


class ValidationIssue(BaseModel):
    field: str
    message: str
    level: Literal["ERROR", "WARNING"] = "ERROR"


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class EnvironmentConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    envName: str = Field(..., min_length=1, max_length=256)
    status: ConfigStatus = ConfigStatus.ENABLED
    remark: str | None = None


class EnvironmentResponse(EnvironmentConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


class ServiceEndpointConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    serviceCode: str = Field(..., min_length=1, max_length=128)
    serviceName: str = Field(..., min_length=1, max_length=256)
    baseUrl: str = Field(..., min_length=1, max_length=1024)
    status: ConfigStatus = ConfigStatus.ENABLED


class ServiceEndpointResponse(ServiceEndpointConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


class DatasourceConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    datasourceCode: str = Field(..., min_length=1, max_length=128)
    datasourceName: str = Field(..., min_length=1, max_length=256)
    dbType: str = Field(..., min_length=1, max_length=64)
    host: str = Field(..., min_length=1, max_length=256)
    port: int = Field(..., ge=1, le=65535)
    databaseName: str = Field(..., min_length=1, max_length=256)
    username: str | None = None
    password: str | None = None
    status: ConfigStatus = ConfigStatus.ENABLED


class DatasourceResponse(DatasourceConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


class SqlTemplateParameter(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: InputFieldType | str
    required: bool = True
    defaultValue: Any = None


class SqlTemplateSafety(BaseModel):
    requireWhere: bool = True
    maxAffectedRows: int | None = Field(default=None, ge=1)


class SqlTemplateConfig(BaseModel):
    templateCode: str = Field(..., min_length=1, max_length=128)
    templateName: str = Field(..., min_length=1, max_length=256)
    operation: SqlOperation
    datasourceType: str = Field(..., min_length=1, max_length=64)
    sqlText: str = Field(..., min_length=1)
    parameters: list[SqlTemplateParameter] = Field(default_factory=list)
    safety: SqlTemplateSafety = Field(default_factory=SqlTemplateSafety)
    status: ConfigStatus = ConfigStatus.ENABLED


class SqlTemplateResponse(SqlTemplateConfig):
    id: str
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


class DisableResponse(BaseModel):
    success: bool = True
