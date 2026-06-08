"""HTTP 执行器：负责请求构造、HTTP 发送（含重试）、响应解析、条件求值和输出提取。"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import traceback
from time import perf_counter
from typing import Any
from urllib.parse import urljoin

import httpx

# 创建模块日志记录器
logger = logging.getLogger(__name__)

from app.gdp.datagen.config.common.models import ConditionRule, ErrorMapping
from app.gdp.datagen.config.httpsource.models import (
    BusinessResult,
    HttpSourceConfig,
    HttpSourceTestErrorInfo,
    HttpSourceTestRequestInfo,
    HttpSourceTestResponse,
    HttpSourceTestResponseInfo,
    ParsedCookie,
    RetryInfo,
)

# 路径解析时标记缺失值
_MISSING = object()

_EXTRACTOR_RE = re.compile(r"^\$\{(?P<source>[A-Z_]+)\((?P<path>.*)\)\}$")
_EXTRACTOR_TOKEN_RE = re.compile(r"\$\{(?P<source>[A-Z_]+)\((?P<path>.*?)\)\}")
_REQUEST_BODY = "REQ_BODY"
_REQUEST_HEADER = "REQ_HEADER"
_REQUEST_AUTH = "REQ_AUTH"
_RESPONSE_BODY = "RES_BODY"
_RESPONSE_HEADER = "RES_HEADER"
_RESPONSE_COOKIE = "RES_COOKIE"


# ── 公开入口 ─────────────────────────────────────────────────────────

async def execute_http_test(
    config: HttpSourceConfig,
    base_url: str,
    timeout: float,
) -> HttpSourceTestResponse:
    """执行一次完整的 HTTP 接口配置测试。

    Args:
        config: HTTP 接口配置。
        base_url: 已解析的环境 Base URL。
        timeout: 请求超时秒数。

    Returns:
        完整的测试结果响应。
    """
    logger.info("=" * 60)
    logger.info("【HTTP 执行器】开始执行 HTTP 接口配置测试")
    logger.info("接口编码: %s", config.sourceCode)
    logger.info("接口名称: %s", config.sourceName)

    # 1. 构造请求信息
    request_info = build_request_info(base_url, config)
    logger.info("-" * 40)
    logger.info("【请求信息】")
    logger.info("请求方式: %s", request_info.method)
    logger.info("请求 URL: %s", request_info.url)
    logger.info("请求头: %s", json.dumps(request_info.headers, ensure_ascii=False, indent=2) if request_info.headers else "无")
    logger.info("查询参数: %s", json.dumps(request_info.query, ensure_ascii=False, indent=2) if request_info.query else "无")
    logger.info("请求体类型: %s", request_info.bodyType)
    if request_info.body is not None:
        body_str = json.dumps(request_info.body, ensure_ascii=False, indent=2) if isinstance(request_info.body, (dict, list)) else str(request_info.body)
        logger.info("请求体内容:\n%s", body_str)
    else:
        logger.info("请求体内容: 无")
    logger.info("超时时间: %s 秒", timeout)
    logger.info("-" * 40)

    # 2. 执行请求（含重试）
    started = perf_counter()
    response, retry_info, send_error = await _execute_with_retry(
        request_info, config, timeout
    )
    elapsed_ms = round((perf_counter() - started) * 1000, 3)

    # 3. 异常处理
    if send_error is not None:
        # 服务端记录完整堆栈用于排查
        logger.error("【HTTP 请求失败】发生异常")
        logger.error("异常类型: %s", type(send_error).__name__)
        logger.error("异常信息: %s", str(send_error))
        logger.error("完整堆栈:\n%s", "".join(traceback.format_exception(type(send_error), send_error, send_error.__traceback__)))

        # 前端只返回友好的错误信息，不暴露内部堆栈和源代码路径
        error_msg = str(send_error)
        if config.errorMapping:
            context = build_runtime_context(config, request_info, None, {}, [])
            error_msg = apply_error_mapping(config, None, error_msg, context=context)

        # 根据异常类型生成友好的用户提示
        friendly_message = _friendly_error_message(type(send_error).__name__, str(send_error))

        logger.info("=" * 60)
        return HttpSourceTestResponse(
            success=False,
            request=request_info,
            response=HttpSourceTestResponseInfo(elapsedMs=elapsed_ms),
            retryInfo=retry_info if retry_info.attempts > 1 else None,
            error=HttpSourceTestErrorInfo(
                type=type(send_error).__name__,
                message=error_msg,
                detail=friendly_message,
            ),
        )

    # 4. 解析响应
    assert response is not None
    logger.info("【响应信息】")
    logger.info("HTTP 状态码: %d", response.status_code)
    logger.info("响应头: %s", json.dumps(dict(response.headers), ensure_ascii=False, indent=2))
    body = response_body(response)
    cookies = parse_response_cookies(response)
    headers_dict = dict(response.headers)
    logger.info("解析到的 Cookie 数量: %d", len(cookies))
    if isinstance(body, (dict, list)):
        logger.info("响应体 (JSON):\n%s", json.dumps(body, ensure_ascii=False, indent=2))
    else:
        logger.info("响应体 (文本): %s", str(body)[:500] if body else "空")
    logger.info("执行耗时: %.3f 毫秒", elapsed_ms)
    logger.info("-" * 40)

    context = build_runtime_context(config, request_info, body, headers_dict, cookies)

    # 5. 求值业务结果
    business_result = evaluate_business_result(config, response.status_code, body, context=context)
    if business_result:
        logger.info("【业务结果判定】")
        logger.info("是否成功: %s", "成功" if business_result.isSuccess else "失败")
        logger.info("原因: %s", business_result.reason)
        if business_result.matchedRules:
            logger.info("匹配规则: %s", business_result.matchedRules)

    # 6. 提取输出变量
    extracted = extract_outputs(config, body, headers_dict, cookies, request_info=request_info)
    if extracted:
        logger.info("【输出变量提取】")
        for var_name, var_value in extracted.items():
            logger.info("  %s = %s", var_name, var_value)

    error_info = None
    if business_result is not None and not business_result.isSuccess:
        error_msg = apply_error_mapping(
            config,
            body,
            business_result.reason,
            mapping=config.businessErrorMapping,
            context=context,
        )
        error_info = HttpSourceTestErrorInfo(
            type="BusinessError",
            message=error_msg,
            detail=business_result.reason,
        )

    final_success = business_result.isSuccess if business_result else True
    logger.info("=" * 60)
    logger.info("【HTTP 执行器】测试完成，最终结果: %s", "成功" if final_success else "失败")
    logger.info("=" * 60)

    return HttpSourceTestResponse(
        success=final_success,
        request=request_info,
        response=HttpSourceTestResponseInfo(
            statusCode=response.status_code,
            headers=headers_dict,
            body=body,
            cookies=cookies,
            elapsedMs=elapsed_ms,
        ),
        businessResult=business_result,
        extractedOutputs=extracted,
        retryInfo=retry_info if retry_info.attempts > 1 else None,
        error=error_info,
    )


# ── 请求构造 ─────────────────────────────────────────────────────────

def build_request_info(base_url: str, config: HttpSourceConfig) -> HttpSourceTestRequestInfo:
    mapping = config.requestMapping or {}
    query = _string_map(mapping.get("query"))
    headers = _string_map(mapping.get("headers"))
    auth = mapping.get("authConfig") if isinstance(mapping.get("authConfig"), dict) else {"type": "none"}
    _apply_auth(headers, query, auth)

    body_type = str(mapping.get("bodyType") or "none")
    body = None if config.method == "GET" else _request_body(mapping, body_type)
    url = _join_url(base_url, config.path)
    if query:
        url = str(httpx.URL(url).copy_merge_params(query))
    return HttpSourceTestRequestInfo(
        url=url,
        method=config.method.value,
        headers=headers,
        query=query,
        body=body,
        bodyType=body_type,
    )


def _join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): "" if val is None else str(val) for key, val in value.items()}


def _apply_auth(headers: dict[str, str], query: dict[str, str], auth: object) -> None:
    if not isinstance(auth, dict):
        return
    auth_type = auth.get("type")
    if auth_type == "bearer" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif auth_type == "basic" and auth.get("username"):
        username = str(auth.get("username"))
        password = str(auth.get("password") or "")
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"
    elif auth_type == "apikey" and auth.get("key"):
        key = str(auth["key"])
        value = "" if auth.get("value") is None else str(auth.get("value"))
        if auth.get("addTo") == "query":
            query[key] = value
        else:
            headers[key] = value


def _request_body(mapping: dict[str, object], body_type: str) -> object:
    if body_type == "raw-json":
        raw_body = mapping.get("rawBody")
        if isinstance(raw_body, str) and raw_body.strip():
            try:
                return json.loads(raw_body)
            except json.JSONDecodeError:
                return raw_body
        return _tree_to_object(mapping.get("bodyTree"))
    if body_type in {"raw-text", "raw-xml"}:
        return mapping.get("rawBody") or ""
    if body_type == "form-data":
        rows = mapping.get("formData")
        if not isinstance(rows, list):
            return {}
        return {
            str(row.get("key")): "" if row.get("value") is None else str(row.get("value"))
            for row in rows
            if isinstance(row, dict) and row.get("enabled", True) and row.get("key")
        }
    if body_type == "x-www-form-urlencoded":
        return _string_map(mapping.get("urlEncodedData"))
    return None


def _tree_to_object(value: object) -> object:
    if not isinstance(value, list):
        return {}
    result: dict[str, object] = {}
    for item in value:
        if isinstance(item, dict) and item.get("name"):
            result[str(item["name"])] = _tree_value(item)
    return result


def _tree_value(field: dict[str, object]) -> object:
    field_type = field.get("type")
    children = field.get("children")
    default = field.get("defaultValue")
    if field_type == "object":
        return _tree_to_object(children)
    if field_type == "array":
        if isinstance(children, list) and children:
            return [_tree_value(children[0])]
        return []
    if field_type == "number":
        try:
            text = str(default)
            return int(text) if text.isdigit() else float(text)
        except (TypeError, ValueError):
            return default
    if field_type == "boolean":
        if isinstance(default, bool):
            return default
        return str(default).lower() == "true"
    return default


def _request_content(request_info: HttpSourceTestRequestInfo) -> bytes | str | None:
    if request_info.method == "GET":
        return None
    if request_info.bodyType == "raw-json":
        if isinstance(request_info.body, str):
            return request_info.body
        return json.dumps(request_info.body, ensure_ascii=False).encode("utf-8")
    if request_info.bodyType in {"raw-text", "raw-xml"}:
        return "" if request_info.body is None else str(request_info.body)
    return None


def _request_form_data(request_info: HttpSourceTestRequestInfo) -> dict[str, str] | None:
    if request_info.bodyType == "x-www-form-urlencoded" and isinstance(request_info.body, dict):
        return {str(key): "" if value is None else str(value) for key, value in request_info.body.items()}
    return None


def _request_files(request_info: HttpSourceTestRequestInfo) -> dict[str, tuple[None, str]] | None:
    if request_info.bodyType == "form-data" and isinstance(request_info.body, dict):
        return {
            str(key): (None, "" if value is None else str(value))
            for key, value in request_info.body.items()
        }
    return None


def response_body(response: httpx.Response) -> object:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return response.json()
        except ValueError:
            pass
    return response.text


# ── 重试逻辑 ─────────────────────────────────────────────────────────

async def _execute_with_retry(
    request_info: HttpSourceTestRequestInfo,
    config: HttpSourceConfig,
    timeout: float,
) -> tuple[httpx.Response | None, RetryInfo, Exception | None]:
    """执行 HTTP 请求，根据重试策略处理失败。

    Returns:
        (response, retry_info, error) — 成功时 error 为 None，失败时 response 为 None。
    """
    retry_policy = config.retryPolicy
    max_attempts = 1
    interval_ms = 0
    retry_on: set[str] = set()

    if retry_policy and retry_policy.enabled:
        max_attempts = retry_policy.maxAttempts
        interval_ms = retry_policy.intervalMs
        retry_on = {e.value for e in retry_policy.retryOn}
        logger.info("【重试策略】已启用，最大尝试次数: %d, 重试间隔: %d 毫秒, 重试条件: %s",
                    max_attempts, interval_ms, retry_on)

    last_error: str | None = None
    response: httpx.Response | None = None

    for attempt in range(1, max_attempts + 1):
        logger.info("【HTTP 请求】第 %d/%d 次尝试发送...", attempt, max_attempts)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.request(
                    request_info.method,
                    request_info.url,
                    headers=request_info.headers,
                    content=_request_content(request_info),
                    data=_request_form_data(request_info),
                    files=_request_files(request_info),
                )

            logger.info("【HTTP 响应】收到响应，状态码: %d", response.status_code)

            # 检查是否需要因 HTTP 状态码重试
            error_type = _classify_response_status(response.status_code)
            if error_type and error_type in retry_on and attempt < max_attempts:
                last_error = f"HTTP {response.status_code}"
                logger.warning("【HTTP 重试】状态码 %d 触发重试条件 %s，将在 %d 毫秒后重试",
                               response.status_code, error_type, interval_ms)
                response = None
                await asyncio.sleep(interval_ms / 1000)
                continue

            return response, RetryInfo(attempts=attempt, lastError=last_error), None

        except httpx.TimeoutException as exc:
            last_error = str(exc)
            logger.error("【HTTP 请求超时】%s", last_error)
            if "NETWORK_TIMEOUT" not in retry_on or attempt >= max_attempts:
                return None, RetryInfo(attempts=attempt, lastError=last_error), exc
            logger.info("【HTTP 重试】超时触发重试，将在 %d 毫秒后重试", interval_ms)
            await asyncio.sleep(interval_ms / 1000)

        except httpx.ConnectError as exc:
            last_error = str(exc)
            logger.error("【HTTP 连接失败】%s", last_error)
            if "CONNECTION_RESET" not in retry_on or attempt >= max_attempts:
                return None, RetryInfo(attempts=attempt, lastError=last_error), exc
            logger.info("【HTTP 重试】连接失败触发重试，将在 %d 毫秒后重试", interval_ms)
            await asyncio.sleep(interval_ms / 1000)

        except Exception as exc:
            last_error = str(exc)
            logger.error("【HTTP 请求异常】%s: %s", type(exc).__name__, last_error)
            return None, RetryInfo(attempts=attempt, lastError=last_error), exc

    # 理论上不会到这里
    logger.error("【HTTP 请求】所有重试尝试均已失败")
    return None, RetryInfo(attempts=max_attempts, lastError=last_error), Exception(last_error or "unknown error")


def _friendly_error_message(error_type: str, raw_message: str) -> str:
    """根据异常类型生成面向用户的友好中文提示。

    不暴露内部堆栈、源代码路径或第三方库实现细节。
    """
    if error_type == "ConnectError":
        return "无法连接到目标服务器，请检查服务器地址、端口是否正确，以及目标服务是否正常运行。"
    if error_type == "ConnectTimeout":
        return "连接服务器超时，请检查网络连通性或适当增加超时时间。"
    if error_type == "ReadTimeout":
        return "服务器响应超时，目标接口处理时间过长，请适当增加超时时间。"
    if error_type == "WriteError":
        return "发送请求数据时发生网络错误，请检查网络连接。"
    if error_type == "TimeoutException":
        return "请求超时，请检查目标服务状态或适当增加超时时间。"
    if error_type == "NetworkError":
        return "网络异常，请检查网络连接和目标服务是否可用。"
    if error_type == "RemoteProtocolError":
        return "服务器协议异常，目标服务返回了不合规的响应，请检查目标服务状态。"
    if error_type == "DNSLookupFailed":
        return "域名解析失败，请检查服务器地址是否正确。"
    if error_type == "SSLZeroReturnError" or error_type == "SSLError":
        return "SSL/TLS 握手失败，请检查目标服务的证书配置。"
    # 兜底：只返回原始消息，不包含堆栈
    return raw_message or "请求执行过程中发生未知错误。"


def _classify_response_status(status_code: int) -> str | None:
    """根据 HTTP 状态码分类为可重试的错误类型。"""
    if status_code == 429:
        return "RATE_LIMIT"
    if status_code >= 500:
        return "HTTP_5XX"
    return None


# ── Cookie 解析 ──────────────────────────────────────────────────────

def parse_response_cookies(response: httpx.Response) -> list[ParsedCookie]:
    """从 HTTP 响应中解析所有 Cookie。"""
    cookies: list[ParsedCookie] = []
    seen: set[str] = set()

    # 优先从 Set-Cookie 头解析（信息最完整）
    try:
        raw_cookies = response.headers.get_list("set-cookie")
    except AttributeError:
        # httpx 版本兼容：部分版本无 get_list
        raw_cookies = []
        sc = response.headers.get("set-cookie")
        if sc:
            raw_cookies = [sc]

    for raw in raw_cookies:
        cookie = _parse_set_cookie(raw)
        if cookie:
            seen.add(cookie.name)
            cookies.append(cookie)

    # 兜底：从 httpx cookies jar 补入遗漏的
    for name, value in response.cookies.items():
        if name not in seen:
            cookies.append(ParsedCookie(
                name=name,
                value=value,
                raw=f"{name}={value}",
            ))

    return cookies


def _parse_set_cookie(raw: str) -> ParsedCookie | None:
    """解析单条 Set-Cookie 头。"""
    parts = [p.strip() for p in raw.split(";")]
    if not parts:
        return None

    # 第一段是 name=value
    eq_idx = parts[0].find("=")
    if eq_idx < 0:
        return None
    name = parts[0][:eq_idx].strip()
    value = parts[0][eq_idx + 1:].strip()

    # 解析属性
    attrs: dict[str, str | bool] = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            attrs[k.strip().lower()] = v.strip()
        else:
            attrs[part.strip().lower()] = True

    return ParsedCookie(
        name=name,
        value=value,
        domain=attrs.get("domain") if isinstance(attrs.get("domain"), str) else None,
        path=attrs.get("path", "/") if isinstance(attrs.get("path"), str) else "/",
        expires=attrs.get("expires") if isinstance(attrs.get("expires"), str) else None,
        httpOnly="httponly" in attrs,
        secure="secure" in attrs,
        sameSite=attrs.get("samesite") if isinstance(attrs.get("samesite"), str) else None,
        raw=raw,
    )


# ── 表达式上下文 ────────────────────────────────────────────────────

def build_runtime_context(
    config: HttpSourceConfig,
    request_info: HttpSourceTestRequestInfo | None,
    response_body_value: Any,
    response_headers: dict[str, str],
    response_cookies: list[ParsedCookie],
) -> dict[str, Any]:
    """构建 ${REQ_*()} / ${RES_*()} 表达式可访问的数据上下文。"""
    request_mapping = config.requestMapping or {}
    auth_config = request_mapping.get("authConfig")
    cookie_dict = {c.name: c.value for c in response_cookies}

    return {
        _REQUEST_BODY: request_info.body if request_info is not None else None,
        _REQUEST_HEADER: request_info.headers if request_info is not None else {},
        _REQUEST_AUTH: auth_config if isinstance(auth_config, dict) else {},
        _RESPONSE_BODY: response_body_value,
        _RESPONSE_HEADER: response_headers,
        _RESPONSE_COOKIE: cookie_dict,
    }


def resolve_expression(
    context: dict[str, Any],
    expression: str,
) -> Any:
    """解析 ${REQ_*()} / ${RES_*()} 标识符表达式。"""
    match = _EXTRACTOR_RE.match((expression or "").strip())
    if not match:
        return _MISSING

    source = match.group("source")
    path = match.group("path").strip()
    current = context.get(source)
    return resolve_path(
        current,
        path,
        case_insensitive=is_header_source(source),
    )


def interpolate_expressions(template: str, context: dict[str, Any]) -> str:
    """替换模板中的 ${REQ_*()} / ${RES_*()} 标识符。"""
    def replace(match: re.Match[str]) -> str:
        value = resolve_expression(context, match.group(0))
        return "" if value is _MISSING else str(value)

    return _EXTRACTOR_TOKEN_RE.sub(replace, template)


def _clean_path(path: str) -> str:
    return path.lstrip("$").lstrip(".")


def is_header_source(source: str) -> bool:
    return source in {_REQUEST_HEADER, _RESPONSE_HEADER}


# ── 条件求值引擎 ────────────────────────────────────────────────────

def evaluate_business_result(
    config: HttpSourceConfig,
    status_code: int,
    body: Any,
    *,
    context: dict[str, Any] | None = None,
) -> BusinessResult | None:
    """根据配置的响应处理规则求值业务结果。"""
    handling = config.responseHandling
    if handling is None:
        return None

    # 检查 HTTP 状态码
    success_codes = handling.statusCode.success or [200]
    if status_code not in success_codes:
        return BusinessResult(
            isSuccess=False,
            reason=f"HTTP 状态码 {status_code} 不在成功列表 {success_codes} 中",
        )

    matched: list[str] = []

    # 求值失败规则（OR，短路）
    failure_rules = handling.businessFailure.anyOf or []
    for rule in failure_rules:
        if _check_condition(body, rule, context=context):
            return BusinessResult(
                isSuccess=False,
                reason=f"命中失败规则: {rule.path} {rule.op} {rule.value}",
                matchedRules=[f"{rule.path} {rule.op} {rule.value}"],
            )

    # 求值成功规则（AND）
    success_rules = handling.businessSuccess.allOf or []
    if not success_rules:
        return BusinessResult(
            isSuccess=True,
            reason="HTTP 状态码在成功列表中，无额外成功条件",
        )

    for rule in success_rules:
        if _check_condition(body, rule, context=context):
            matched.append(f"{rule.path} {rule.op} {rule.value}")
        else:
            return BusinessResult(
                isSuccess=False,
                reason=f"成功条件未满足: {rule.path} {rule.op} {rule.value}",
                matchedRules=matched,
            )

    return BusinessResult(
        isSuccess=True,
        reason="所有成功条件均已满足",
        matchedRules=matched,
    )


def _check_condition(body: Any, rule: ConditionRule, *, context: dict[str, Any] | None = None) -> bool:
    """对单条条件规则求值。"""
    if context is not None:
        value = resolve_expression(context, rule.path)
    else:
        value = resolve_path(body, rule.path)
    target = rule.value
    op = rule.op.upper()

    if op == "EXISTS":
        return value is not _MISSING
    if op == "NOT_EXISTS":
        return value is _MISSING
    if op == "EMPTY":
        return value is _MISSING or value == "" or value == [] or value == {} or value is None
    if op == "NOT_EMPTY":
        return value is not _MISSING and value != "" and value != [] and value != {} and value is not None
    if value is _MISSING:
        return False

    if op == "EQ":
        return _loose_eq(value, target)
    if op in ("NE", "NEQ"):
        return not _loose_eq(value, target)
    if op in ("GT", "GTE", "LT", "LTE"):
        try:
            a, b = float(value), float(target)  # type: ignore[arg-type]
            return {"GT": a > b, "GTE": a >= b, "LT": a < b, "LTE": a <= b}[op]
        except (ValueError, TypeError):
            return False
    if op == "CONTAINS":
        return str(target) in str(value)
    if op == "IN":
        if isinstance(target, list):
            return value in target or str(value) in [str(x) for x in target]
        return False
    if op == "NOT_IN":
        if isinstance(target, list):
            return value not in target and str(value) not in [str(x) for x in target]
        return True
    if op == "REGEX":
        try:
            return bool(re.search(str(target), str(value)))
        except re.error:
            return False
    return False


def _loose_eq(actual: Any, expected: Any) -> bool:
    """宽松相等比较：类型不同时尝试字符串比较。"""
    if actual == expected:
        return True
    return str(actual) == str(expected)


def resolve_path(obj: Any, path: str, *, case_insensitive: bool = False) -> Any:
    """按点分路径从 dict/list 中提取值。

    支持格式: ``data.code``, ``data.items[0].id``。
    """
    if not path:
        return _MISSING

    # 去除开头的 $. 前缀
    cleaned = _clean_path(path)
    parts = re.split(r"\.|\[|\]", cleaned)

    current = obj
    for part in parts:
        if not part:
            continue
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            elif case_insensitive:
                matched = next((k for k in current if str(k).lower() == part.lower()), None)
                if matched is None:
                    return _MISSING
                current = current[matched]
            else:
                return _MISSING
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


# ── 输出变量提取 ────────────────────────────────────────────────────

def extract_outputs(
    config: HttpSourceConfig,
    body: Any,
    headers: dict[str, str],
    cookies: list[ParsedCookie],
    *,
    request_info: HttpSourceTestRequestInfo | None = None,
) -> dict[str, Any]:
    """根据 outputMapping 从响应中提取输出变量。"""
    if not config.outputMapping:
        return {}

    context = build_runtime_context(config, request_info, body, headers, cookies)

    result: dict[str, Any] = {}
    for var_name, path in config.outputMapping.items():
        value = resolve_expression(context, path)
        result[var_name] = None if value is _MISSING else value
    return result


# ── 错误映射 ────────────────────────────────────────────────────────

def apply_error_mapping(
    config: HttpSourceConfig,
    body: Any,
    raw_error: str,
    *,
    mapping: ErrorMapping | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """根据错误映射配置生成人类可读的错误信息。"""
    em = mapping if mapping is not None else config.errorMapping
    if em is None:
        return raw_error

    if context is None:
        context = build_runtime_context(config, None, body, {}, [])

    # 提取字段
    extracted: dict[str, str] = {}
    for var_name, path in em.fields.items():
        value = resolve_expression(context, path)
        extracted[var_name] = "" if value is _MISSING else str(value)

    # 应用模板
    message = ""
    if em.messageTemplate:
        try:
            message = interpolate_expressions(em.messageTemplate, context).format_map(extracted)
        except (KeyError, ValueError):
            message = ""

    # 兜底消息
    if not message:
        message = em.fallbackMessage or raw_error

    # 追加原始响应
    if em.exposeRawResponse and body is not None:
        raw_text = json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else str(body)
        message = f"{message}\n原始响应: {raw_text}"

    return message
