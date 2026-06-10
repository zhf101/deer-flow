"""GDP 造数敏感信息脱敏工具。"""

from __future__ import annotations

from typing import Any

REDACTED_VALUE = "***已脱敏***"

_SENSITIVE_EXACT_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "api-token",
    "client_secret",
    "secret_key",
    "private_key",
    "connection_string",
    "connectionstring",
    "jdbc_url",
    "jdbcurl",
    "dsn",
}

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "access-token",
    "refresh-token",
    "api-key",
    "secret",
    "password",
    "passwd",
    "token",
    "credential",
    "privatekey",
    "private-key",
    "connectionstring",
    "connection-string",
)


def redact_sensitive_payload(value: Any) -> Any:
    """递归脱敏 payload 中常见凭据字段，保留原结构供前端定位问题。"""

    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = redact_sensitive_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_payload(item) for item in value]
    return value


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace(" ", "_")
    compact = normalized.replace("_", "").replace("-", "")
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    return any(part in normalized or part in compact for part in _SENSITIVE_KEY_PARTS)
