"""造数场景运行时执行引擎。"""

from __future__ import annotations

import heapq
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.common.models import InputFieldType
from app.gdp.datagen.config.httpsource.executor import execute_http_test
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.scene.expression import resolve_mapping
from app.gdp.datagen.config.scene.models import (
    HttpStepDefinition,
    SceneDefinition,
    SceneExecutionResult,
    SceneRunRequest,
    SceneVersion,
    SqlStepDefinition,
    StepDefinition,
    StepExecutionResult,
)
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter
from app.gdp.datagen.runtime.sql.models import SqlExecutionOptions, SqlExecutionRequest
from app.gdp.datagen.runtime.sql.parameters import bind_source_parameters
from app.gdp.datagen.runtime.sql.service import SqlExecutionService

# 创建模块日志记录器
logger = logging.getLogger(__name__)


class SceneExecutionError(RuntimeError):
    """场景执行无法继续。"""


class SceneExecutor:
    """执行已发布的场景定义。

    当前支持 HTTP 和 SQL 步骤。HTTP 步骤复用接口配置执行器，SQL 步骤复用
    SQL 运行时服务，断言和转换步骤在运行时契约接入前返回明确的不支持信息。
    """

    def __init__(
        self,
        sql_execution_service: SqlExecutionService,
        base_repository: BaseConfigRepository,
    ) -> None:
        self._sql = sql_execution_service
        self._base_repo = base_repository

    async def run(self, version: SceneVersion, request: SceneRunRequest) -> SceneExecutionResult:
        scene = version.definition
        logger.info("=" * 60)
        logger.info("【场景执行器】开始执行造数场景")
        logger.info("  场景编码: %s", scene.sceneCode)
        logger.info("  场景名称: %s", scene.sceneName)
        logger.info("  版本号: %s", version.versionNo)
        logger.info("  环境编码: %s", request.envCode)
        logger.info("  错误策略: %s", scene.errorPolicy)
        logger.info("  步骤数量: %d", len(scene.steps))
        if request.inputs:
            logger.info("【场景入参】")
            for key, value in request.inputs.items():
                logger.info("  %s = %s", key, json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else value)
        else:
            logger.info("  场景入参: 无")
        logger.info("=" * 60)

        started_at = _now()
        started = perf_counter()
        errors: list[str] = []
        step_results: list[StepExecutionResult] = []
        context = _initial_context(scene, request.inputs)
        step_order_by_id = {step.stepId: _step_order_value(step, index) for index, step in enumerate(scene.steps, 1)}

        for idx, step in enumerate(_execution_order(scene.steps), 1):
            logger.info("-" * 40)
            logger.info("【步骤 %d/%d】%s (%s)", idx, len(scene.steps), step.stepName, step.stepId)
            logger.info("  步骤类型: %s", step.type.value)
            logger.info("  是否启用: %s", "是" if step.enabled else "否")

            if not step.enabled:
                logger.info("  跳过原因: 步骤已禁用")
                result = _skipped_result(step, "step disabled")
                _apply_step_orders(result, step_order_by_id, idx)
                step_results.append(result)
                _add_step_context(context, result)
                continue

            if _dependency_failed(step, step_results):
                logger.warning("  跳过原因: 依赖步骤执行失败")
                result = _skipped_result(step, "dependency failed")
                _apply_step_orders(result, step_order_by_id, idx)
                step_results.append(result)
                _add_step_context(context, result)
                if scene.errorPolicy == "STOP_ON_ERROR":
                    logger.info("  错误策略为 STOP_ON_ERROR，停止执行")
                    break
                continue

            result = await self._execute_step(step, request.envCode, context)
            _apply_step_orders(result, step_order_by_id, idx)
            step_results.append(result)
            _add_step_context(context, result)

            logger.info("  执行状态: %s", result.status)
            logger.info("  执行耗时: %.3f 毫秒", result.durationMs)
            if result.outputs:
                logger.info("  输出变量:")
                for key, value in result.outputs.items():
                    logger.info("    %s = %s", key, value)
            if result.error:
                logger.error("  错误信息: %s", result.error)

            if result.status == "FAILED":
                errors.append(f"{step.stepId}: {result.error or 'step failed'}")
                if scene.errorPolicy == "STOP_ON_ERROR":
                    logger.info("  错误策略为 STOP_ON_ERROR，停止执行")
                    break

        final_output = resolve_mapping(scene.resultMapping, context)
        finished_at = _now()
        total_duration = round((perf_counter() - started) * 1000, 3)

        scene_status = _scene_status(step_results, errors)
        logger.info("=" * 60)
        logger.info("【场景执行器】执行完成")
        logger.info("  最终状态: %s", scene_status)
        logger.info("  总耗时: %.3f 毫秒", total_duration)
        if errors:
            logger.info("  错误数量: %d", len(errors))
            for err in errors:
                logger.error("    - %s", err)
        if final_output:
            logger.info("【最终输出】")
            logger.info("  %s", json.dumps(final_output, ensure_ascii=False, default=str))
        logger.info("=" * 60)

        return SceneExecutionResult(
            sceneCode=scene.sceneCode,
            versionNo=version.versionNo,
            envCode=request.envCode,
            inputs=request.inputs,
            status=scene_status,
            startedAt=started_at,
            finishedAt=finished_at,
            durationMs=total_duration,
            stepResults=step_results,
            finalOutput=final_output,
            errors=errors,
        )

    async def _execute_step(
        self,
        step: StepDefinition,
        env_code: str,
        context: dict[str, Any],
    ) -> StepExecutionResult:
        started_at = _now()
        started = perf_counter()
        try:
            if isinstance(step, HttpStepDefinition):
                http_result = await self._execute_http_step(step, env_code, context)
                error = http_result.error.message if http_result.error else None
                return StepExecutionResult(
                    stepId=step.stepId,
                    stepName=step.stepName,
                    type=step.type,
                    status="SUCCESS" if http_result.success else "FAILED",
                    startedAt=started_at,
                    finishedAt=_now(),
                    durationMs=round((perf_counter() - started) * 1000, 3),
                    outputs=http_result.extractedOutputs,
                    rawResponse=http_result.model_dump(mode="json"),
                    error=error,
                    statusCode=http_result.response.statusCode if http_result.response else None,
                )
            if not isinstance(step, SqlStepDefinition):
                raise SceneExecutionError(f"{step.type.value} step execution is not implemented yet")
            sql_result = await self._execute_sql_step(step, env_code, context)
            error = sql_result.error.message if sql_result.error else None
            return StepExecutionResult(
                stepId=step.stepId,
                stepName=step.stepName,
                type=step.type,
                status="SUCCESS" if sql_result.success else "FAILED",
                startedAt=started_at,
                finishedAt=_now(),
                durationMs=round((perf_counter() - started) * 1000, 3),
                outputs=sql_result.extractedOutputs,
                rawResponse=sql_result.model_dump(mode="json"),
                error=error,
            )
        except Exception as exc:
            logger.error("【步骤执行异常】步骤 %s 发生未预期异常: %s: %s",
                         step.stepId, type(exc).__name__, str(exc))
            # 返回给前端的错误信息只包含友好描述，不暴露内部堆栈
            safe_error = str(exc) if isinstance(exc, SceneExecutionError) else f"{step.stepName} 执行过程中发生异常，请检查配置。"
            return StepExecutionResult(
                stepId=step.stepId,
                stepName=step.stepName,
                type=step.type,
                status="FAILED",
                startedAt=started_at,
                finishedAt=_now(),
                durationMs=round((perf_counter() - started) * 1000, 3),
                outputs={},
                error=safe_error,
            )

    async def _execute_http_step(
        self,
        step: HttpStepDefinition,
        env_code: str,
        context: dict[str, Any],
    ):
        if not step.sysCode or not step.path:
            raise SceneExecutionError("HTTP step requires sysCode and path")

        logger.info("【HTTP 步骤详情】")
        logger.info("  系统编码: %s", step.sysCode)
        logger.info("  请求方法: %s", step.method.value)
        logger.info("  请求路径: %s", step.path)

        try:
            endpoint = await self._base_repo.get_enabled_service_endpoint(
                env_code=env_code,
                sys_code=step.sysCode,
            )
        except BaseConfigNotFoundError as exc:
            raise SceneExecutionError(str(exc)) from exc

        request_mapping = _deep_merge(
            resolve_mapping(step.requestMapping, context),
            resolve_mapping(step.httpParamMapping, context),
        )
        logger.info("  Base URL: %s", endpoint.baseUrl)
        logger.info("  请求映射: %s", json.dumps(request_mapping, ensure_ascii=False, default=str) if request_mapping else "无")

        config = HttpSourceConfig(
            sourceCode=step.stepId,
            sourceName=step.sourceName or step.stepName or step.stepId,
            sysCode=step.sysCode,
            path=step.path,
            method=step.method,
            timeoutConfig=step.timeoutConfig,
            requestMapping=request_mapping,
            bodySchema=step.bodySchema,
            responseSchema=step.responseSchema,
            responseHeadersSchema=step.responseHeadersSchema,
            responseCookiesSchema=step.responseCookiesSchema,
            responseHandling=step.responseHandling,
            errorMapping=step.errorMapping,
            businessErrorMapping=step.businessErrorMapping,
            outputMapping=step.outputMapping,
            outputMeta=step.outputMeta,
            retryPolicy=step.retryPolicy,
        )
        return await execute_http_test(config, endpoint.baseUrl, step.timeoutConfig)

    async def _execute_sql_step(
        self,
        step: SqlStepDefinition,
        env_code: str,
        context: dict[str, Any],
    ):
        if not step.sysCode or not step.datasourceCode or not step.operation:
            raise SceneExecutionError("SQL step requires sysCode, datasourceCode and operation")
        sql_text = step.normalizedSql or step.sqlText
        if not sql_text:
            raise SceneExecutionError("SQL step requires normalizedSql or sqlText")

        logger.info("【SQL 步骤详情】")
        logger.info("  系统编码: %s", step.sysCode)
        logger.info("  数据源编码: %s", step.datasourceCode)
        logger.info("  操作类型: %s", step.operation.value)
        logger.info("  SQL 文本: %s", sql_text)

        definitions = [SqlSourceParameter.model_validate(item) for item in step.parameters]
        raw_parameters = resolve_mapping(step.paramMapping, context)
        logger.info("  参数映射原始值: %s", json.dumps(raw_parameters, ensure_ascii=False, default=str) if raw_parameters else "无")
        parameters = bind_source_parameters(
            sql_text=sql_text,
            definitions=definitions,
            values=raw_parameters,
        )
        logger.info("  参数绑定结果: %s", json.dumps(parameters, ensure_ascii=False, default=str) if parameters else "无")

        if step.outputMapping:
            logger.info("  输出映射: %s", json.dumps(step.outputMapping, ensure_ascii=False))

        request = SqlExecutionRequest(
            envCode=env_code,
            sysCode=step.sysCode,
            datasourceCode=step.datasourceCode,
            operation=step.operation,
            sqlText=sql_text,
            parameters=parameters,
            safety=step.safety,
            options=SqlExecutionOptions(maxRows=200),
            outputMapping=step.outputMapping,
        )
        return await self._sql.execute(request)


def _initial_context(scene: SceneDefinition, inputs: dict[str, Any]) -> dict[str, Any]:
    merged_inputs = {field.name: _default_input_value(field) for field in scene.inputSchema}
    merged_inputs.update(inputs)
    return {"input": merged_inputs, "steps": {}}


def _default_input_value(field) -> Any:
    if field.defaultValue is not None:
        return field.defaultValue
    if field.type == InputFieldType.OBJECT and field.children:
        return {child.name: _default_input_value(child) for child in field.children}
    return None


def _execution_order(steps: list[StepDefinition]) -> list[StepDefinition]:
    enabled_by_id = {step.stepId: step for step in steps}
    order_index = {step.stepId: (_step_order_value(step, index + 1), index) for index, step in enumerate(steps)}
    graph: dict[str, list[str]] = defaultdict(list)
    indegree = {step.stepId: 0 for step in steps}
    for step in steps:
        for dep in step.dependsOn:
            if dep in enabled_by_id:
                graph[dep].append(step.stepId)
                indegree[step.stepId] += 1
    # 依赖满足后优先执行编排列表中更靠前的节点，保证执行时间线贴近用户看到的顺序。
    queue = [(order_index[step.stepId], step.stepId) for step in steps if indegree[step.stepId] == 0]
    heapq.heapify(queue)
    ordered_ids: list[str] = []
    while queue:
        _, step_id = heapq.heappop(queue)
        ordered_ids.append(step_id)
        for nxt in graph[step_id]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(queue, (order_index[nxt], nxt))
    if len(ordered_ids) != len(steps):
        raise SceneExecutionError("scene dependencies contain a cycle")
    return [enabled_by_id[step_id] for step_id in ordered_ids]


def _step_order_value(step: StepDefinition, fallback: int) -> int:
    """读取步骤执行顺序，草稿旧数据缺失时回退到当前列表位置。"""

    return step.executionOrder or fallback


def _dependency_failed(step: StepDefinition, results: list[StepExecutionResult]) -> bool:
    by_id = {result.stepId: result for result in results}
    return any(by_id.get(dep) is not None and by_id[dep].status != "SUCCESS" for dep in step.dependsOn)


def _add_step_context(context: dict[str, Any], result: StepExecutionResult) -> None:
    context["steps"][result.stepId] = {
        "outputs": result.outputs,
        "rawResponse": result.rawResponse,
        "status": result.status,
        "error": result.error,
    }


def _skipped_result(step: StepDefinition, reason: str) -> StepExecutionResult:
    now = _now()
    return StepExecutionResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=step.type,
        status="SKIPPED",
        startedAt=now,
        finishedAt=now,
        durationMs=0,
        outputs={},
        error=reason,
    )


def _apply_step_orders(
    result: StepExecutionResult,
    step_order_by_id: dict[str, int],
    timeline_order: int,
) -> None:
    """补充节点在编排列表和执行时间线中的顺序。"""

    result.stepOrder = step_order_by_id.get(result.stepId)
    result.timelineOrder = timeline_order


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并 HTTP 请求映射，后者覆盖前者。"""

    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _scene_status(results: list[StepExecutionResult], errors: list[str]) -> str:
    if not errors:
        return "SUCCESS"
    if any(result.status == "SUCCESS" for result in results):
        return "PARTIAL"
    return "FAILED"


def _now() -> datetime:
    return datetime.now(UTC)
