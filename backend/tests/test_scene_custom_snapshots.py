from __future__ import annotations

import pytest
from sqlalchemy import select

from app.gdp.datagen.config.common.models import HttpMethod, InputFieldDefinition, InputFieldType, SceneStatus, SqlOperation
from app.gdp.datagen.config.scene.models import BatchConfig, HttpStepDefinition, SceneDefinition, SqlStepDefinition, ValidationResult
from app.gdp.datagen.config.scene.repository import (
    DataFactorySceneStepHttpConfigRow,
    DataFactorySceneStepRow,
    DataFactorySceneStepSqlConfigRow,
    DataFactorySceneVersionRow,
    SceneRepository,
)
from app.gdp.datagen.config.scene.validation import validate_scene_publish
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def scene_repo(tmp_path):
    db_path = tmp_path / "scene.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        yield SceneRepository(session_factory)
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_custom_http_and_sql_steps_are_saved_as_scene_snapshots(scene_repo: SceneRepository):
    saved = await scene_repo.create_scene(_scene("customScene"))

    assert saved.versionNo == 1
    assert saved.versionStatus == "DRAFT"
    assert len(saved.definition.steps) == 2
    assert [step.executionOrder for step in saved.definition.steps] == [1, 2]
    assert saved.definition.steps[0].templateRef is None
    assert saved.definition.steps[1].templateRef is None

    loaded = await scene_repo.get_scene("customScene")
    http_step = loaded.definition.steps[0]
    sql_step = loaded.definition.steps[1]

    assert http_step.path == "/orders"
    assert http_step.requestMapping["headers"]["Trace-Id"] == "${system.uuid}"
    assert sql_step.normalizedSql == "select * from orders where id = :orderId"
    assert sql_step.paramMapping == {"orderId": "${steps.create_order.outputs.orderNo}"}

    session_factory = get_session_factory()
    assert session_factory is not None
    async with session_factory() as session:
        http_row = (await session.execute(select(DataFactorySceneStepHttpConfigRow))).scalar_one()
        sql_row = (await session.execute(select(DataFactorySceneStepSqlConfigRow))).scalar_one()
        step_rows = (
            await session.execute(select(DataFactorySceneStepRow).order_by(DataFactorySceneStepRow.sort_order.asc()))
        ).scalars().all()

    assert [(row.step_id, row.sort_order) for row in step_rows] == [("create_order", 1), ("query_order", 2)]
    assert http_row.source_code is None
    assert http_row.source_hash_snapshot is None
    assert http_row.drifted is False
    assert sql_row.source_code is None
    assert sql_row.source_hash_snapshot is None
    assert sql_row.drifted is False


@pytest.mark.anyio
async def test_editing_published_scene_creates_new_draft_version(scene_repo: SceneRepository):
    await scene_repo.create_scene(_scene("versionedScene"))
    first_publish = await scene_repo.publish_scene(
        "versionedScene",
        validation_result=ValidationResult(valid=True, issues=[]),
    )

    assert first_publish.versionNo == 1
    assert first_publish.versionStatus == "PUBLISHED"

    updated = _scene("versionedScene")
    updated.sceneName = "Updated custom scene"
    updated.steps[0].path = "/orders/v2"
    draft = await scene_repo.update_scene("versionedScene", updated)

    assert draft.versionNo == 2
    assert draft.versionStatus == "DRAFT"
    assert draft.definition.status == SceneStatus.DRAFT
    assert draft.definition.steps[0].path == "/orders/v2"

    published = await scene_repo.get_scene("versionedScene", version_no=1)
    assert published.versionStatus == "PUBLISHED"
    assert published.definition.status == SceneStatus.PUBLISHED
    assert published.definition.steps[0].path == "/orders"


@pytest.mark.anyio
async def test_scene_list_supports_keyword_status_limit_and_offset(scene_repo: SceneRepository):
    await scene_repo.create_scene(_scene("alphaOrder"))
    await scene_repo.create_scene(_scene("betaOrder"))
    await scene_repo.create_scene(_scene("alphaUser"))
    await scene_repo.publish_scene("alphaOrder", validation_result=ValidationResult(valid=True, issues=[]))

    published_alpha = await scene_repo.list_scenes(keyword="alpha", status=SceneStatus.PUBLISHED, limit=20, offset=0)
    assert [scene.sceneCode for scene in published_alpha] == ["alphaOrder"]

    paged = await scene_repo.list_scenes(limit=1, offset=1)
    assert len(paged) == 1


@pytest.mark.anyio
async def test_error_policy_is_stored_as_plain_string(scene_repo: SceneRepository):
    scene = _scene("continueScene")
    scene.errorPolicy = "CONTINUE_ON_ERROR"
    await scene_repo.create_scene(scene)

    session_factory = get_session_factory()
    assert session_factory is not None
    async with session_factory() as session:
        version_row = (await session.execute(select(DataFactorySceneVersionRow))).scalar_one()

    assert version_row.error_policy_json == "CONTINUE_ON_ERROR"
    loaded = await scene_repo.get_scene("continueScene")
    assert loaded.definition.errorPolicy == "CONTINUE_ON_ERROR"


def test_sql_parameter_without_required_defaults_to_optional():
    scene = _scene("optionalParamScene")
    sql_step = scene.steps[1]
    sql_step.parameters = [{"name": "optionalFilter", "type": "string"}]
    sql_step.paramMapping = {}

    result = validate_scene_publish(scene)

    assert result.valid is True


def test_publish_rejects_update_or_delete_without_where_when_required():
    scene = _scene("unsafeDeleteScene")
    sql_step = scene.steps[1]
    sql_step.operation = SqlOperation.DELETE
    sql_step.sqlText = "DELETE FROM orders"
    sql_step.normalizedSql = "DELETE FROM orders"
    sql_step.parameters = []
    sql_step.paramMapping = {}

    result = validate_scene_publish(scene)

    assert result.valid is False
    assert any("必须包含 WHERE 条件" in issue.message for issue in result.issues)


def test_publish_accepts_delete_with_where_when_required():
    scene = _scene("safeDeleteScene")
    sql_step = scene.steps[1]
    sql_step.operation = SqlOperation.DELETE
    sql_step.sqlText = "DELETE FROM orders WHERE id = :orderId"
    sql_step.normalizedSql = "DELETE FROM orders WHERE id = :orderId"

    result = validate_scene_publish(scene)

    assert result.valid is True


def test_publish_rejects_missing_step_output_name():
    scene = _scene("missingOutputScene")
    sql_step = scene.steps[1]
    sql_step.paramMapping = {"orderId": "${steps.create_order.outputs.missing}"}

    result = validate_scene_publish(scene)

    assert result.valid is False
    assert any("步骤输出不存在：create_order.missing" in issue.message for issue in result.issues)


def test_publish_rejects_references_to_disabled_steps():
    scene = _scene("disabledReferenceScene")
    disabled_step = HttpStepDefinition(
        stepId="disabled_login",
        stepName="禁用登录",
        type="HTTP",
        enabled=False,
        dependsOn=[],
        outputMapping={"token": "${RES_BODY(data.token)}"},
    )
    scene.steps.insert(0, disabled_step)
    sql_step = scene.steps[2]
    sql_step.dependsOn = ["disabled_login"]
    sql_step.paramMapping = {"orderId": "${steps.disabled_login.outputs.token}"}
    scene.resultMapping = {"token": "${steps.disabled_login.outputs.token}"}

    result = validate_scene_publish(scene)

    assert result.valid is False
    assert any("不能引用禁用步骤" in issue.message for issue in result.issues)


def _scene(scene_code: str) -> SceneDefinition:
    return SceneDefinition(
        sceneCode=scene_code,
        sceneName="Custom scene",
        inputSchema=[
            InputFieldDefinition(
                name="env",
                label="环境",
                type=InputFieldType.STRING,
                required=True,
                batchEnabled=False,
            )
        ],
        steps=[
            HttpStepDefinition(
                stepId="create_order",
                stepName="创建订单",
                type="HTTP",
                enabled=True,
                dependsOn=[],
                sysCode="TRADE",
                method=HttpMethod.POST,
                path="/orders",
                requestMapping={
                    "headers": {"Trace-Id": "${system.uuid}"},
                    "bodyMapping": {"buyer.id": "${input.userId}"},
                },
                responseHandling={
                    "expectedContentType": "JSON",
                    "statusCode": {"success": [200]},
                    "businessSuccess": {"allOf": []},
                    "businessFailure": {"anyOf": []},
                },
                outputMapping={"orderNo": "${RES_BODY(data.orderNo)}"},
            ),
            SqlStepDefinition(
                stepId="query_order",
                stepName="查询订单",
                type="SQL",
                enabled=True,
                dependsOn=["create_order"],
                sysCode="TRADE",
                datasourceCode="tradeDb",
                operation=SqlOperation.SELECT,
                sqlText="select * from orders where id = :orderId",
                normalizedSql="select * from orders where id = :orderId",
                parameters=[{"name": "orderId", "type": "string", "required": True}],
                paramMapping={"orderId": "${steps.create_order.outputs.orderNo}"},
                resultFields=[{"id": "f1", "fieldName": "id", "sourceTable": "orders", "alias": "id", "description": ""}],
                outputMapping={"orderId": "${SQL_RESULT(rows[0].id)}"},
            ),
        ],
        resultMapping={"orderNo": "${steps.create_order.outputs.orderNo}"},
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )
