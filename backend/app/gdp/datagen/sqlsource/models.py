"""SQL 配置 Pydantic 数据模型（从 SqlTemplate 演进）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.gdp.models import (
    ConfigStatus,
    InputFieldType,
    SqlOperation,
    SqlTemplateSafety,
)


class SqlSourceParameter(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: InputFieldType | str
    required: bool = True
    defaultValue: Any = None
    description: str | None = None


class SqlSourceParseRequest(BaseModel):
    sqlText: str = Field(..., min_length=1)
    parameters: list[SqlSourceParameter] = Field(default_factory=list)


class SqlSourceTableMeta(BaseModel):
    id: str
    tableName: str
    alias: str = ""
    description: str = ""


class SqlSourceFieldMeta(BaseModel):
    id: str
    fieldName: str
    sourceTable: str = ""
    alias: str = ""
    description: str = ""


class SqlSourceConditionMeta(BaseModel):
    id: str
    fieldName: str
    sourceTable: str = ""
    paramName: str = ""
    description: str = ""


class SqlSourceParseResponse(BaseModel):
    normalizedSql: str
    operation: SqlOperation
    tables: list[SqlSourceTableMeta] = Field(default_factory=list)
    resultFields: list[SqlSourceFieldMeta] = Field(default_factory=list)
    conditionFields: list[SqlSourceConditionMeta] = Field(default_factory=list)
    parameters: list[SqlSourceParameter] = Field(default_factory=list)


class SqlSourceConfig(BaseModel):
    """可复用的 SQL 配置，引用 baseconfig 的数据源。"""

    sourceCode: str = Field(..., min_length=1, max_length=128)
    sourceName: str = Field(..., min_length=1, max_length=256)
    datasourceCode: str = Field(..., min_length=1, max_length=128)
    operation: SqlOperation
    sqlText: str = Field(..., min_length=1)
    parameters: list[SqlSourceParameter] = Field(default_factory=list)
    safety: SqlTemplateSafety = Field(default_factory=SqlTemplateSafety)
    status: ConfigStatus = ConfigStatus.ENABLED


class SqlSourceResponse(SqlSourceConfig):
    id: str
    createdBy: str | None = None
    updatedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime


class DisableResponse(BaseModel):
    success: bool = True
