"""HTTP 执行器核心逻辑单元测试。"""

# ruff: noqa: E402,I001

from __future__ import annotations

import sys
from pathlib import Path

# 确保 deerflow 包可导入（workspace 成员在 packages/harness 下）
_harness = str(Path(__file__).resolve().parents[1] / "packages" / "harness")
if _harness not in sys.path:
    sys.path.insert(0, _harness)

from app.gdp.datagen.config.common.models import ConditionRule, HttpTimeoutConfig
from app.gdp.datagen.config.httpsource.models import (
    HttpSourceConfig,
    HttpSourceTestRequest,
    HttpSourceTestRequestInfo,
    ParsedCookie,
)
from app.gdp.datagen.config.httpsource.executor import (
    _MISSING,
    _build_httpx_timeout,
    _check_condition,
    _friendly_error_message,
    _parse_set_cookie,
    apply_error_mapping,
    build_request_info,
    build_runtime_context,
    evaluate_business_result,
    extract_outputs,
    interpolate_expressions,
    resolve_path,
)


# ── 超时配置 ───────────────────────────────────────────────────────

class TestHttpTimeoutConfig:
    def test_request_uses_default_timeout_config(self):
        request = HttpSourceTestRequest(
            envCode="dev",
            config=HttpSourceConfig(
                sourceCode="test",
                sourceName="test",
                sysCode="SYS",
                path="/test",
                requestMapping={},
                outputMapping={},
            ),
        )

        assert request.config.timeoutConfig.connectTimeoutSeconds == 10
        assert request.config.timeoutConfig.readTimeoutSeconds == 10
        assert request.config.timeoutConfig.writeTimeoutSeconds == 10
        assert request.config.timeoutConfig.poolTimeoutSeconds == 10

    def test_old_timeout_seconds_field_is_rejected(self):
        from pydantic import ValidationError

        try:
            HttpSourceTestRequest(
                envCode="dev",
                timeoutSeconds=20,
                config=HttpSourceConfig(
                    sourceCode="test",
                    sourceName="test",
                    sysCode="SYS",
                    path="/test",
                    requestMapping={},
                    outputMapping={},
                ),
            )
        except ValidationError as exc:
            assert "timeoutSeconds" in str(exc)
        else:
            raise AssertionError("旧 timeoutSeconds 字段应被拒绝")

    def test_build_httpx_timeout_uses_all_timeout_fields(self):
        timeout = _build_httpx_timeout(
            HttpTimeoutConfig(
                connectTimeoutSeconds=2,
                readTimeoutSeconds=15,
                writeTimeoutSeconds=8,
                poolTimeoutSeconds=3,
            )
        )

        assert timeout.connect == 2
        assert timeout.read == 15
        assert timeout.write == 8
        assert timeout.pool == 3

    def test_friendly_timeout_messages_cover_all_timeout_types(self):
        assert "连接服务器超时" in _friendly_error_message("ConnectTimeout", "")
        assert "服务器响应超时" in _friendly_error_message("ReadTimeout", "")
        assert "发送请求数据超时" in _friendly_error_message("WriteTimeout", "")
        assert "连接池可用连接超时" in _friendly_error_message("PoolTimeout", "")


# ── 请求体构造 ─────────────────────────────────────────────────────

class TestBuildRequestBody:
    def _make_config(self, request_mapping):
        from app.gdp.datagen.config.common.models import HttpMethod

        return HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            method=HttpMethod.POST,
            requestMapping=request_mapping,
            outputMapping={},
        )

    def test_raw_json_uses_raw_body(self):
        info = build_request_info(
            "http://mock.local",
            self._make_config(
                {
                    "bodyType": "raw-json",
                    "rawBody": '{"user":{"name":"张三"},"tags":["vip"]}',
                }
            ),
        )

        assert info.bodyType == "raw-json"
        assert info.body == {"user": {"name": "张三"}, "tags": ["vip"]}

    def test_raw_json_can_use_body_tree(self):
        info = build_request_info(
            "http://mock.local",
            self._make_config(
                {
                    "bodyType": "raw-json",
                    "bodyTree": [
                        {"name": "buyer_id", "type": "string", "defaultValue": "U10001"},
                        {"name": "amount", "type": "number", "defaultValue": "99.9"},
                    ],
                }
            ),
        )

        assert info.body == {"buyer_id": "U10001", "amount": 99.9}

    def test_urlencoded_uses_unified_url_encoded_data(self):
        info = build_request_info(
            "http://mock.local",
            self._make_config(
                {
                    "bodyType": "x-www-form-urlencoded",
                    "urlEncodedData": {
                        "grant_type": "password",
                        "username": "demo",
                    },
                }
            ),
        )

        assert info.bodyType == "x-www-form-urlencoded"
        assert info.body == {"grant_type": "password", "username": "demo"}

    def test_form_data_uses_unified_form_data_rows(self):
        info = build_request_info(
            "http://mock.local",
            self._make_config(
                {
                    "bodyType": "form-data",
                    "formData": [
                        {"key": "file", "value": "demo.csv", "enabled": True},
                        {"key": "disabled", "value": "skip", "enabled": False},
                        {"key": "bizType", "value": "ORDER", "enabled": True},
                    ],
                }
            ),
        )

        assert info.bodyType == "form-data"
        assert info.body == {"file": "demo.csv", "bizType": "ORDER"}

    def test_old_body_field_names_are_not_supported(self):
        info = build_request_info(
            "http://mock.local",
            self._make_config(
                {
                    "bodyType": "form-urlencoded",
                    "formFields": {"username": "legacy"},
                }
            ),
        )

        assert info.body is None


# ── Cookie 解析 ─────────────────────────────────────────────────────

class TestParseSetCookie:
    def test_simple_cookie(self):
        raw = "SESSION=abc123; Path=/; HttpOnly"
        cookie = _parse_set_cookie(raw)
        assert cookie is not None
        assert cookie.name == "SESSION"
        assert cookie.value == "abc123"
        assert cookie.path == "/"
        assert cookie.httpOnly is True
        assert cookie.secure is False

    def test_full_cookie(self):
        raw = "token=xyz; Domain=.example.com; Path=/api; Secure; HttpOnly; SameSite=Strict"
        cookie = _parse_set_cookie(raw)
        assert cookie is not None
        assert cookie.name == "token"
        assert cookie.value == "xyz"
        assert cookie.domain == ".example.com"
        assert cookie.path == "/api"
        assert cookie.secure is True
        assert cookie.httpOnly is True
        assert cookie.sameSite == "Strict"

    def test_cookie_with_expires(self):
        raw = "id=42; Expires=Thu, 01 Jan 2026 00:00:00 GMT; Path=/"
        cookie = _parse_set_cookie(raw)
        assert cookie is not None
        assert cookie.expires == "Thu, 01 Jan 2026 00:00:00 GMT"

    def test_empty_string(self):
        assert _parse_set_cookie("") is None

    def test_no_equals(self):
        assert _parse_set_cookie("INVALID") is None

    def test_value_with_equals(self):
        raw = "data=base64==; Path=/"
        cookie = _parse_set_cookie(raw)
        assert cookie is not None
        assert cookie.name == "data"
        assert cookie.value == "base64=="


# ── 路径解析 ────────────────────────────────────────────────────────

class TestResolvePath:
    def test_simple_key(self):
        assert resolve_path({"code": 200}, "code") == 200

    def test_nested_key(self):
        obj = {"data": {"user": {"name": "Alice"}}}
        assert resolve_path(obj, "data.user.name") == "Alice"

    def test_array_index(self):
        obj = {"items": ["a", "b", "c"]}
        assert resolve_path(obj, "items[1]") == "b"

    def test_mixed_path(self):
        obj = {"data": {"items": [{"id": 10}, {"id": 20}]}}
        assert resolve_path(obj, "data.items[0].id") == 10

    def test_missing_key(self):
        assert resolve_path({"a": 1}, "b") is _MISSING

    def test_dollar_prefix(self):
        assert resolve_path({"code": 0}, "$.code") == 0

    def test_empty_path(self):
        assert resolve_path({"a": 1}, "") is _MISSING

    def test_none_body(self):
        assert resolve_path(None, "a.b") is _MISSING


# ── 条件求值 ────────────────────────────────────────────────────────

class TestCheckCondition:
    def test_eq(self):
        rule = ConditionRule(path="code", op="EQ", value=200)
        assert _check_condition({"code": 200}, rule) is True

    def test_eq_string_coercion(self):
        rule = ConditionRule(path="code", op="EQ", value="200")
        assert _check_condition({"code": 200}, rule) is True

    def test_ne(self):
        rule = ConditionRule(path="code", op="NE", value=500)
        assert _check_condition({"code": 200}, rule) is True

    def test_neq(self):
        rule = ConditionRule(path="code", op="NEQ", value=500)
        assert _check_condition({"code": 200}, rule) is True

    def test_gt(self):
        rule = ConditionRule(path="count", op="GT", value=5)
        assert _check_condition({"count": 10}, rule) is True
        assert _check_condition({"count": 3}, rule) is False

    def test_exists(self):
        rule = ConditionRule(path="token", op="EXISTS", value=None)
        assert _check_condition({"token": "abc"}, rule) is True
        assert _check_condition({"other": 1}, rule) is False

    def test_not_exists(self):
        rule = ConditionRule(path="error", op="NOT_EXISTS", value=None)
        assert _check_condition({"data": 1}, rule) is True

    def test_empty(self):
        rule = ConditionRule(path="msg", op="EMPTY", value=None)
        assert _check_condition({"msg": ""}, rule) is True
        assert _check_condition({"msg": "hello"}, rule) is False

    def test_not_empty(self):
        rule = ConditionRule(path="msg", op="NOT_EMPTY", value=None)
        assert _check_condition({"msg": "hello"}, rule) is True

    def test_contains(self):
        rule = ConditionRule(path="msg", op="CONTAINS", value="error")
        assert _check_condition({"msg": "an error occurred"}, rule) is True
        assert _check_condition({"msg": "success"}, rule) is False

    def test_in(self):
        rule = ConditionRule(path="status", op="IN", value=["active", "pending"])
        assert _check_condition({"status": "active"}, rule) is True
        assert _check_condition({"status": "deleted"}, rule) is False

    def test_not_in(self):
        rule = ConditionRule(path="status", op="NOT_IN", value=["deleted"])
        assert _check_condition({"status": "active"}, rule) is True

    def test_regex(self):
        rule = ConditionRule(path="email", op="REGEX", value=r"^[\w.]+@[\w.]+$")
        assert _check_condition({"email": "a@b.com"}, rule) is True
        assert _check_condition({"email": "invalid"}, rule) is False

    def test_missing_field_returns_false(self):
        rule = ConditionRule(path="missing", op="EQ", value=1)
        assert _check_condition({"other": 1}, rule) is False


# ── 业务结果求值 ──────────────────────────────────────────────────

class TestEvaluateBusinessResult:
    def _make_config(self, response_handling):
        return HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
            responseHandling=response_handling,
        )

    def test_no_handling_returns_none(self):
        config = self._make_config(None)
        assert evaluate_business_result(config, 200, {}) is None

    def test_status_not_in_success_list(self):
        from app.gdp.datagen.config.common.models import (
            ResponseConditionGroup,
            ResponseHandling,
            ResponseStatusCodeRule,
        )
        handling = ResponseHandling(
            statusCode=ResponseStatusCodeRule(success=[200]),
            businessSuccess=ResponseConditionGroup(allOf=[]),
            businessFailure=ResponseConditionGroup(anyOf=[]),
        )
        config = self._make_config(handling)
        result = evaluate_business_result(config, 500, {})
        assert result is not None
        assert result.isSuccess is False
        assert "500" in result.reason

    def test_all_success_rules_match(self):
        from app.gdp.datagen.config.common.models import (
            ConditionRule,
            ResponseConditionGroup,
            ResponseHandling,
            ResponseStatusCodeRule,
        )
        handling = ResponseHandling(
            statusCode=ResponseStatusCodeRule(success=[200]),
            businessSuccess=ResponseConditionGroup(
                allOf=[
                    ConditionRule(path="${RES_BODY(code)}", op="EQ", value=0),
                    ConditionRule(path="${RES_BODY(msg)}", op="EQ", value="ok"),
                ]
            ),
            businessFailure=ResponseConditionGroup(anyOf=[]),
        )
        config = self._make_config(handling)
        body = {"code": 0, "msg": "ok"}
        context = build_runtime_context(config, None, body, {}, [])
        result = evaluate_business_result(config, 200, body, context=context)
        assert result is not None
        assert result.isSuccess is True

    def test_legacy_body_path_is_not_supported(self):
        from app.gdp.datagen.config.common.models import (
            ConditionRule,
            ResponseConditionGroup,
            ResponseHandling,
            ResponseStatusCodeRule,
        )
        handling = ResponseHandling(
            statusCode=ResponseStatusCodeRule(success=[200]),
            businessSuccess=ResponseConditionGroup(
                allOf=[ConditionRule(path="$.body.code", op="EQ", value=0)]
            ),
            businessFailure=ResponseConditionGroup(anyOf=[]),
        )
        config = self._make_config(handling)
        context = build_runtime_context(config, None, {"code": 0}, {}, [])
        result = evaluate_business_result(config, 200, {"code": 0}, context=context)
        assert result is not None
        assert result.isSuccess is False

    def test_identifier_success_rule_matches_response_body(self):
        from app.gdp.datagen.config.common.models import (
            ConditionRule,
            ResponseConditionGroup,
            ResponseHandling,
            ResponseStatusCodeRule,
        )
        handling = ResponseHandling(
            statusCode=ResponseStatusCodeRule(success=[200]),
            businessSuccess=ResponseConditionGroup(
                allOf=[ConditionRule(path="${RES_BODY(code)}", op="EQ", value=0)]
            ),
            businessFailure=ResponseConditionGroup(anyOf=[]),
        )
        config = self._make_config(handling)
        context = build_runtime_context(config, None, {"code": 0}, {}, [])
        result = evaluate_business_result(config, 200, {"code": 0}, context=context)
        assert result is not None
        assert result.isSuccess is True

    def test_failure_rule_triggers(self):
        from app.gdp.datagen.config.common.models import (
            ConditionRule,
            ResponseConditionGroup,
            ResponseHandling,
            ResponseStatusCodeRule,
        )
        handling = ResponseHandling(
            statusCode=ResponseStatusCodeRule(success=[200]),
            businessSuccess=ResponseConditionGroup(allOf=[]),
            businessFailure=ResponseConditionGroup(
                anyOf=[ConditionRule(path="${RES_BODY(error)}", op="NOT_EMPTY", value=None)]
            ),
        )
        config = self._make_config(handling)
        body = {"error": "timeout"}
        context = build_runtime_context(config, None, body, {}, [])
        result = evaluate_business_result(config, 200, body, context=context)
        assert result is not None
        assert result.isSuccess is False


# ── 输出变量提取 ──────────────────────────────────────────────────

class TestExtractOutputs:
    def test_basic_extraction(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={"token": "${RES_BODY(data.token)}", "trace": "${RES_HEADER(x-trace-id)}"},
        )
        body = {"data": {"token": "abc123"}}
        headers = {"x-trace-id": "trace-456"}
        result = extract_outputs(config, body, headers, [])
        assert result["token"] == "abc123"
        assert result["trace"] == "trace-456"

    def test_identifier_extraction_and_header_case_insensitive(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={
                "token": "${RES_BODY(data.token)}",
                "trace": "${RES_HEADER(X-Trace-Id)}",
            },
        )
        body = {"data": {"token": "abc123"}}
        headers = {"x-trace-id": "trace-456"}
        result = extract_outputs(config, body, headers, [])
        assert result["token"] == "abc123"
        assert result["trace"] == "trace-456"

    def test_request_identifier_extraction(self):
        request_info = HttpSourceTestRequestInfo(
            url="http://example.test",
            method="POST",
            headers={"X-Request-Id": "req-1"},
            body={"code": "A001"},
        )
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={"authConfig": {"type": "bearer", "token": "secret"}},
            outputMapping={
                "requestCode": "${REQ_BODY(code)}",
                "requestId": "${REQ_HEADER(x-request-id)}",
                "authType": "${REQ_AUTH(type)}",
            },
        )
        result = extract_outputs(config, {}, {}, [], request_info=request_info)
        assert result["requestCode"] == "A001"
        assert result["requestId"] == "req-1"
        assert result["authType"] == "bearer"

    def test_cookie_extraction(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={"session": "${RES_COOKIE(SESSION)}"},
        )
        cookies = [ParsedCookie(name="SESSION", value="sess_789")]
        result = extract_outputs(config, {}, {}, cookies)
        assert result["session"] == "sess_789"

    def test_legacy_output_paths_are_not_supported(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={"token": "body.data.token", "trace": "$.headers.X-Trace-Id"},
        )
        result = extract_outputs(config, {"data": {"token": "abc123"}}, {"x-trace-id": "trace-456"}, [])
        assert result["token"] is None
        assert result["trace"] is None

    def test_missing_path_returns_none(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={"missing": "${RES_BODY(nonexistent)}"},
        )
        result = extract_outputs(config, {"data": 1}, {}, [])
        assert result["missing"] is None

    def test_empty_mapping(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
        )
        assert extract_outputs(config, {}, {}, []) == {}


# ── 错误映射 ─────────────────────────────────────────────────────

class TestApplyErrorMapping:
    def test_template_formatting(self):
        from app.gdp.datagen.config.common.models import ErrorMapping
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
            errorMapping=ErrorMapping(
                messageTemplate="错误码: {code}, 消息: {msg}",
                fields={"code": "${RES_BODY(error.code)}", "msg": "${RES_BODY(error.message)}"},
            ),
        )
        body = {"error": {"code": "E001", "message": "参数无效"}}
        result = apply_error_mapping(config, body, "raw error")
        assert "E001" in result
        assert "参数无效" in result

    def test_fallback_message(self):
        from app.gdp.datagen.config.common.models import ErrorMapping
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
            errorMapping=ErrorMapping(
                fallbackMessage="未知错误",
                fields={},
            ),
        )
        result = apply_error_mapping(config, None, "raw")
        assert result == "未知错误"

    def test_no_mapping_returns_raw(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
        )
        assert apply_error_mapping(config, None, "raw error") == "raw error"

    def test_expose_raw_response(self):
        from app.gdp.datagen.config.common.models import ErrorMapping
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
            errorMapping=ErrorMapping(
                fallbackMessage="失败",
                fields={},
                exposeRawResponse=True,
            ),
        )
        body = {"detail": "bad request"}
        result = apply_error_mapping(config, body, "raw")
        assert "原始响应" in result

    def test_identifier_template_interpolation(self):
        config = HttpSourceConfig(
            sourceCode="test",
            sourceName="test",
            sysCode="SYS",
            path="/test",
            requestMapping={},
            outputMapping={},
        )
        context = build_runtime_context(config, None, {"message": "参数无效"}, {"x-trace-id": "t1"}, [])
        result = interpolate_expressions("失败: ${RES_BODY(message)}, trace=${RES_HEADER(X-Trace-Id)}", context)
        assert result == "失败: 参数无效, trace=t1"
