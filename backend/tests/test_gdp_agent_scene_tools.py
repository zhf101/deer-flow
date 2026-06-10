"""GDP Agent 场景工具测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.gdp.agent.tools.scene_tools import bind_scene_inputs, build_scene_tools, run_datagen_scene_for_task
from app.gdp.agent.tools.task_tools import get_datagen_task_state
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.common.models import CapabilityType, HttpMethod, InputFieldDefinition, InputFieldType, SceneStatus, StepType
from app.gdp.datagen.config.scene.models import (
    BatchConfig,
    HttpStepDefinition,
    SceneDefinition,
    SceneExecutionResult,
    SceneRunRequest,
    StepExecutionResult,
    ValidationResult,
)
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def services(tmp_path):
    db_path = tmp_path / "agent-tools.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        scene_repo = SceneRepository(session_factory)
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        await scene_repo.create_scene(_scene("createOrder"))
        await scene_repo.publish_scene("createOrder", validation_result=ValidationResult(valid=True, issues=[]))
        yield {
            "catalog": AgentCatalogService(scene_repo),
            "task": task_service,
            "scene_success": _FakeSceneService("SUCCESS"),
            "scene_failed": _FakeSceneService("FAILED"),
        }
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_bind_scene_inputs_uses_alias_and_variable_stack(services):
    result = await bind_scene_inputs(
        services["catalog"],
        scene_code="createOrder",
        user_inputs={},
        visible_variables=[{"name": "buyer", "semanticType": "USER_ID", "valuePreview": "U1"}],
    )

    assert result["bindings"] == {"userId": "U1"}
    assert result["missingInputs"] == []
    assert result["sources"] == {"userId": "variable.buyer"}


@pytest.mark.anyio
async def test_bind_scene_inputs_uses_full_variable_value_before_preview(services):
    result = await bind_scene_inputs(
        services["catalog"],
        scene_code="createOrder",
        user_inputs={},
        visible_variables=[
            {
                "name": "buyer",
                "semanticType": "USER_ID",
                "value": ["U1", "U2", "U3"],
                "valuePreview": ["U1", "U2"],
            }
        ],
    )

    assert result["bindings"] == {"userId": ["U1", "U2", "U3"]}
    assert result["missingInputs"] == []


@pytest.mark.anyio
async def test_run_datagen_scene_for_task_records_success_history(services):
    task_run = await services["task"].create_task_run(
        DatagenTaskRunCreateRequest(userIntent="造订单", inputs={"userId": "U1"})
    )

    result = await run_datagen_scene_for_task(
        services["task"],
        services["scene_success"],
        task_run_id=task_run.taskRunId,
        scene_code="createOrder",
        env_code="DEV",
        input_params={"userId": "U1"},
    )

    assert result["success"] is True
    assert result["sceneRunId"] == "scene_run_success"
    assert "finalOutput" not in result
    assert result["outputKeys"] == ["orderId"]
    assert result["finalOutputPreview"] == {"orderId": "O1"}
    steps = await services["task"].list_steps(task_run.taskRunId)
    assert steps[0].sceneRunId == "scene_run_success"
    updated_task = await services["task"].get_task_run(task_run.taskRunId)
    assert updated_task.visibleVariables[-1].name == "orderId"
    assert updated_task.visibleVariables[-1].value == "O1"
    assert updated_task.visibleVariables[-1].valuePreview == "O1"
    events = await services["task"].list_events(task_run.taskRunId)
    assert "SCENE_RUN_STARTED" in [event.eventType for event in events]
    assert "SCENE_RUN_FINISHED" in [event.eventType for event in events]
    assert "VARIABLE_STACK_UPDATED" in [event.eventType for event in events]


@pytest.mark.anyio
async def test_run_datagen_scene_for_task_returns_preview_but_persists_full_output(services):
    task_run = await services["task"].create_task_run(
        DatagenTaskRunCreateRequest(userIntent="查询一批订单", inputs={"userId": "U1"})
    )
    large_output = {
        "orders": [{"orderId": f"O{i}", "status": "PAID"} for i in range(5)],
        "rawText": "X" * 300,
    }

    result = await run_datagen_scene_for_task(
        services["task"],
        _FakeSceneService("SUCCESS", final_output=large_output),
        task_run_id=task_run.taskRunId,
        scene_code="createOrder",
        env_code="DEV",
        input_params={"userId": "U1"},
    )

    assert "finalOutput" not in result
    assert result["outputKeys"] == ["orders", "rawText"]
    assert result["finalOutputPreview"]["orders"] == large_output["orders"][:2]
    assert result["finalOutputPreview"]["rawText"] == "X" * 256
    assert result["finalOutputSchema"]["fields"]["orders"]["type"] == "array"
    assert result["finalOutputSize"]["itemCount"] == 2
    steps = await services["task"].list_steps(task_run.taskRunId)
    assert steps[0].output == large_output


@pytest.mark.anyio
async def test_run_datagen_scene_for_task_reuses_successful_same_input_step(services):
    task_run = await services["task"].create_task_run(
        DatagenTaskRunCreateRequest(userIntent="造订单", inputs={"userId": "U1"})
    )

    first = await run_datagen_scene_for_task(
        services["task"],
        services["scene_success"],
        task_run_id=task_run.taskRunId,
        scene_code="createOrder",
        env_code="DEV",
        input_params={"userId": "U1"},
    )
    second = await run_datagen_scene_for_task(
        services["task"],
        services["scene_success"],
        task_run_id=task_run.taskRunId,
        scene_code="createOrder",
        env_code="DEV",
        input_params={"userId": "U1"},
    )

    assert second["idempotentReuse"] is True
    assert second["taskStepId"] == first["taskStepId"]
    assert second["sceneRunId"] == first["sceneRunId"]
    assert services["scene_success"].call_count == 1
    steps = await services["task"].list_steps(task_run.taskRunId)
    assert [step.stepType for step in steps].count("RUN_SCENE") == 1
    events = await services["task"].list_events(task_run.taskRunId)
    assert "SCENE_RUN_IDEMPOTENT_REUSED" in [event.eventType for event in events]


@pytest.mark.anyio
async def test_run_datagen_scene_for_task_fails_task_on_scene_error(services):
    task_run = await services["task"].create_task_run(
        DatagenTaskRunCreateRequest(userIntent="造订单", inputs={"userId": "U1"})
    )

    result = await run_datagen_scene_for_task(
        services["task"],
        services["scene_failed"],
        task_run_id=task_run.taskRunId,
        scene_code="createOrder",
        env_code="DEV",
        input_params={"userId": "U1"},
    )

    assert result["success"] is False
    failed_task = await services["task"].get_task_run(task_run.taskRunId)
    assert failed_task.status == "FAILED"
    assert failed_task.failureType == "SCENE_BUSINESS_ERROR"


@pytest.mark.anyio
async def test_get_datagen_task_state_returns_variable_preview_only(services):
    task_run = await services["task"].create_task_run(
        DatagenTaskRunCreateRequest(userIntent="造订单", inputs={"userId": "U1"})
    )

    state = await get_datagen_task_state(services["task"], task_run.taskRunId)

    assert state["taskRunId"] == task_run.taskRunId
    assert state["visibleVariables"][0]["valuePreview"] == "U1"
    assert "value" not in state["visibleVariables"][0]


@pytest.mark.anyio
async def test_build_scene_tools_exposes_expected_tool_names(services):
    tools = build_scene_tools(
        catalog_service=services["catalog"],
        task_service=services["task"],
        scene_service=services["scene_success"],
    )

    assert {tool.name for tool in tools} == {
        "search_scene_contracts",
        "get_scene_contract",
        "bind_scene_inputs",
        "run_datagen_scene_for_task",
        "reflect_scene_result",
    }


class _FakeSceneService:
    def __init__(self, status: str, *, final_output: dict | None = None) -> None:
        self._status = status
        self._final_output = final_output
        self.call_count = 0

    async def run_scene(self, request: SceneRunRequest) -> SceneExecutionResult:
        self.call_count += 1
        now = datetime.now(UTC)
        success = self._status == "SUCCESS"
        final_output = self._final_output or {"orderId": "O1"}
        return SceneExecutionResult(
            runId="scene_run_success" if success else "scene_run_failed",
            sceneCode=request.sceneCode,
            versionNo=1,
            envCode=request.envCode,
            inputs=request.inputs,
            status=self._status,
            startedAt=now,
            finishedAt=now,
            durationMs=1,
            stepResults=[
                StepExecutionResult(
                    stepId="createOrder",
                    stepName="创建订单",
                    type=StepType.HTTP,
                    status=self._status,
                    startedAt=now,
                    finishedAt=now,
                    durationMs=1,
                    outputs=final_output if success else {},
                    error=None if success else "业务失败",
                )
            ],
            finalOutput=final_output if success else {},
            errors=[] if success else ["createOrder: 业务失败"],
        )


def _scene(scene_code: str) -> SceneDefinition:
    return SceneDefinition(
        sceneCode=scene_code,
        sceneName="创建订单",
        sceneRemark="创建测试订单并返回订单号。",
        tags=["订单"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[{"effectType": "CREATE_ORDER", "target": "orders"}],
        agentDescription="创建一笔测试订单。",
        inputSchema=[
            InputFieldDefinition(name="env", label="环境", type=InputFieldType.STRING),
            InputFieldDefinition(
                name="userId",
                label="用户",
                type=InputFieldType.STRING,
                semanticType="USER_ID",
                aliases=["buyerId"],
            ),
        ],
        resultSchema=[
            InputFieldDefinition(
                name="orderId",
                label="订单号",
                type=InputFieldType.STRING,
                semanticType="ORDER_ID",
            )
        ],
        steps=[
            HttpStepDefinition(
                stepId="createOrder",
                stepName="创建订单",
                type="HTTP",
                sysCode="TRADE",
                method=HttpMethod.POST,
                path="/orders",
                requestMapping={"bodyMapping": {"userId": "${input.userId}"}},
                outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
            )
        ],
        resultMapping={"orderId": "${steps.createOrder.outputs.orderId}"},
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )
