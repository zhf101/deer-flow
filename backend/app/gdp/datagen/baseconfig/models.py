"""基础配置 Pydantic 数据模型：环境、服务端点、数据源。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.gdp.models import ConfigStatus


# ── 环境配置 ──────────────────────────────────────────────────────────


class EnvironmentConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    envName: str = Field(..., min_length=1, max_length=256)
    status: ConfigStatus = ConfigStatus.ENABLED
    remark: str | None = None


class EnvironmentResponse(EnvironmentConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


# ── 服务端点配置 ──────────────────────────────────────────────────────


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


# ── 数据源配置 ────────────────────────────────────────────────────────


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


# ── 通用操作结果 ──────────────────────────────────────────────────────


class DisableResponse(BaseModel):
    success: bool = True
