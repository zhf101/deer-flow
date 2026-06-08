"""SQL 执行编排服务。"""

from __future__ import annotations

import json
import logging

from app.gdp.datagen.config.base.models import DatasourceConfig
from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.sqlsource.models import SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import SqlSourceNotFoundError, SqlSourceRepository
from app.gdp.datagen.runtime.sql.errors import (
    SqlExecutionRequestError,
    SqlParameterError,
    SqlSafetyError,
    UnsupportedDatabaseError,
)
from app.gdp.datagen.runtime.sql.models import (
    SqlExecutionOptions,
    SqlExecutionRequest,
    SqlExecutionResult,
    SqlSourceTestRequest,
)
from app.gdp.datagen.runtime.sql.parameters import bind_direct_parameters, bind_source_parameters
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.result import apply_output_mapping
from app.gdp.datagen.runtime.sql.safety import validate_sql_request

# 创建模块日志记录器
logger = logging.getLogger(__name__)


class SqlExecutionService:
    """加载 SQL 运行时资源、校验请求并分派到具体执行器。"""

    def __init__(
        self,
        *,
        base_repository: BaseConfigRepository,
        sql_source_repository: SqlSourceRepository,
        registry: SqlExecutorRegistry | None = None,
    ) -> None:
        self._base_repo = base_repository
        self._sql_repo = sql_source_repository
        self._registry = registry or SqlExecutorRegistry()

    async def execute_source(self, body: SqlSourceTestRequest) -> SqlExecutionResult:
        logger.info("【SQL 测试执行】开始执行 SQL 配置测试")
        logger.info("  配置编码: %s", body.sourceCode)
        logger.info("  环境编码: %s", body.envCode)
        if body.parameters:
            logger.info("  传入参数: %s", json.dumps(body.parameters, ensure_ascii=False, default=str))
        else:
            logger.info("  传入参数: 无")

        source = await self._sql_repo.get_sql_source(body.sourceCode)
        if source.status != ConfigStatus.ENABLED:
            logger.error("【SQL 测试执行】SQL 配置已禁用: %s", body.sourceCode)
            raise SqlExecutionRequestError(f"SQL source is disabled: {body.sourceCode}")

        logger.info("  配置名称: %s", source.sourceName)
        logger.info("  系统编码: %s", source.sysCode)
        logger.info("  数据源编码: %s", source.datasourceCode)

        sql_text = source.normalizedSql or source.sqlText
        parameters = bind_source_parameters(
            sql_text=sql_text,
            definitions=source.parameters,
            values=body.parameters,
        )
        request = _request_from_source(
            source=source,
            env_code=body.envCode,
            sql_text=sql_text,
            parameters=parameters,
            options=body.options,
            output_mapping=body.outputMapping,
        )
        datasource = await self._load_datasource(request)
        return await self.execute(request, datasource=datasource)

    async def execute(
        self,
        request: SqlExecutionRequest,
        *,
        datasource: DatasourceConfig | None = None,
    ) -> SqlExecutionResult:
        if datasource is None:
            request = request.model_copy(
                update={"parameters": bind_direct_parameters(request.sqlText, request.parameters)}
            )
            datasource = await self._load_datasource(request)

        logger.info("【SQL 安全校验】开始校验 SQL 请求")
        logger.info("  操作类型: %s", request.operation.value)
        logger.info("  WHERE 必填: %s", "是" if request.safety.requireWhere else "否")
        if request.safety.maxAffectedRows is not None:
            logger.info("  最大影响行数: %d", request.safety.maxAffectedRows)

        try:
            validate_sql_request(
                sql_text=request.sqlText,
                expected_operation=request.operation,
                safety=request.safety,
            )
            logger.info("  安全校验通过")
        except SqlSafetyError as exc:
            logger.error("【SQL 安全校验】校验失败: %s", str(exc))
            return SqlExecutionResult.failed(
                db_type=datasource.dbType,
                operation=request.operation,
                error_type=type(exc).__name__,
                message=str(exc),
            )

        executor = self._registry.get(datasource.dbType)
        logger.info("【SQL 执行分派】使用执行器: %s", type(executor).__name__)
        result = await executor.execute(datasource=datasource, request=request)
        return apply_output_mapping(result, request.outputMapping)

    async def _load_datasource(self, request: SqlExecutionRequest) -> DatasourceConfig:
        logger.info("【数据源解析】加载数据源配置")
        logger.info("  环境编码: %s", request.envCode)
        logger.info("  系统编码: %s", request.sysCode)
        logger.info("  数据源编码: %s", request.datasourceCode)
        try:
            datasource = await self._base_repo.get_enabled_datasource(
                env_code=request.envCode,
                sys_code=request.sysCode,
                datasource_code=request.datasourceCode,
            )
            logger.info("  数据源解析成功: %s (%s:%d)", datasource.datasourceName, datasource.host, datasource.port)
            return datasource
        except BaseConfigNotFoundError as exc:
            logger.error("【数据源解析】数据源未找到: %s", str(exc))
            raise SqlExecutionRequestError(
                f"当前选择的环境「{request.envCode}」还没有为系统「{request.sysCode}」"
                f"配置启用的数据源「{request.datasourceCode}」。"
                "请先到「基础配置 > 数据源」新增或启用对应配置后再测试 SQL。"
            ) from exc


def _request_from_source(
    *,
    source: SqlSourceResponse,
    env_code: str,
    sql_text: str,
    parameters: dict[str, object],
    options: SqlExecutionOptions,
    output_mapping: dict[str, str],
) -> SqlExecutionRequest:
    return SqlExecutionRequest(
        envCode=env_code,
        sysCode=source.sysCode,
        datasourceCode=source.datasourceCode,
        operation=source.operation,
        sqlText=sql_text,
        parameters=parameters,
        safety=source.safety,
        options=options,
        outputMapping=output_mapping,
    )


def status_code_for_error(exc: Exception) -> int:
    if isinstance(exc, SqlSourceNotFoundError):
        return 404
    if isinstance(exc, (SqlExecutionRequestError, SqlParameterError, UnsupportedDatabaseError)):
        return 422
    return 500
