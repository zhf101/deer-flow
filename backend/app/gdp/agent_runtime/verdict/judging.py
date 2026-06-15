"""证据到结果判定的规则。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..models import Action, Evidence, Verdict, VerdictType, reject_lm_proposal
from ..support.log_text import describe_fact_name, describe_fact_value


def _now() -> datetime:
    return datetime.now(UTC)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def judge(evidence: Evidence, action: Action) -> Verdict:
    """回答用户最关心的问题："我的造数目标达成了吗？"。"""

    reject_lm_proposal(evidence)
    reject_lm_proposal(action)

    verdict_id = _gen_id("vrd")

    if evidence.unknown_facts:
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.UNKNOWN_STATE,
            reason="执行结果未知：" + "，".join(describe_fact_name(item) for item in evidence.unknown_facts),
            created_at=_now(),
        )

    if evidence.missing_facts:
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.NEED_USER,
            reason="证据不足，缺失：" + "，".join(describe_fact_name(item) for item in evidence.missing_facts),
            created_at=_now(),
        )

    failed_facts = [fact for fact in evidence.facts if not fact.passed]
    if failed_facts:
        return Verdict(
            verdict_id=verdict_id,
            task_run_id=evidence.task_run_id,
            step_id=evidence.step_id,
            evidence_id=evidence.evidence_id,
            verdict_type=VerdictType.FAILED,
            reason="；".join(_failed_fact_reason(fact) for fact in failed_facts),
            created_at=_now(),
        )

    return Verdict(
        verdict_id=verdict_id,
        task_run_id=evidence.task_run_id,
        step_id=evidence.step_id,
        evidence_id=evidence.evidence_id,
        verdict_type=VerdictType.DONE,
        reason="所有事实通过",
        created_at=_now(),
    )


def _failed_fact_reason(fact) -> str:
    """把失败事实转成用户可读原因。"""

    if fact.detail:
        return fact.detail
    return (
        f"{describe_fact_name(fact.subject)}未达预期："
        f"期望={describe_fact_value(fact.expected)}，实际={describe_fact_value(fact.actual)}"
    )
