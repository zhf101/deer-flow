from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.gdp.datagen.config.scene.models import (
    AssertStepDefinition,
    HttpStepDefinition,
    SceneDefinition,
    SqlStepDefinition,
    TransformStepDefinition,
    parse_step_definition_payload,
)


def _base_payload(step_type: str) -> dict:
    return {
        "stepId": f"{step_type.lower()}_1",
        "stepName": f"{step_type} 步骤",
        "type": step_type,
        "enabled": True,
        "dependsOn": [],
        "outputMapping": {},
    }


def test_http_step_parses_to_http_subclass():
    step = parse_step_definition_payload(
        {
            **_base_payload("HTTP"),
            "method": "POST",
            "path": "/orders",
            "sysCode": "TRADE",
            "requestMapping": {},
            "httpParamMapping": {},
        }
    )

    assert isinstance(step, HttpStepDefinition)
    assert step.path == "/orders"


def test_sql_step_parses_to_sql_subclass():
    step = parse_step_definition_payload(
        {
            **_base_payload("SQL"),
            "sysCode": "TRADE",
            "datasourceCode": "tradeDb",
            "operation": "SELECT",
            "sqlText": "select 1",
            "paramMapping": {},
        }
    )

    assert isinstance(step, SqlStepDefinition)
    assert step.sysCode == "TRADE"


def test_assert_step_parses_to_assert_subclass():
    step = parse_step_definition_payload(
        {
            **_base_payload("ASSERT"),
            "assertions": [{"expression": "", "message": ""}],
        }
    )

    assert isinstance(step, AssertStepDefinition)
    assert step.assertions[0].expression == ""


def test_transform_step_parses_to_transform_subclass():
    step = parse_step_definition_payload(
        {
            **_base_payload("TRANSFORM"),
            "assignments": {"vars.value": "${input.value}"},
        }
    )

    assert isinstance(step, TransformStepDefinition)
    assert step.assignments == {"vars.value": "${input.value}"}


def test_draft_http_step_allows_missing_runtime_required_fields():
    step = parse_step_definition_payload({**_base_payload("HTTP"), "requestMapping": {}, "httpParamMapping": {}})

    assert isinstance(step, HttpStepDefinition)
    assert step.sysCode is None
    assert step.path is None


def test_draft_sql_step_allows_missing_runtime_required_fields():
    step = parse_step_definition_payload({**_base_payload("SQL"), "paramMapping": {}})

    assert isinstance(step, SqlStepDefinition)
    assert step.sysCode is None
    assert step.datasourceCode is None
    assert step.sqlText is None


@pytest.mark.parametrize(
    ("step_type", "extra_field", "extra_value"),
    [
        ("SQL", "path", "/orders"),
        ("HTTP", "sqlText", "select 1"),
        ("HTTP", "url", "/orders"),
        ("SQL", "sqlParamMapping", {}),
        ("HTTP", "httpSourceCode", "http_template"),
        ("SQL", "sqlSourceCode", "sql_template"),
        ("SQL", "sqlTemplateCode", "legacy_template"),
    ],
)
def test_legacy_or_cross_type_fields_are_rejected(step_type: str, extra_field: str, extra_value):
    payload = {**_base_payload(step_type), extra_field: extra_value}

    with pytest.raises(ValidationError):
        parse_step_definition_payload(payload)


def test_scene_definition_parses_step_union():
    scene = SceneDefinition(
        sceneCode="scene_1",
        sceneName="场景",
        inputSchema=[],
        steps=[
            {**_base_payload("HTTP"), "method": "GET", "requestMapping": {}, "httpParamMapping": {}},
            {**_base_payload("SQL"), "paramMapping": {}},
        ],
        resultMapping={},
    )

    assert isinstance(scene.steps[0], HttpStepDefinition)
    assert isinstance(scene.steps[1], SqlStepDefinition)
