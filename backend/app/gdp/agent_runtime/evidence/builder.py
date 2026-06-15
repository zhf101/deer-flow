"""Evidence 对象组装。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..models import Action, ActionAttempt, Evidence, Observation, PlanStep
from .extraction import extract_evidence_parts


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def build_evidence(
    step: PlanStep,
    action: Action,
    observation: Observation,
    attempt: ActionAttempt,
) -> Evidence:
    """从执行观察中按场景契约抽取事实，为后续判定提供完整依据。"""

    parts = extract_evidence_parts(action, observation, attempt)
    return Evidence(
        evidence_id=_gen_id("evi"),
        task_run_id=action.task_run_id,
        step_id=step.step_id,
        action_id=action.action_id,
        facts=parts.facts,
        missing_facts=parts.missing_facts,
        unknown_facts=parts.unknown_facts,
        created_at=_now(),
    )
