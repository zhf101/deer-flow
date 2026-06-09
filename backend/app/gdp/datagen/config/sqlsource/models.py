"""SQL 配置 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.gdp.datagen.config.common.models import (
    ConfigStatus,
    InputFieldType,
    SqlOperation,
    SqlSourceSafety,
)


class SqlSourceParameter(BaseModel):
    """SQL 参数定义。

    这里描述 SQL 中需要由场景输入、前置步骤输出或默认值提供的变量。
    支持 ``:userId``、``#{userId}``、``${tenantId}`` 等参数形式解析后的统一表示。
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="参数名，不包含 :、#{}、${} 等占位符包装。例如 userId。",
    )
    type: InputFieldType | str = Field(
        ...,
        description="参数类型。优先使用标准输入字段类型，也允许保留数据库方言或业务自定义类型。",
    )
    required: bool = Field(
        default=True,
        description="是否必填。必填参数在编排步骤中必须完成参数映射或提供默认值。",
    )
    defaultValue: Any = Field(
        default=None,
        description="参数默认值。当步骤参数映射未提供该参数时可作为兜底值。",
    )
    description: str | None = Field(
        default=None,
        description="参数用途说明，便于配置人员理解该参数对应的业务含义。",
    )


class SqlSourceParseRequest(BaseModel):
    """SQL 解析请求。

    前端在录入或修改 SQL 后调用解析接口，用于标准化 SQL、推导操作类型、
    识别表、结果字段、条件字段和参数列表。
    """

    sqlText: str = Field(
        ...,
        min_length=1,
        description="待解析的 SQL 文本。支持普通 SQL、命名参数 SQL 和部分 MyBatis XML 片段。",
    )
    parameters: list[SqlSourceParameter] = Field(
        default_factory=list,
        description="用户已维护的参数定义。解析结果会尽量保留已有类型、默认值和说明。",
    )


class SqlSourceTableMeta(BaseModel):
    """SQL 涉及的数据表元数据。"""

    id: str = Field(..., description="前端列表行 ID，用于稳定渲染和编辑。")
    tableName: str = Field(..., description="表名。")
    alias: str = Field(default="", description="SQL 中使用的表别名。")
    description: str = Field(default="", description="表用途说明。")


class SqlSourceFieldMeta(BaseModel):
    """SELECT 查询结果字段元数据。"""

    id: str = Field(..., description="前端列表行 ID，用于稳定渲染和编辑。")
    fieldName: str = Field(..., description="字段名或表达式。")
    sourceTable: str = Field(default="", description="字段来源表名或表别名。")
    alias: str = Field(default="", description="字段查询别名。")
    description: str = Field(default="", description="字段含义说明。")


class SqlSourceConditionMeta(BaseModel):
    """SQL 条件字段元数据。"""

    id: str = Field(..., description="前端列表行 ID，用于稳定渲染和编辑。")
    fieldName: str = Field(..., description="与 SQL 参数绑定的条件字段名，通常来自 WHERE、HAVING 或带参数的 JOIN ON。")
    sourceTable: str = Field(default="", description="条件字段来源表名或表别名。")
    paramName: str = Field(default="", description="该条件绑定的参数名。")
    description: str = Field(default="", description="条件用途说明。")


class SqlSourceParseResponse(BaseModel):
    """SQL 解析结果。"""

    normalizedSql: str = Field(
        ...,
        description="标准化后的 SQL 文本。可去除 XML 包装或统一占位符格式。",
    )
    operation: SqlOperation = Field(..., description="SQL 操作类型。")
    tables: list[SqlSourceTableMeta] = Field(
        default_factory=list,
        description="SQL 涉及的数据表列表。",
    )
    resultFields: list[SqlSourceFieldMeta] = Field(
        default_factory=list,
        description="SELECT 查询结果字段列表。非 SELECT SQL 通常为空。",
    )
    conditionFields: list[SqlSourceConditionMeta] = Field(
        default_factory=list,
        description="SQL 参数绑定条件字段列表，用于辅助理解入参与字段的对应关系。",
    )
    parameters: list[SqlSourceParameter] = Field(
        default_factory=list,
        description="解析出的参数定义列表。",
    )


class SqlSourceConfig(BaseModel):
    """可复用 SQL 配置。

    一条 SQL 配置描述一个可被编排步骤复用的数据库操作。它通过 ``sysCode``
    归属到系统，通过 ``datasourceCode`` 引用该系统下的基础数据源配置。
    """

    sourceCode: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="SQL 配置唯一编码。编排 SQL 步骤通过该编码引用 SQL 配置。",
    )
    sourceName: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="SQL 名称或用途说明，用于列表展示和人工识别。",
    )
    sysCode: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="所属系统编码，关联基础配置 SysConfig.sysCode。",
    )
    datasourceCode: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="数据源编码，关联基础配置 DatasourceConfig.datasourceCode，并与 sysCode 共同确定数据源归属。",
    )
    operation: SqlOperation = Field(..., description="SQL 操作类型。")
    sqlText: str = Field(
        ...,
        min_length=1,
        description="SQL 文本。支持命名参数、MyBatis 风格参数和可执行 SQL 片段。",
    )
    normalizedSql: str = Field(
        default="",
        description="解析后用于运行时执行的规范 SQL。占位符统一保留命名参数形式，例如 :userId。",
    )
    tables: list[SqlSourceTableMeta] = Field(
        default_factory=list,
        description="SQL 涉及的数据表元数据。保存后用于页面直接回显操作表说明。",
    )
    resultFields: list[SqlSourceFieldMeta] = Field(
        default_factory=list,
        description="SELECT 查询结果字段元数据。保存后用于页面直接回显查询结果字段说明。",
    )
    conditionFields: list[SqlSourceConditionMeta] = Field(
        default_factory=list,
        description="WHERE、JOIN ON、UPDATE 条件等位置涉及的条件字段元数据。",
    )
    parameters: list[SqlSourceParameter] = Field(
        default_factory=list,
        description="SQL 参数定义列表，用于约束编排步骤中的参数映射。",
    )
    safety: SqlSourceSafety = Field(
        default_factory=SqlSourceSafety,
        description="SQL 安全策略。例如 UPDATE/DELETE 是否要求 WHERE、最大影响行数等。",
    )
    status: ConfigStatus = Field(
        default=ConfigStatus.ENABLED,
        description="配置状态。只有启用状态的 SQL 配置可用于发布和运行。",
    )


class SqlSourceResponse(SqlSourceConfig):
    """SQL 配置查询响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    createdBy: str | None = Field(default=None, description="创建人标识。")
    updatedBy: str | None = Field(default=None, description="最近更新人标识。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")


class DisableResponse(BaseModel):
    """停用或删除操作响应。"""

    success: bool = Field(default=True, description="操作是否成功。")
