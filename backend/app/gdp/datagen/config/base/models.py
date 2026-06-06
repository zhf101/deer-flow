"""Base configuration API models for datagen.

This module matches the frontend contract in
``frontend/src/gdp/datagen/common/lib/types.ts`` for environments, service
endpoints, and datasources.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.gdp.datagen.config.common.models import ConfigStatus


class EnvironmentConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    envName: str = Field(..., min_length=1, max_length=256)
    status: ConfigStatus = ConfigStatus.ENABLED
    remark: str | None = None


class SysConfig(BaseModel):
    sysCode: str = Field(..., min_length=1, max_length=64)
    sysName: str = Field(..., min_length=1, max_length=256)
    status: ConfigStatus = ConfigStatus.ENABLED
    remark: str | None = None


class SysConfigResponse(SysConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


class EnvironmentResponse(EnvironmentConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


class ServiceEndpointConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    sysCode: str = Field(..., min_length=1, max_length=64)
    baseUrl: str = Field(..., min_length=1, max_length=1024)
    status: ConfigStatus = ConfigStatus.ENABLED


class ServiceEndpointResponse(ServiceEndpointConfig):
    id: str
    createdAt: datetime
    updatedAt: datetime


class DatasourceConfig(BaseModel):
    envCode: str = Field(..., min_length=1, max_length=64)
    sysCode: str = Field(..., min_length=1, max_length=64)
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


class OperationResponse(BaseModel):
    success: bool = True
