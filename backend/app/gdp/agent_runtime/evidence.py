"""证据事实构建。

本模块负责从场景执行的原始结果中抽取可判定的证据事实——用于回答
"用户的造数目标是否达成"这个核心问题。所有判定必须基于证据而非猜测。

确定性逻辑，不调用 LLM。
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
    """从执行观察中按场景契约抽取事实，为后续判定提供完整依据。

    业务目标：回答"用户的造数目标是否达成"，必须基于从执行结果中抽取的客观事实，
    而非任何主观猜测。
    当前动作：根据场景执行状态和业务结果，按以下优先级抽取事实：
    1. 执行状态未知 → 记录"结果未知"，无法判定
    2. 纯技术失败（无业务结果）→ 记录失败事实和友好原因
    3. 场景整体状态 → 记录 scene.status 事实
    4. 场景业务判定（businessResult）→ 优先采信场景自身的成功/失败规则和原因
    5. 回退逻辑（无 businessResult）→ 按订单字段契约兜底抽取（仅 create_paid_order）
    预期结果：返回 Evidence 对象，包含已知事实（facts）、缺失事实（missing_facts）
    和未知事实（unknown_facts），交由 judge 函数做出最终判定。
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

    # 场景执行失败时分两种情况处理：
    # - 如果场景返回了业务结果（businessResult），说明执行到了业务层但业务逻辑判定失败，
    #   真正原因（如"支付状态不是 PAID"）藏在 businessResult 里，需要继续往下走业务判定分支抽取精确原因。
    # - 如果没有业务结果，说明是纯技术失败（网络超时、校验异常等），
    #   此时只能记录一条技术层失败事实，但至少要把 execution 层的友好错误信息带上。
    if attempt.status == AttemptStatus.FAILED and not preview.get("businessResult"):
        facts.append(
            EvidenceFact(
                subject="attempt.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCEEDED",
                actual="FAILED",
                passed=False,
                # 把执行层已经准备好的友好错误信息（如”无法连接到目标服务器，请检查地址和端口”）
                # 直接带入 detail，这样最终用户看到的失败原因是可读的排查提示，
                # 而不是”期望=SUCCEEDED 实际=FAILED”这种只有开发才能看懂的机器话。
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

    # 优先采信场景自身的业务判定结果。
    # 业务目标：场景配置了 successCriteria 后，成功/失败已由场景按配置规则计算完毕，
    # 精确原因（如”命中失败规则: pay_status eq UNPAID”）在 reason / failedRules 里。
    # 当前动作：直接将场景的判定结果转为一条事实，不需要 Agent 再反推或硬编码字段名。
    # 预期结果：任意配了规则的场景都能走这条路，系统具备通用性；
    # 即使场景状态为 FAILED，这条事实也能补上”为什么失败”的具体原因，
    # 而不只是上面那条空泛的 scene.status 状态码。
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
                # detail 承载用户可读的失败原因：优先展示命中的失败规则
                # （如”pay_status eq UNPAID”），其次是场景给出的判定说明。
                # 让最终判定结果和前端展示能直接告诉用户”哪里不对”。
                detail=”；”.join(str(r) for r in failed_rules) or str(business.get(“reason”) or “”),
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

    # 场景没有配置业务判定规则（businessResult 为空）时的回退逻辑。
    # 业务目标：即使场景没有配 successCriteria，也要尽可能给用户一个明确的判定。
    # 当前动作：非 create_paid_order 的场景没有可抽取的固定字段契约，
    # 只能凭已有的 scene.status 事实判定；create_paid_order 走下面的专用兜底。
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
