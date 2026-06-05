"""HTTP 步骤执行器。

负责：
1. 解析 URL 中的变量引用（如 ``${env.services.auth.baseUrl}/api/login``）
2. 构建请求（headers / query params / body）
3. 通过 httpx 发送异步 HTTP 请求
4. 评估 responseHandling（状态码 + 业务规则）
5. 通过 outputMapping 的 JSONPath 提取输出变量
6. 根据 errorMapping 构建友好的错误信息
7. 支持 retryPolicy 重试策略
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.gdp.engine.condition_evaluator import evaluate_all_of, evaluate_any_of
from app.gdp.engine.context import ExecutionContext
from app.gdp.engine.jsonpath_utils import jsonpath_extract
from app.gdp.engine.models import StepResult
from app.gdp.engine.variable_resolver import resolve_value
from app.gdp.models import (
    ErrorMapping,
    RetryErrorType,
    RetryPolicy,
    ResponseHandling,
    StepDefinition,
)

# 默认 HTTP 超时时间（秒）
DEFAULT_TIMEOUT = 30.0


async def execute_http_step(step: StepDefinition, ctx: ExecutionContext) -> StepResult:
    """执行 HTTP 步骤。"""
    started_at = datetime.now(UTC)

    # ── 1. 解析 URL ──
    url = resolve_value(step.url or "", ctx)
    if not url:
        return _fail(step, started_at, "HTTP 步骤 URL 为空")

    method = (step.method or "GET").value if step.method else "GET"

    # ── 2. 构建请求头和请求体 ──
    resolved_mapping = resolve_value(step.requestMapping or {}, ctx)
    headers = dict(resolved_mapping.get("headers", {}))
    params = resolved_mapping.get("query") or resolved_mapping.get("params")
    body_type = resolved_mapping.get("bodyType", "raw-json")

    # 根据 bodyType 决定请求体发送方式
    request_kwargs: dict[str, Any] = {
        "headers": headers,
        "params": params,
    }
    if method.upper() == "POST":
        if body_type == "x-www-form-urlencoded":
            # URL 编码表单: key=value&key2=value2
            url_data = resolved_mapping.get("urlEncodedData") or {}
            request_kwargs["data"] = url_data
        elif body_type == "form-data":
            # multipart/form-data: 数组格式的表单字段
            form_rows = resolved_mapping.get("formData") or []
            form_data = {}
            for row in form_rows:
                if isinstance(row, dict) and row.get("key") and row.get("enabled", True):
                    form_data[row["key"]] = row.get("value", "")
            request_kwargs["data"] = form_data
        elif body_type in ("raw-text", "raw-xml"):
            # 原始文本: 直接发送文本内容
            raw_body = resolved_mapping.get("rawBody", "")
            request_kwargs["content"] = raw_body
        else:
            # 默认 JSON (raw-json 或旧的 body 字段)
            json_body = resolved_mapping.get("body")
            if json_body is not None:
                request_kwargs["json"] = json_body
            else:
                # 兼容: 如果有 rawBody 且 bodyType 是 raw-json
                # rawBody 可能包含 JSONC 注释 (// 和 /* */)，发送前自动剥离
                raw_body = resolved_mapping.get("rawBody")
                if raw_body:
                    request_kwargs["content"] = _strip_jsonc_comments(raw_body)

    # ── 3. 重试逻辑 ──
    retry_policy = step.retryPolicy or RetryPolicy()
    max_attempts = retry_policy.maxAttempts if retry_policy.enabled else 1
    interval_ms = retry_policy.intervalMs

    last_error: str | None = None
    last_status_code: int | None = None
    last_raw_data: dict[str, Any] | None = None

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
                response = await client.request(method, str(url), **request_kwargs)

            last_status_code = response.status_code

            # ── 4. 构建结构化响应数据 ──
            raw_data: dict[str, Any] = {
                "status": response.status_code,
                "headers": dict(response.headers),
            }
            try:
                raw_data["body"] = response.json()
            except Exception:
                raw_data["body"] = response.text
            last_raw_data = raw_data

            # ── 5. 评估 responseHandling ──
            handling = step.responseHandling
            if handling:
                status_ok = response.status_code in handling.statusCode.success
                biz_ok = True
                if handling.businessSuccess and handling.businessSuccess.allOf:
                    biz_ok = evaluate_all_of(handling.businessSuccess.allOf, raw_data)

                if not status_ok or not biz_ok:
                    error_msg = _build_error_message(step.errorMapping, raw_data)
                    last_error = error_msg

                    # 判断是否可重试
                    if _is_retryable(response, retry_policy) and attempt < max_attempts - 1:
                        await asyncio.sleep(interval_ms / 1000)
                        continue

                    # 不可重试或已用尽重试次数
                    return _fail(step, started_at, error_msg,
                                  status_code=response.status_code,
                                  raw_response=raw_data)

            # ── 6. 提取 outputMapping ──
            outputs = _extract_outputs(step.outputMapping, raw_data)

            # ── 7. 写入上下文并返回成功 ──
            ctx.set_step_output(step.stepId, outputs)
            ctx.set_step_raw(step.stepId, raw_data)

            finished_at = datetime.now(UTC)
            return StepResult(
                stepId=step.stepId,
                stepName=step.stepName,
                type=step.type,
                status="SUCCESS",
                startedAt=started_at,
                finishedAt=finished_at,
                durationMs=_duration_ms(started_at, finished_at),
                outputs=outputs,
                rawResponse=raw_data,
                statusCode=response.status_code,
            )

        except httpx.TimeoutException as exc:
            last_error = f"HTTP 请求超时: {exc}"
            if (RetryErrorType.NETWORK_TIMEOUT in (retry_policy.retryOn or [])
                    and attempt < max_attempts - 1):
                await asyncio.sleep(interval_ms / 1000)
                continue

        except httpx.ConnectError as exc:
            last_error = f"HTTP 连接失败: {exc}"
            if (RetryErrorType.CONNECTION_RESET in (retry_policy.retryOn or [])
                    and attempt < max_attempts - 1):
                await asyncio.sleep(interval_ms / 1000)
                continue

        except httpx.HTTPError as exc:
            last_error = f"HTTP 错误: {exc}"
            break  # 非网络类错误不重试

    return _fail(step, started_at, last_error or "HTTP 执行失败",
                  status_code=last_status_code, raw_response=last_raw_data)


def _extract_outputs(
    output_mapping: dict[str, str],
    raw_data: dict[str, Any],
) -> dict[str, Any]:
    """根据 outputMapping 从响应数据中提取输出变量。"""
    outputs: dict[str, Any] = {}
    for key, jsonpath in output_mapping.items():
        outputs[key] = jsonpath_extract(raw_data, jsonpath)
    return outputs


def _build_error_message(
    error_mapping: ErrorMapping | None,
    raw_data: dict[str, Any],
) -> str:
    """根据 errorMapping 构建人类友好的错误信息。"""
    if error_mapping is None:
        return "HTTP 请求业务失败"

    # 提取错误字段
    error_fields: dict[str, Any] = {}
    for field_name, jsonpath in error_mapping.fields.items():
        error_fields[field_name] = jsonpath_extract(raw_data, jsonpath)

    # 尝试模板替换
    if error_mapping.messageTemplate:
        msg = error_mapping.messageTemplate
        for field_name, value in error_fields.items():
            msg = msg.replace(f"${{error.{field_name}}}", str(value or ""))
        return msg

    # 使用兜底消息
    if error_mapping.fallbackMessage:
        return error_mapping.fallbackMessage

    # 默认
    return f"HTTP 请求业务失败: {error_fields}"


def _is_retryable(response: httpx.Response, retry_policy: RetryPolicy) -> bool:
    """判断当前错误是否在可重试类型列表中。"""
    if not retry_policy.enabled or not retry_policy.retryOn:
        return False

    status = response.status_code
    retry_on = retry_policy.retryOn

    if RetryErrorType.HTTP_5XX in retry_on and 500 <= status < 600:
        return True
    if RetryErrorType.RATE_LIMIT in retry_on and status == 429:
        return True
    return False


def _fail(
    step: StepDefinition,
    started_at: datetime,
    error: str,
    *,
    status_code: int | None = None,
    raw_response: Any = None,
) -> StepResult:
    """构造失败的步骤结果。"""
    finished_at = datetime.now(UTC)
    return StepResult(
        stepId=step.stepId,
        stepName=step.stepName,
        type=step.type,
        status="FAILED",
        startedAt=started_at,
        finishedAt=finished_at,
        durationMs=_duration_ms(started_at, finished_at),
        error=error,
        statusCode=status_code,
        rawResponse=raw_response,
    )


def _duration_ms(started: datetime, finished: datetime) -> int:
    """计算两个时间点之间的毫秒差。"""
    return int((finished - started).total_seconds() * 1000)


import re as _re

_JSONC_LINE_RE = _re.compile(r'//.*$')
_JSONC_BLOCK_RE = _re.compile(r'/\*[\s\S]*?\*/')


def _strip_jsonc_comments(text: str) -> str:
    """剥离 JSONC 注释（// 行注释和 /* 块注释 */），保留 JSON 字符串内的内容。

    采用逐字符状态机方式，在字符串字面量内部不处理注释标记。
    """
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # 字符串字面量: 原样保留直到闭合引号
        if ch == '"':
            j = i + 1
            while j < n:
                if text[j] == '\\':
                    j += 2  # 跳过转义字符
                    continue
                if text[j] == '"':
                    j += 1
                    break
                j += 1
            result.append(text[i:j])
            i = j
            continue

        # 块注释 /* ... */
        if ch == '/' and i + 1 < n and text[i + 1] == '*':
            end = text.find('*/', i + 2)
            i = (end + 2) if end != -1 else n
            continue

        # 行注释 //
        if ch == '/' and i + 1 < n and text[i + 1] == '/':
            # 跳到行尾
            end = text.find('\n', i)
            i = end if end != -1 else n
            continue

        result.append(ch)
        i += 1

    return ''.join(result)
