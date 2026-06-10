"""造数任务控制面服务测试。"""

from __future__ import annotations

import pytest

from app.gdp.datagen.config.task import api as task_api
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskRunCreateRequest,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
    DatagenTaskUserReplyRequest,
)
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def task_service(tmp_path):
    db_path = tmp_path / "datagen-task.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repo = DatagenTaskRepository(session_factory)
        yield DatagenTaskService(repo), repo
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_create_task_defaults_dev_and_records_events(task_service):
    service, _repo = task_service

    task_run = await service.create_task_run(
        DatagenTaskRunCreateRequest(
            userIntent="  帮我造一笔已支付订单  ",
            inputs={"count": 1},
        ),
        operator="tester",
    )

    assert task_run.userIntent == "帮我造一笔已支付订单"
    assert task_run.envCode == "DEV"
    assert task_run.envSource == "SYSTEM_DEFAULT"
    assert task_run.status == "PLANNING"
    assert task_run.phase == "INTAKE"
    assert task_run.goalStack[0].goal == "帮我造一笔已支付订单"
    assert task_run.plan is not None
    assert task_run.plan.steps[0].stepType == "RUN_SCENE"
    assert task_run.visibleVariables[0].name == "count"
    assert task_run.visibleVariables[0].valuePreview == 1

    events = await service.list_events(task_run.taskRunId)
    assert [event.eventType for event in events] == ["TASK_CREATED", "DEFAULT_ENV_SELECTED", "TASK_PLAN_CREATED"]
    assert events[1].payload == {"envCode": "DEV"}
    assert events[2].payload["steps"][0]["stepType"] == "RUN_SCENE"


@pytest.mark.anyio
async def test_create_task_keeps_explicit_env_without_default_event(task_service):
    service, _repo = task_service

    task_run = await service.create_task_run(
        DatagenTaskRunCreateRequest(userIntent="查询测试服用户", envCode="TEST")
    )

    assert task_run.envCode == "TEST"
    assert task_run.envSource == "USER_EXPLICIT"
    events = await service.list_events(task_run.taskRunId)
    assert [event.eventType for event in events] == ["TASK_CREATED", "TASK_PLAN_CREATED"]


@pytest.mark.anyio
async def test_repository_records_task_step(task_service):
    service, repo = task_service
    task_run = await service.create_task_run(DatagenTaskRunCreateRequest(userIntent="造订单"))

    step = await repo.create_step(
        task_run_id=task_run.taskRunId,
        step_no=1,
        phase=DatagenTaskPhase.SCENE_FULFILLMENT,
        step_type=DatagenTaskStepType.RUN_SCENE,
        goal="执行创建订单场景",
        status=DatagenTaskStepStatus.SUCCESS,
        selected_resource={"sceneCode": "create_order"},
        input_binding={"count": 1},
        output={"orderId": "O1"},
        scene_run_id="scene_run_1",
    )

    assert step.sceneRunId == "scene_run_1"
    assert step.selectedResource == {"sceneCode": "create_order"}
    steps = await service.list_steps(task_run.taskRunId)
    assert [item.taskStepId for item in steps] == [step.taskStepId]


@pytest.mark.anyio
async def test_continue_task_recovers_non_terminal_steps(task_service):
    service, _repo = task_service
    task_run = await service.create_task_run(DatagenTaskRunCreateRequest(userIntent="继续造订单"))
    running_step = await service.record_task_step(
        task_run.taskRunId,
        phase=DatagenTaskPhase.SCENE_EXECUTING,
        step_type=DatagenTaskStepType.RUN_SCENE,
        goal="执行上一次未完成的场景。",
        status=DatagenTaskStepStatus.RUNNING,
    )
    pending_step = await service.record_task_step(
        task_run.taskRunId,
        phase=DatagenTaskPhase.PROGRESS_REFLECTION,
        step_type=DatagenTaskStepType.REFLECT,
        goal="等待上一次未完成的反思。",
        status=DatagenTaskStepStatus.PENDING,
    )

    response = await service.continue_task(task_run.taskRunId)

    assert "已恢复 2 个非终态步骤" in response.message
    steps = await service.list_steps(task_run.taskRunId)
    recovered = {step.taskStepId: step for step in steps}
    assert recovered[running_step.taskStepId].status == "FAILED"
    assert recovered[running_step.taskStepId].errorType == "RECOVERED_NON_TERMINAL_STEP"
    assert recovered[pending_step.taskStepId].status == "FAILED"
    assert recovered[pending_step.taskStepId].errorMessage == "继续推进任务前恢复上一次运行遗留的非终态步骤。"
    events = await service.list_events(task_run.taskRunId)
    assert [event.eventType for event in events][-2:] == ["TASK_CONTINUE_REQUESTED", "TASK_STEPS_RECOVERED"]
    assert {item["taskStepId"] for item in events[-1].payload["steps"]} == {
        running_step.taskStepId,
        pending_step.taskStepId,
    }


@pytest.mark.anyio
async def test_append_visible_variables_from_scene_result_summarizes_large_value(task_service):
    service, _repo = task_service
    task_run = await service.create_task_run(DatagenTaskRunCreateRequest(userIntent="查询商品"))

    variables = await service.append_visible_variables_from_scene_result(
        task_run.taskRunId,
        scene_code="querySku",
        scene_run_id="scene_run_sku",
        final_output={
            "skuList": [
                {"skuId": "SKU001", "name": "测试商品1", "price": 100, "stock": 10},
                {"skuId": "SKU002", "name": "测试商品2", "price": 200, "stock": 20},
                {"skuId": "SKU003", "name": "测试商品3", "price": 300, "stock": 30},
            ]
        },
    )

    sku_list = next(item for item in variables if item.name == "skuList")
    assert sku_list.valueSize is not None
    assert sku_list.valueSize.itemCount == 3
    assert sku_list.valuePreview == [
        {"skuId": "SKU001", "name": "测试商品1", "price": 100, "stock": 10},
        {"skuId": "SKU002", "name": "测试商品2", "price": 200, "stock": 20},
    ]
    assert sku_list.valueSchema == {
        "type": "array",
        "itemSchema": {
            "type": "object",
            "fields": {
                "skuId": {"type": "string"},
                "name": {"type": "string"},
                "price": {"type": "integer"},
                "stock": {"type": "integer"},
            },
        },
    }
    task = await service.get_task_run(task_run.taskRunId)
    assert task.visibleVariables[-1].source == "${task.sceneRuns.scene_run_sku.finalOutput.skuList}"
    events = await service.list_events(task_run.taskRunId)
    assert events[-1].eventType == "VARIABLE_STACK_UPDATED"


@pytest.mark.anyio
async def test_mark_waiting_user_records_ask_user_step(task_service):
    service, _repo = task_service
    task_run = await service.create_task_run(DatagenTaskRunCreateRequest(userIntent="造订单"))

    await service.mark_waiting_user(
        task_run.taskRunId,
        pending_interrupts={
            "questionType": "WRITE_SCENE_APPROVAL",
            "question": "是否执行写操作场景？",
        },
        message="写操作场景执行前需要用户确认。",
    )

    steps = await service.list_steps(task_run.taskRunId)
    assert steps[0].stepType == "ASK_USER"
    assert steps[0].status == "WAITING_USER"
    assert steps[0].selectedResource == {"questionType": "WRITE_SCENE_APPROVAL"}
    assert steps[0].output["question"] == "是否执行写操作场景？"


@pytest.mark.anyio
async def test_user_reply_records_resume_failed_event_when_runtime_rejects(task_service, monkeypatch):
    service, _repo = task_service
    task_run = await service.create_task_run(
        DatagenTaskRunCreateRequest(userIntent="造订单"),
        deerflow_thread_id="thread-resume-failed",
    )
    await service.mark_waiting_user(
        task_run.taskRunId,
        pending_interrupts={"questionType": "WRITE_SCENE_APPROVAL", "question": "是否执行写操作场景？"},
        message="写操作场景执行前需要用户确认。",
    )

    async def _raise_start_run(*args, **kwargs):
        raise RuntimeError("checkpoint missing")

    monkeypatch.setattr("app.gateway.services.start_run", _raise_start_run)

    with pytest.raises(RuntimeError, match="checkpoint missing"):
        await task_api.record_user_reply(
            task_run.taskRunId,
            DatagenTaskUserReplyRequest(reply={"approved": True}),
            request=object(),
            service=service,
        )

    events = await service.list_events(task_run.taskRunId)
    assert [event.eventType for event in events][-2:] == ["USER_REPLY", "RESUME_FAILED"]
    assert events[-1].payload == {"error": "checkpoint missing"}


@pytest.mark.anyio
async def test_cancel_task_updates_terminal_status(task_service):
    service, _repo = task_service
    task_run = await service.create_task_run(DatagenTaskRunCreateRequest(userIntent="造订单"))

    cancelled = await service.cancel_task(task_run.taskRunId)

    assert cancelled.status == "CANCELLED"
    assert cancelled.finalSummary == "任务已取消。"
    assert cancelled.finishedAt is not None
