"""GDP Agent Runtime 数据库账本持久化测试。"""

from __future__ import annotations

import pytest
from _agent_runtime_catalog_fakes import make_candidate

from app.gdp.agent_runtime.evidence import build_evidence
from app.gdp.agent_runtime.execution import run_action
from app.gdp.agent_runtime.flow import create_single_step, create_task_run, make_scene_action
from app.gdp.agent_runtime.models import (
    ActionStatus,
    DecisionKind,
    DecisionOption,
    DecisionRecord,
    DecisionSource,
    DecisionStatus,
    StepStatus,
    TaskRunStatus,
)
from app.gdp.agent_runtime.planner import plan_step_spec_ref
from app.gdp.agent_runtime.repository import AgentRuntimeRepository
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import EntityNotFoundError, Store
from app.gdp.agent_runtime.transitions import transition_action, transition_step, transition_task_run
from app.gdp.agent_runtime.verdict import apply_verdict, judge
from app.gdp.agent_runtime.workflows.reply_commands import SupplyInputCommand
from app.gdp.agent_runtime.workflows.reply_workflow import handle_reply
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


class _Request:
    scene_code = None

    def __init__(self, inputs: dict[str, object]) -> None:
        self.inputs = inputs


class _MissingInputCatalog:
    async def search(self, **kwargs):
        goal = str(kwargs["goal"])
        user_inputs = kwargs["user_inputs"]
        if "创建" in goal:
            candidate = make_candidate("create_order", scene_name=goal)
        elif "支付" in goal:
            missing = [] if "pay_channel" in user_inputs else ["pay_channel"]
            candidate = make_candidate("pay_order", scene_name=goal, missing_inputs=missing)
        else:
            candidate = make_candidate("query_order", scene_name=goal)
        return ([candidate], [goal])

    async def get_contract(self, *, scene_code: str, user_inputs: dict[str, object]):
        if scene_code == "pay_order":
            missing = [] if "pay_channel" in user_inputs else ["pay_channel"]
            return make_candidate(scene_code, missing_inputs=missing)
        return make_candidate(scene_code)


@pytest.mark.anyio
async def test_runtime_repository_persists_and_hydrates_full_timeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """数据库仓储能保存并恢复完整 Runtime timeline 和 payload。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        return {
            "runId": "scene-run-1",
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)

    db_path = tmp_path / "agent-runtime.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repository = AgentRuntimeRepository(session_factory)

        store = Store()
        task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
        step = create_single_step(task_run)
        action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
        task_run = transition_task_run(task_run, TaskRunStatus.RUNNING)
        step = transition_step(step, StepStatus.RUNNING)
        action = transition_action(action, ActionStatus.RUNNING)
        decision = DecisionRecord(
            decision_id="dec-1",
            task_run_id=task_run.task_run_id,
            step_id=step.step_id,
            requirement_id="req-1",
            proposal_id="prop-1",
            action_id=action.action_id,
            scene_run_id=None,
            decision_kind=DecisionKind.SCENE_SELECTION,
            decision_source=DecisionSource.RULE,
            status=DecisionStatus.DECIDED,
            target_type="scene",
            target_id="create_paid_order",
            input_ref=action.input_ref,
            options=[
                DecisionOption(
                    option_id="create_paid_order",
                    option_type="scene",
                    label="创建已支付订单",
                    score=0.9,
                    reasons=["命中订单目标"],
                )
            ],
            selected_option=DecisionOption(
                option_id="create_paid_order",
                option_type="scene",
                label="创建已支付订单",
                score=0.9,
                reasons=["命中订单目标"],
            ),
            selected_reasons=["单候选高置信自动选定"],
            rejected_reasons=[],
            criteria=["单候选", "评分达到自动选择阈值"],
            evidence_refs=["req-1", "prop-1"],
            model_info=None,
            summary="单候选高置信自动选定：创建已支付订单（create_paid_order）。",
            created_at=task_run.updated_at,
        )
        store.save_task_run(task_run)
        store.save_step(step)
        store.save_action(action)
        store.save_decision(decision)
        store.save_payload(task_run.task_run_id, action.input_ref, {"buyer_id": "U1"})

        attempt, observation = await run_action(action, store)
        store.save_attempt(attempt)
        store.save_observation(observation)
        evidence = build_evidence(step, action, observation, attempt)
        store.save_evidence(evidence)
        verdict = judge(evidence, action)
        store.save_verdict(verdict)
        task_run, step, action = apply_verdict(task_run, step, action, verdict)
        store.save_task_run(task_run)
        store.save_step(step)
        store.save_action(action)

        await repository.persist_store(store, task_run.task_run_id)

        restored = await repository.hydrate_store(task_run.task_run_id)
        timeline = restored.get_timeline(task_run.task_run_id)

        assert timeline["task_run_id"] == task_run.task_run_id
        assert timeline["actions"][0]["scene_code"] == "create_paid_order"
        assert timeline["attempts"][0]["scene_run_id"] == "scene-run-1"
        assert timeline["decisions"][0]["decision_kind"] == "SCENE_SELECTION"
        assert timeline["decisions"][0]["target_id"] == "create_paid_order"
        assert timeline["observations"][0]["raw_ref"] == attempt.response_ref
        assert timeline["evidences"][0]["facts"][0]["subject"] == "scene.status"
        assert timeline["verdicts"][0]["verdict_type"] == "DONE"
        assert restored.get_payload(task_run.task_run_id, attempt.request_ref)["inputs"] == {"buyer_id": "U1"}
        assert restored.get_payload(task_run.task_run_id, attempt.response_ref or "")["runId"] == "scene-run-1"
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_runtime_repository_persists_only_current_task_payloads(tmp_path) -> None:
    """持久化单个 TaskRun 时，不能把其他任务的 payload 串入当前任务。"""
    db_path = tmp_path / "agent-runtime-payload-isolation.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repository = AgentRuntimeRepository(session_factory)

        store = Store()
        task_a = create_task_run("任务 A", env_code="SIT1")
        task_b = create_task_run("任务 B", env_code="SIT1")
        store.save_task_run(task_a)
        store.save_task_run(task_b)
        store.save_payload(task_a.task_run_id, "ref:shared", {"owner": "A"})
        store.save_payload(task_b.task_run_id, "ref:shared", {"owner": "B"})
        store.save_payload(task_b.task_run_id, "ref:only-b", {"owner": "B"})

        await repository.persist_store(store, task_a.task_run_id)

        restored_a = await repository.hydrate_store(task_a.task_run_id)
        assert restored_a.get_payload(task_a.task_run_id, "ref:shared") == {"owner": "A"}

        with pytest.raises(EntityNotFoundError):
            await repository.get_payload(task_a.task_run_id, "ref:only-b")
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_runtime_repository_hydrates_multistep_waiting_user_and_resumes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """多步骤 WAITING_USER 落库恢复后，仍能从 active_step_id 和步骤快照继续执行。"""
    calls: list[dict[str, object]] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        calls.append({"scene_code": scene_code, "inputs": dict(inputs)})
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-1"}, "errors": []}
        if scene_code == "pay_order":
            return {
                "status": "SUCCESS",
                "finalOutput": {"order_id": inputs["order_id"], "pay_status": "PAID", "payment_id": "PAY-1"},
                "errors": [],
            }
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": inputs["order_id"], "pay_status": "PAID", "payment_id": "PAY-1"},
            "errors": [],
        }

    catalog = _MissingInputCatalog()
    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    monkeypatch.setattr("app.gdp.agent_runtime.runner.get_catalog", lambda: catalog)

    db_path = tmp_path / "agent-runtime-multistep-reply.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repository = AgentRuntimeRepository(session_factory)

        store = Store()
        task_run = create_task_run("创建订单并支付", env_code="SIT1")
        store.save_task_run(task_run)
        waiting = await run_task(task_run, _Request({"buyer_id": "U1"}), store, catalog=catalog)

        assert waiting.status == TaskRunStatus.WAITING_USER
        active_step_id = waiting.active_step_id
        assert active_step_id is not None
        assert store.get_payload(waiting.task_run_id, plan_step_spec_ref(active_step_id))["goal"] == "支付订单"

        await repository.persist_store(store, waiting.task_run_id)

        restored = await repository.hydrate_store(waiting.task_run_id)
        restored_task_run = restored.get_task_run(waiting.task_run_id)
        restored_timeline = restored.get_timeline(waiting.task_run_id)
        assert restored_task_run.active_step_id == active_step_id
        assert restored.get_payload(waiting.task_run_id, plan_step_spec_ref(active_step_id))["goal"] == "支付订单"
        assert [step["status"] for step in restored_timeline["steps"]] == ["DONE", "PENDING", "PENDING"]
        assert all("value_ref" not in variable for variable in restored_timeline["variables"])

        result = await handle_reply(
            restored_task_run,
            SupplyInputCommand({"inputs": {"pay_channel": "BALANCE"}}),
            restored,
        )

        timeline = restored.get_timeline(waiting.task_run_id)
        assert result.status == TaskRunStatus.COMPLETED
        assert [step["status"] for step in timeline["steps"]] == ["DONE", "DONE", "DONE"]
        assert [call["scene_code"] for call in calls] == ["create_order", "pay_order", "query_order"]
        assert calls[1]["inputs"] == {"order_id": "ORDER-1", "pay_channel": "BALANCE"}
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_runtime_repository_idempotency_gate_detects_started_action(tmp_path) -> None:
    """数据库幂等门控能识别同一任务中已发起过写请求的同键动作。"""

    db_path = tmp_path / "agent-runtime-idempotency.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repository = AgentRuntimeRepository(session_factory)

        store = Store()
        task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
        step = create_single_step(task_run)
        started_action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
        duplicate_action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
        started_action.attempt_ids.append("att-existing")

        store.save_task_run(task_run)
        store.save_step(step)
        store.save_action(started_action)
        store.save_action(duplicate_action)

        await repository.persist_store(store, task_run.task_run_id)

        assert await repository.claim_idempotency_key(
            task_run.task_run_id,
            duplicate_action.action_id,
            duplicate_action.idempotency_key,
        ) is True
        assert await repository.claim_idempotency_key(
            task_run.task_run_id,
            started_action.action_id,
            started_action.idempotency_key,
        ) is False
    finally:
        await close_engine()
