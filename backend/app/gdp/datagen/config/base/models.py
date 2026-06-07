"""造数基础配置 API 数据模型。

本模块和前端 ``frontend/src/gdp/datagen/common/lib/types.ts`` 的基础配置
契约保持一致，覆盖系统、环境、HTTP 服务端点和数据库数据源配置。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.gdp.datagen.config.common.models import ConfigStatus


class IdentifierReferenceType(StrEnum):
    """标识引用类型。"""

    TIME = "TIME"
    MATCHER = "MATCHER"
    TPN = "TPN"
    LOGIN = "LOGIN"
    BASE64 = "BASE64"


class EnvironmentConfig(BaseModel):
    """环境配置。

    环境用于区分 dev、test、pre、prod 等部署上下文。服务端点和数据源都需要
    绑定环境，运行时根据环境选择对应连接信息。
    """

    envCode: str = Field(..., min_length=1, max_length=64, description="环境唯一编码，例如 dev、test、prod。")
    envName: str = Field(..., min_length=1, max_length=256, description="环境名称，用于页面展示。")
    status: ConfigStatus = Field(default=ConfigStatus.ENABLED, description="环境状态。禁用后不建议用于运行。")
    remark: str | None = Field(default=None, description="环境备注说明。")


class SysConfig(BaseModel):
    """系统配置。

    系统是 HTTP 接口配置、SQL 配置、服务端点和数据源的归属边界。通过
    ``sysCode`` 可以把一个业务系统下的接口和数据库配置关联起来。
    """

    sysCode: str = Field(..., min_length=1, max_length=64, description="系统唯一编码。HTTP 接口配置和 SQL 配置通过该编码归属到系统。")
    sysName: str = Field(..., min_length=1, max_length=256, description="系统名称，用于页面展示和人工识别。")
    status: ConfigStatus = Field(default=ConfigStatus.ENABLED, description="系统状态。禁用后不建议新增运行配置引用。")
    remark: str | None = Field(default=None, description="系统备注说明。")


class SysConfigResponse(SysConfig):
    """系统配置查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class EnvironmentResponse(EnvironmentConfig):
    """环境配置查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class ServiceEndpointConfig(BaseModel):
    """HTTP 服务端点配置。

    一条服务端点配置描述某个系统在某个环境下的 Base URL。HTTP 接口配置只保存
    相对路径，运行时通过 ``envCode + sysCode`` 找到这里的 ``baseUrl``。
    """

    envCode: str = Field(..., min_length=1, max_length=64, description="环境编码，关联 EnvironmentConfig.envCode。")
    sysCode: str = Field(..., min_length=1, max_length=64, description="系统编码，关联 SysConfig.sysCode。")
    baseUrl: str = Field(..., min_length=1, max_length=1024, description="系统在该环境下的 HTTP Base URL。")
    status: ConfigStatus = Field(default=ConfigStatus.ENABLED, description="服务端点状态。只有启用状态建议用于运行。")


class ServiceEndpointResponse(ServiceEndpointConfig):
    """HTTP 服务端点查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class DatasourceConfig(BaseModel):
    """数据库数据源配置。

    一条数据源配置描述某个系统在某个环境下的数据库连接信息。SQL 配置通过
    ``sysCode + datasourceCode`` 引用数据源，运行时再结合 ``envCode`` 获取
    具体连接参数。
    """

    envCode: str = Field(..., min_length=1, max_length=64, description="环境编码，关联 EnvironmentConfig.envCode。")
    sysCode: str = Field(..., min_length=1, max_length=64, description="系统编码，关联 SysConfig.sysCode。")
    datasourceCode: str = Field(..., min_length=1, max_length=128, description="数据源唯一编码。同一环境、同一系统下唯一。")
    datasourceName: str = Field(..., min_length=1, max_length=256, description="数据源名称，用于页面展示。")
    dbType: str = Field(..., min_length=1, max_length=64, description="数据库类型，例如 MySQL、PostgreSQL、Oracle。")
    host: str = Field(..., min_length=1, max_length=256, description="数据库主机地址。")
    port: int = Field(..., ge=1, le=65535, description="数据库端口。")
    databaseName: str = Field(..., min_length=1, max_length=256, description="数据库名或服务名。")
    username: str | None = Field(default=None, description="数据库用户名。")
    password: str | None = Field(default=None, description="数据库密码或凭据密文。")
    status: ConfigStatus = Field(default=ConfigStatus.ENABLED, description="数据源状态。只有启用状态建议用于运行。")


class DatasourceResponse(DatasourceConfig):
    """数据库数据源查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class IdentifierReferenceParameter(BaseModel):
    """标识引用参数说明。"""

    name: str = Field(..., min_length=1, max_length=128, description="参数名，例如 type、pattern、offset。")
    description: str = Field(..., description="参数含义说明。")
    required: bool = Field(default=False, description="该参数是否必填。")
    defaultValue: Any = Field(default=None, description="参数默认值。")


class IdentifierReferenceExample(BaseModel):
    """标识引用示例。"""

    expression: str = Field(..., min_length=1, max_length=1024, description="完整标识引用表达式。")
    description: str = Field(..., description="示例说明。")


class IdentifierReferenceConfig(BaseModel):
    """系统内置标识引用配置。

    标识引用是运行时表达式能力，不允许用户新增任意标识。页面只维护系统预置
    标识的说明、示例、适用位置和启停状态。
    """

    refCode: str = Field(..., min_length=1, max_length=64, description="标识编码，例如 TIME、MATCHER、TPN。")
    refName: str = Field(..., min_length=1, max_length=128, description="标识名称，例如 时间偏移、正则表达式。")
    refType: IdentifierReferenceType = Field(..., description="标识引用类型。")
    syntax: str = Field(..., min_length=1, max_length=512, description="标识语法，例如 ${type(pattern)offset}。")
    description: str = Field(..., description="标识用途说明。")
    usageScope: list[str] = Field(default_factory=list, description="可引用位置，例如发送前、报文节点、预期结果、发送后处理。")
    parameters: list[IdentifierReferenceParameter] = Field(default_factory=list, description="参数说明列表。")
    examples: list[IdentifierReferenceExample] = Field(default_factory=list, description="示例列表。")
    status: ConfigStatus = Field(default=ConfigStatus.ENABLED, description="标识状态。停用后运行时不应解析该标识。")
    remark: str | None = Field(default=None, description="备注说明。")


class IdentifierReferenceResponse(IdentifierReferenceConfig):
    """系统内置标识引用查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class OperationResponse(BaseModel):
    """通用操作响应。"""

    success: bool = Field(default=True, description="操作是否成功。")
