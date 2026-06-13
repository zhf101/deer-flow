"""GDP Agent Runtime 数据库账本持久化测试。"""

from __future__ import annotations

import pytest

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
from app.gdp.agent_runtime.repository import AgentRuntimeRepository
from app.gdp.agent_runtime.store import EntityNotFoundError, Store
from app.gdp.agent_runtime.transitions import transition_action, transition_step, transition_task_run
from app.gdp.agent_runtime.verdict import apply_verdict, judge
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


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
