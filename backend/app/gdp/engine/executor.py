"""GDP 场景执行器主入口。

负责将已发布的场景配置转化为实际的操作：
1. 加载已发布的场景版本（status 必须为 PUBLISHED）
2. 校验输入参数（根据 inputSchema 检查必填项和类型）
3. 创建执行上下文，预加载服务端点和数据源配置
4. 按数组顺序逐步执行，分发到具体步骤执行器
5. 失败时根据 batchConfig.failurePolicy 决定是停止还是继续
6. 解析 resultMapping 构建最终输出
7. 返回完整的 ExecutionResult
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.gdp.engine.context import ExecutionContext
from app.gdp.engine.models import ExecutionRequest, ExecutionResult, StepResult
from app.gdp.engine.steps import execute_step
from app.gdp.engine.variable_resolver import resolve_value
from app.gdp.models import (
    ConfigStatus,
    InputFieldDefinition,
    SceneDefinition,
    SceneStatus,
    SqlTemplateConfig,
    StepDefinition,
)
from app.gdp.persistence.model import (
    DataFactoryDatasourceRow,
    DataFactorySceneRow,
    DataFactorySceneVersionRow,
    DataFactoryServiceEndpointRow,
    DataFactorySqlTemplateRow,
)
from app.gdp.persistence.repository import DataFactoryNotFoundError, _loads

from sqlalchemy import select

logger = logging.getLogger(__name__)


class SceneExecutor:
    """GDP 场景执行器——加载已发布场景并逐步执行。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def execute(self, scene_code: str, request: ExecutionRequest) -> ExecutionResult:
        """执行一个已发布的场景。

        Args:
            scene_code: 场景编码
            request: 执行请求（包含 envCode 和 inputs）

        Returns:
            完整的执行结果

        Raises:
            HTTPException: 场景未找到或未发布时抛出
        """
        started_at = datetime.now(UTC)

        # ── 1. 加载已发布版本 ──
        scene_row, version_row, definition = await self._load_published_scene(scene_code)

        # ── 2. 校验输入参数 ──
        validation_errors = self._validate_inputs(definition.inputSchema, request.inputs)
        if validation_errors:
            finished_at = datetime.now(UTC)
            return ExecutionResult(
                sceneCode=scene_code,
                versionNo=version_row.version_no,
                envCode=request.envCode,
                status="FAILED",
                startedAt=started_at,
                finishedAt=finished_at,
                durationMs=_duration_ms(started_at, finished_at),
                errors=validation_errors,
            )

        # ── 3. 创建执行上下文 ──
        ctx = ExecutionContext(inputs=request.inputs, env_code=request.envCode)

        # 预加载服务端点
        await self._load_service_endpoints(ctx, request.envCode)

        # 预加载数据源
        await self._load_datasources(ctx, request.envCode)

        # 预加载 SQL 模板（供 SQL 步骤使用）
        sql_templates = await self._load_sql_templates()

        # ── 4. 逐步执行 ──
        step_results: list[StepResult] = []
        stop_on_error = definition.batchConfig.failurePolicy == "STOP_ON_ERROR"

        for step_def in definition.steps:
            # 跳过禁用的步骤
            if not step_def.enabled:
                now = datetime.now(UTC)
                step_results.append(StepResult(
                    stepId=step_def.stepId,
                    stepName=step_def.stepName,
                    type=step_def.type,
                    status="SKIPPED",
                    startedAt=now,
                    finishedAt=now,
                    durationMs=0,
                ))
                continue

            # 执行步骤
            result = await execute_step(
                step_def, ctx,
                sql_template_resolver=lambda code: sql_templates.get(code),
                datasource_resolver=lambda ds_code, env: self._resolve_datasource_url(
                    ds_code, env, ctx.datasources
                ),
            )
            step_results.append(result)

            if result.status == "FAILED":
                ctx.errors.append(f"步骤 {step_def.stepId} 执行失败: {result.error}")
                if stop_on_error:
                    break

        # ── 5. 构建最终输出（resultMapping）──
        final_output: dict[str, Any] = {}
        if not ctx.errors:
            final_output = self._resolve_result_mapping(definition.resultMapping, ctx)

        finished_at = datetime.now(UTC)
        status = "SUCCESS" if not ctx.errors else "FAILED"

        return ExecutionResult(
            sceneCode=scene_code,
            versionNo=version_row.version_no,
            envCode=request.envCode,
            status=status,
            startedAt=started_at,
            finishedAt=finished_at,
            durationMs=_duration_ms(started_at, finished_at),
            stepResults=step_results,
            finalOutput=final_output,
            errors=ctx.errors,
        )

    # ── 内部方法 ──────────────────────────────────────────────────────

    async def _load_published_scene(
        self, scene_code: str
    ) -> tuple[DataFactorySceneRow, DataFactorySceneVersionRow, SceneDefinition]:
        """加载已发布的场景定义。"""
        from fastapi import HTTPException

        async with self._sf() as session:
            # 查找场景
            stmt = select(DataFactorySceneRow).where(DataFactorySceneRow.scene_code == scene_code)
            scene_row = (await session.execute(stmt)).scalar_one_or_none()
            if scene_row is None:
                raise HTTPException(status_code=404, detail=f"场景不存在: {scene_code}")

            if scene_row.status != SceneStatus.PUBLISHED.value:
                raise HTTPException(status_code=400, detail=f"场景未发布，当前状态: {scene_row.status}")

            # 获取最新版本
            stmt = (
                select(DataFactorySceneVersionRow)
                .where(DataFactorySceneVersionRow.scene_id == scene_row.id)
                .order_by(DataFactorySceneVersionRow.version_no.desc())
                .limit(1)
            )
            version_row = (await session.execute(stmt)).scalar_one_or_none()
            if version_row is None:
                raise HTTPException(status_code=404, detail="场景版本不存在")

            # 重建 SceneDefinition
            definition = SceneDefinition(
                sceneCode=scene_row.scene_code,
                sceneName=scene_row.scene_name,
                sceneRemark=scene_row.scene_remark,
                sceneType=scene_row.scene_type,
                environmentField=version_row.environment_field,
                inputSchema=_loads(version_row.input_schema_json, []),
                steps=_loads(version_row.steps_json, []),
                resultMapping=_loads(version_row.result_mapping_json, {}),
                batchConfig=_loads(version_row.batch_config_json, {}),
                status=scene_row.status,
            )

            return scene_row, version_row, definition

    async def _load_service_endpoints(self, ctx: ExecutionContext, env_code: str) -> None:
        """预加载指定环境的服务端点配置。"""
        async with self._sf() as session:
            stmt = (
                select(DataFactoryServiceEndpointRow)
                .where(
                    DataFactoryServiceEndpointRow.env_code == env_code,
                    DataFactoryServiceEndpointRow.status == ConfigStatus.ENABLED.value,
                )
            )
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                ctx.service_endpoints[row.service_code] = row.base_url

    async def _load_datasources(self, ctx: ExecutionContext, env_code: str) -> None:
        """预加载指定环境的数据源配置。"""
        async with self._sf() as session:
            stmt = (
                select(DataFactoryDatasourceRow)
                .where(
                    DataFactoryDatasourceRow.env_code == env_code,
                    DataFactoryDatasourceRow.status == ConfigStatus.ENABLED.value,
                )
            )
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                ctx.datasources[row.datasource_code] = {
                    "datasourceCode": row.datasource_code,
                    "dbType": row.db_type,
                    "host": row.host,
                    "port": row.port,
                    "databaseName": row.database_name,
                    "username": row.username,
                    "password": row.password,
                }

    async def _load_sql_templates(self) -> dict[str, SqlTemplateConfig]:
        """预加载所有启用的 SQL 模板。"""
        async with self._sf() as session:
            stmt = (
                select(DataFactorySqlTemplateRow)
                .where(DataFactorySqlTemplateRow.status == ConfigStatus.ENABLED.value)
            )
            rows = (await session.execute(stmt)).scalars().all()
            templates: dict[str, SqlTemplateConfig] = {}
            for row in rows:
                templates[row.template_code] = SqlTemplateConfig(
                    templateCode=row.template_code,
                    templateName=row.template_name,
                    operation=row.operation,
                    datasourceType=row.datasource_type,
                    sqlText=row.sql_text,
                    parameters=_loads(row.parameters_json, []),
                    safety=_loads(row.safety_json, {}),
                    status=row.status,
                )
            return templates

    def _validate_inputs(
        self, schema: list[InputFieldDefinition], inputs: dict[str, Any]
    ) -> list[str]:
        """校验输入参数是否满足 inputSchema 约束。返回错误列表。"""
        errors: list[str] = []
        for field in schema:
            value = inputs.get(field.name)
            # 必填检查
            if field.required and (value is None or value == ""):
                if field.defaultValue is None:
                    label = field.label or field.name
                    errors.append(f"必填参数缺失: {label}")
            # 类型检查（简单校验）
            if value is not None and value != "":
                if field.type == "number" and not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        errors.append(f"参数 {field.name} 类型错误: 期望数字类型")
        return errors

    def _resolve_result_mapping(
        self, result_mapping: dict[str, Any], ctx: ExecutionContext
    ) -> dict[str, Any]:
        """解析 resultMapping 构建最终输出。

        resultMapping 的 key 可能是 "$.orderNo" 或 "orderNo" 格式，
        值通常是变量引用如 "${steps.createOrder.outputs.orderNo}"。
        """
        output: dict[str, Any] = {}
        for key, value_ref in result_mapping.items():
            # 清理 key 的 "$." 前缀
            clean_key = key.removeprefix("$.").removeprefix("$.")
            # 解析变量引用
            resolved = resolve_value(value_ref, ctx)
            output[clean_key] = resolved
        return output

    @staticmethod
    def _resolve_datasource_url(
        ds_code: str, env_code: str, datasources: dict[str, Any]
    ) -> str | None:
        """根据数据源配置构建 SQLAlchemy 连接 URL。"""
        ds_config = datasources.get(ds_code)
        if ds_config is None:
            return None

        db_type = ds_config.get("dbType", "").upper()
        host = ds_config.get("host", "")
        port = ds_config.get("port", "")
        db_name = ds_config.get("databaseName", "")
        username = ds_config.get("username") or ""
        password = ds_config.get("password") or ""

        # 构建认证部分
        auth_part = ""
        if username:
            auth_part = f"{username}:{password}@" if password else f"{username}@"

        if db_type == "MYSQL":
            return f"mysql+aiomysql://{auth_part}{host}:{port}/{db_name}"
        if db_type in ("POSTGRESQL", "POSTGRES"):
            return f"postgresql+asyncpg://{auth_part}{host}:{port}/{db_name}"
        if db_type == "SQLITE":
            return f"sqlite+aiosqlite:///{db_name}"

        logger.warning("不支持的数据库类型: %s", db_type)
        return None


def _duration_ms(started: datetime, finished: datetime) -> int:
    """计算毫秒差。"""
    return int((finished - started).total_seconds() * 1000)
