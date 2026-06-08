"""SQL 运行时执行的数据模型契约。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.gdp.datagen.config.common.models import SqlOperation, SqlSourceSafety


class SqlExecutionOptions(BaseModel):
    """所有 SQL 执行入口共享的运行时选项。"""

    model_config = ConfigDict(extra="forbid")

    timeoutSeconds: int = Field(
        default=120,
        ge=1,
        le=600,
        description="数据库驱动连接、锁等待和网络读写超时秒数；后端不会用该字段提前返回正在执行的写 SQL。",
    )
    maxRows: int = Field(default=200, ge=1, le=5000, description="SELECT 最多返回行数，默认返回 200 行。")
    dryRun: bool = Field(default=False, description="只做解析和安全检查，不执行 SQL，也不提交写操作。")
    explain: bool = Field(default=False, description="是否请求执行计划。当前阶段仅预留，不影响执行。")


class SqlExecutionRequest(BaseModel):
    """直接 SQL 执行请求。

    SQL 文本应使用统一的命名参数形式，例如 ``where user_id = :userId``。
    """

    envCode: str = Field(..., min_length=1, max_length=64, description="执行 SQL 使用的环境编码。")
    sysCode: str = Field(..., min_length=1, max_length=64, description="SQL 所属系统编码，用于定位数据源。")
    datasourceCode: str = Field(..., min_length=1, max_length=128, description="本次 SQL 执行使用的数据源编码。")
    operation: SqlOperation = Field(..., description="前端声明的 SQL 操作类型，后端会和 SQL 文本解析结果一致性校验。")
    sqlText: str = Field(..., min_length=1, description="待执行 SQL 文本，参数使用统一命名参数形式，例如 :userId。")
    parameters: dict[str, Any] = Field(default_factory=dict, description="SQL 命名参数值，key 为参数名，value 为运行时绑定值。")
    safety: SqlSourceSafety = Field(default_factory=SqlSourceSafety, description="SQL 安全策略，运行时会强制校验。")
    options: SqlExecutionOptions = Field(default_factory=SqlExecutionOptions, description="SQL 执行选项。")
    outputMapping: dict[str, str] = Field(default_factory=dict, description="从 SQL 执行结果提取输出变量的映射规则。")


class SqlSourceTestRequest(BaseModel):
    """在指定环境下执行已保存的 SQL 配置。"""

    envCode: str = Field(..., min_length=1, max_length=64, description="执行已保存 SQL 配置使用的环境编码。")
    sourceCode: str = Field(..., min_length=1, max_length=128, description="待测试的 SQL 配置编码。")
    parameters: dict[str, Any] = Field(default_factory=dict, description="测试执行时传入的 SQL 参数值。")
    options: SqlExecutionOptions = Field(default_factory=SqlExecutionOptions, description="SQL 测试执行选项。")
    outputMapping: dict[str, str] = Field(default_factory=dict, description="测试执行时临时使用的输出提取映射。")


class SqlResultColumn(BaseModel):
    """标准化后的结果列。"""

    name: str
    type: str | None = None


class SqlExecutionErrorInfo(BaseModel):
    """SQL 执行结果中返回的错误信息。"""

    type: str
    message: str
    detail: str | None = None


class SqlExecutionResult(BaseModel):
    """查询和写操作语句统一返回的 SQL 执行结果。"""

    success: bool
    dbType: str
    operation: SqlOperation
    columns: list[SqlResultColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row: dict[str, Any] | None = None
    affectedRows: int = 0
    lastInsertId: Any = None
    generatedKeys: list[Any] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    elapsedMs: float | None = None
    extractedOutputs: dict[str, Any] = Field(default_factory=dict)
    error: SqlExecutionErrorInfo | None = None

    @classmethod
    def failed(
        cls,
        *,
        db_type: str,
        operation: SqlOperation,
        error_type: str,
        message: str,
        detail: str | None = None,
        elapsed_ms: float | None = None,
        warnings: list[str] | None = None,
    ) -> SqlExecutionResult:
        return cls(
            success=False,
            dbType=db_type,
            operation=operation,
            warnings=warnings or [],
            elapsedMs=elapsed_ms,
            error=SqlExecutionErrorInfo(type=error_type, message=message, detail=detail),
        )
