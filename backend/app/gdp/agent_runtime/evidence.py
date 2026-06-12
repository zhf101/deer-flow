"""GDP Agent Runtime Evidence(依据事实) 构建。

从 Observation 中按 Scene 契约抽取事实。确定性逻辑，不调 LLM。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from .models import (
    Action,
    ActionAttempt,
    AttemptStatus,
    Evidence,
    EvidenceFact,
    FactPredicate,
    Observation,
    PlanStep,
)


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
    """从 observation 中按 scene 契约抽取事实。

    优先复用 Scene 执行器已经根据业务成功规则算出的整体状态。
    create_paid_order 作为 MVP 专用纵切片，额外检查订单字段。
    """
    evidence_id = _gen_id("evi")
    facts: list[EvidenceFact] = []
    missing_facts: list[str] = []
    unknown_facts: list[str] = []

    if attempt.status == AttemptStatus.UNKNOWN_STATE:
        unknown_facts.append("attempt_result_unknown")
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    preview = observation.preview or {}

    # 业务失败会被 Scene 降级成 status=FAILED → attempt=FAILED，但真正原因在
    # businessResult 里。所以不能见 FAILED 就提前返回：有 businessResult 时要继续
    # 往下走业务判定分支抽出精确原因；只有纯技术失败（校验/异常/幂等冲突，
    # 没有任何结构化结果）才在这里记一条光秃秃的 attempt 失败事实并返回。
    if attempt.status == AttemptStatus.FAILED and not preview.get("businessResult"):
        facts.append(
            EvidenceFact(
                subject="attempt.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCEEDED",
                actual="FAILED",
                passed=False,
                # detail 带上 execution 层已挖好的友好原因（如“无法连接到目标服务器…”），
                # 否则 Verdict 只能退化成“期望=SUCCEEDED 实际=FAILED”这种用户看不懂的机器话。
                detail=attempt.error_message or None,
                source_observation_id=observation.observation_id,
            )
        )
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    scene_status = str(preview.get("status", "")).upper()
    if scene_status:
        facts.append(
            EvidenceFact(
                subject="scene.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCESS",
                actual=scene_status,
                passed=(scene_status == "SUCCESS"),
                source_observation_id=observation.observation_id,
            )
        )
    else:
        missing_facts.append("scene.status")

    # 优先采信场景自己的业务判定（businessResult）。
    # Scene 配了 successCriteria 时，成功/失败已由场景按配置规则算好，
    # 并把精确原因放在 reason / failedRules 里。这里直接把它转成一条事实即可，
    # 不必再让 Agent 反推或硬编码字段——这样任意配了规则的真实场景都能复用。
    # 业务失败时 Scene 会把 status 降级为 FAILED，上面已记一条 scene.status 失败事实，
    # 这条 business_success 事实补上“为什么失败”，避免只有一句空泛的状态码。
    business = preview.get("businessResult")
    if business:
        is_success = bool(business.get("isSuccess"))
        failed_rules = business.get("failedRules") or []
        facts.append(
            EvidenceFact(
                subject="scene.business_success",
                predicate=FactPredicate.EQUALS,
                expected=True,
                actual=is_success,
                passed=is_success,
                # detail 承载人类可读原因：失败规则优先，其次判定说明。
                # 让 Verdict 和前端能直接展示“命中失败规则: pay_status eq UNPAID”。
                detail="；".join(str(r) for r in failed_rules) or str(business.get("reason") or ""),
                source_observation_id=observation.observation_id,
            )
        )
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    # 场景没配 successCriteria（businessResult 为空）时才走回退逻辑。
    # 非 create_paid_order 的场景没有可抽取的固定字段契约，仅凭步骤状态判定。
    if action.scene_code != "create_paid_order":
        return Evidence(
            evidence_id=evidence_id,
            task_run_id=action.task_run_id,
            step_id=step.step_id,
            action_id=action.action_id,
            facts=facts,
            missing_facts=missing_facts,
            unknown_facts=unknown_facts,
            created_at=_now(),
        )

    # create_paid_order 专用纵切片：场景未配规则时，按订单字段契约兜底抽取。
    final_output = preview.get("finalOutput", preview)

    order_id = final_output.get("order_id")
    if order_id is not None:
        facts.append(
            EvidenceFact(
                subject="order.order_id",
                predicate=FactPredicate.EXISTS,
                expected=True,
                actual=order_id,
                passed=True,
                source_observation_id=observation.observation_id,
            )
        )
    else:
        missing_facts.append("order.order_id")

    pay_status = final_output.get("pay_status")
    if pay_status is not None:
        facts.append(
            EvidenceFact(
                subject="order.pay_status",
                predicate=FactPredicate.EQUALS,
                expected="PAID",
                actual=pay_status,
                passed=(pay_status == "PAID"),
                source_observation_id=observation.observation_id,
            )
        )
    else:
        missing_facts.append("order.pay_status")

    return Evidence(
        evidence_id=evidence_id,
        task_run_id=action.task_run_id,
        step_id=step.step_id,
        action_id=action.action_id,
        facts=facts,
        missing_facts=missing_facts,
        unknown_facts=unknown_facts,
        created_at=_now(),
    )
