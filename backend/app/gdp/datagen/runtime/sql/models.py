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

    name: str = Field(..., description="结果列名称。")
    type: str | None = Field(default=None, description="数据库驱动返回或后端推断的列类型。")


class SqlExecutionErrorInfo(BaseModel):
    """SQL 执行结果中返回的错误信息。"""

    type: str = Field(..., description="错误类型，用于前端和 Agent 判断失败类别。")
    message: str = Field(..., description="人类可读的错误说明。")
    detail: str | None = Field(default=None, description="错误详情，已由后端控制敏感信息暴露。")


class SqlExecutionResult(BaseModel):
    """查询和写操作语句统一返回的 SQL 执行结果。"""

    success: bool = Field(..., description="SQL 是否执行成功。")
    dbType: str = Field(..., description="实际执行 SQL 的数据库类型。")
    operation: SqlOperation = Field(..., description="SQL 操作类型。")
    columns: list[SqlResultColumn] = Field(default_factory=list, description="SELECT 查询返回的列信息。")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="SELECT 查询返回的多行结果。")
    row: dict[str, Any] | None = Field(default=None, description="便捷单行结果，通常为 rows 的第一行。")
    affectedRows: int = Field(default=0, description="写操作影响行数。")
    lastInsertId: Any = Field(default=None, description="插入操作返回的最后插入 ID，不同数据库可能为空。")
    generatedKeys: list[Any] = Field(default_factory=list, description="写操作生成的主键或返回键列表。")
    warnings: list[str] = Field(default_factory=list, description="执行过程中的非阻断警告。")
    elapsedMs: float | None = Field(default=None, description="SQL 执行耗时，单位毫秒。")
    extractedOutputs: dict[str, Any] = Field(default_factory=dict, description="按 outputMapping 提取出的输出变量。")
    error: SqlExecutionErrorInfo | None = Field(default=None, description="失败时返回的错误信息。")

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
