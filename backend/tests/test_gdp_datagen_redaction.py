"""GDP 造数敏感信息脱敏工具测试。"""

from __future__ import annotations

from app.gdp.datagen.redaction import (
    REDACTED_VALUE,
    redact_sensitive_payload,
    redact_validation_errors,
)


def test_redact_sensitive_payload_masks_credential_keys_recursively():
    payload = {
        "sourceCode": "createOrderApi",
        "password": "secret-123",
        "headers": {"Authorization": "Bearer raw-token", "Accept": "application/json"},
        "datasource": {"jdbcUrl": "jdbc:mysql://u:p@host/db", "username": "app"},
        "items": [{"apiKey": "k-1"}, "plain"],
    }

    redacted = redact_sensitive_payload(payload)

    assert redacted["sourceCode"] == "createOrderApi"
    assert redacted["password"] == REDACTED_VALUE
    assert redacted["headers"]["Authorization"] == REDACTED_VALUE
    assert redacted["headers"]["Accept"] == "application/json"
    assert redacted["datasource"]["jdbcUrl"] == REDACTED_VALUE
    assert redacted["items"][0]["apiKey"] == REDACTED_VALUE
    assert redacted["items"][1] == "plain"


def test_redact_validation_errors_masks_input_for_sensitive_field_errors():
    errors = [
        {
            "type": "string_type",
            "loc": ("config", "password"),
            "msg": "Input should be a valid string",
            "input": 12345,
        }
    ]

    redacted = redact_validation_errors(errors)

    assert redacted[0]["input"] == REDACTED_VALUE
    assert redacted[0]["loc"] == ("config", "password")


def test_redact_validation_errors_recursively_redacts_payload_inputs():
    errors = [
        {
            "type": "missing",
            "loc": ("config", "url"),
            "msg": "Field required",
            "input": {"sourceCode": "api", "password": "secret-123", "token": "t-1"},
        }
    ]

    redacted = redact_validation_errors(errors)

    assert redacted[0]["input"]["sourceCode"] == "api"
    assert redacted[0]["input"]["password"] == REDACTED_VALUE
    assert redacted[0]["input"]["token"] == REDACTED_VALUE


def test_redact_validation_errors_keeps_errors_without_input():
    errors = [{"type": "value_error", "loc": ("infra",), "msg": "至少需要一项基础配置。"}]

    assert redact_validation_errors(errors) == errors
