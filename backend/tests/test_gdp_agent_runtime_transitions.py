"""GDP Agent Runtime 状态机专项测试。"""

from __future__ import annotations

import pytest

from datetime import UTC, datetime

from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import (
    LMProposal,
    Requirement,
    RequirementLayer,
    RequirementStatus,
    TaskRunStatus,
)
from app.gdp.agent_runtime.transitions import (
    IllegalTransition,
    transition_requirement,
    transition_task_run,
)


def _make_requirement(status: RequirementStatus = RequirementStatus.PENDING) -> Requirement:
    now = datetime.now(UTC)
    return Requirement(
        requirement_id="req-1",
        task_run_id="tr-1",
        step_id="step-1",
        layer=RequirementLayer.SCENE,
        goal="造一笔已支付订单",
        status=status,
        created_at=now,
        updated_at=now,
    )


def test_task_run_cancel_allowed_before_terminal_and_rejected_after_terminal():
    """CREATED/RUNNING/WAITING_USER 可取消，终态不可回退。"""
    created = create_task_run("待取消任务", env_code="SIT1")
    assert transition_task_run(created, TaskRunStatus.CANCELLED).status == TaskRunStatus.CANCELLED

    running = create_task_run("运行中任务", env_code="SIT1")
    running = transition_task_run(running, TaskRunStatus.RUNNING)
    assert transition_task_run(running, TaskRunStatus.CANCELLED).status == TaskRunStatus.CANCELLED

    waiting = create_task_run("等待用户任务", env_code="SIT1")
    waiting = transition_task_run(waiting, TaskRunStatus.RUNNING)
    waiting.pending_question = "请确认。"
    waiting = transition_task_run(waiting, TaskRunStatus.WAITING_USER)
    assert transition_task_run(waiting, TaskRunStatus.CANCELLED).status == TaskRunStatus.CANCELLED

    failed = create_task_run("失败任务", env_code="SIT1")
    failed = transition_task_run(failed, TaskRunStatus.RUNNING)
    failed.failure_reason = "测试失败。"
    failed = transition_task_run(failed, TaskRunStatus.FAILED)
    with pytest.raises(IllegalTransition):
        transition_task_run(failed, TaskRunStatus.CANCELLED)


def test_requirement_legal_path_pending_resolving_satisfied():
    """Requirement 合法路径：PENDING -> RESOLVING -> SATISFIED。"""
    req = _make_requirement()
    req = transition_requirement(req, RequirementStatus.RESOLVING)
    assert req.status == RequirementStatus.RESOLVING
    req = transition_requirement(req, RequirementStatus.SATISFIED)
    assert req.status == RequirementStatus.SATISFIED


def test_requirement_pending_to_failed_allowed():
    """零候选用户放弃：PENDING -> FAILED。"""
    req = _make_requirement()
    req = transition_requirement(req, RequirementStatus.FAILED)
    assert req.status == RequirementStatus.FAILED


def test_requirement_resolving_to_failed_allowed():
    """候选中放弃：RESOLVING -> FAILED。"""
    req = _make_requirement(RequirementStatus.RESOLVING)
    req = transition_requirement(req, RequirementStatus.FAILED)
    assert req.status == RequirementStatus.FAILED


def test_requirement_illegal_transition_rejected():
    """非法转移被拒：SATISFIED 是终态，不能再转。"""
    req = _make_requirement(RequirementStatus.SATISFIED)
    with pytest.raises(IllegalTransition):
        transition_requirement(req, RequirementStatus.RESOLVING)

    # PENDING 不能直接跳到 SATISFIED（必须先 RESOLVING）。
    pending = _make_requirement()
    with pytest.raises(IllegalTransition):
        transition_requirement(pending, RequirementStatus.SATISFIED)


def test_requirement_transition_rejects_lm_proposal():
    """LMProposal 不能作为状态写入。"""
    req = _make_requirement()
    proposal = LMProposal(
        proposal_id="lp-1",
        payload=RequirementStatus.RESOLVING,
        prompt_hash="hash",
        model_name="test-model",
        confidence=0.9,
    )
    with pytest.raises(TypeError):
        transition_requirement(req, proposal)  # type: ignore[arg-type]

