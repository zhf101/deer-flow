"""执行观察到证据事实的抽取规则。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (
    Action,
    ActionAttempt,
    AttemptStatus,
    EvidenceFact,
    FactPredicate,
    Observation,
)


@dataclass
class EvidenceParts:
    """Evidence 的事实组成部分。"""

    facts: list[EvidenceFact] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    unknown_facts: list[str] = field(default_factory=list)


def extract_evidence_parts(action: Action, observation: Observation, attempt: ActionAttempt) -> EvidenceParts:
    """从执行观察中抽取已知事实、缺失事实和未知事实。

    业务目标：回答"用户的造数目标是否达成"，必须基于从执行结果中抽取的客观事实，
    而非任何主观猜测。
    当前动作：根据场景执行状态和业务结果，按以下优先级抽取事实：
    1. 执行状态未知 → 记录"结果未知"，无法判定
    2. 纯技术失败（无业务结果）→ 记录失败事实和友好原因
    3. 场景整体状态 → 记录 scene.status 事实
    4. 场景业务判定（businessResult）→ 优先采信场景自身的成功/失败规则和原因
    5. 回退逻辑（无 businessResult）→ 按订单字段契约兜底抽取（仅 create_paid_order）
    """

    parts = EvidenceParts()
    if attempt.status == AttemptStatus.UNKNOWN_STATE:
        parts.unknown_facts.append("attempt_result_unknown")
        return parts

    preview = observation.preview or {}

    # 场景执行失败时分两种情况处理：
    # - 如果场景返回了业务结果（businessResult），说明执行到了业务层但业务逻辑判定失败，
    #   真正原因（如"支付状态不是 PAID"）藏在 businessResult 里，需要继续往下走业务判定分支抽取精确原因。
    # - 如果没有业务结果，说明是纯技术失败（网络超时、校验异常等），
    #   此时只能记录一条技术层失败事实，但至少要把 execution 层的友好错误信息带上。
    if attempt.status == AttemptStatus.FAILED and not preview.get("businessResult"):
        parts.facts.append(
            EvidenceFact(
                subject="attempt.status",
                predicate=FactPredicate.EQUALS,
                expected="SUCCEEDED",
                actual="FAILED",
                passed=False,
                detail=attempt.error_message or None,
                source_observation_id=observation.observation_id,
            )
        )
        return parts

    _collect_scene_status(parts, observation, preview)
    if _collect_business_result(parts, observation, preview):
        return parts

    # 场景没有配置业务判定规则（businessResult 为空）时的回退逻辑。
    # 通用场景先抽取实际返回里已经存在的关键 finalOutput 字段，不强加缺失事实。
    _collect_generic_final_output_facts(parts, observation, preview)

    # 非 create_paid_order 的场景没有固定必填字段契约，凭已有 scene.status 和通用事实判定。
    if action.scene_code != "create_paid_order":
        return parts

    _collect_create_paid_order_facts(parts, observation, preview)
    return parts


def _collect_scene_status(parts: EvidenceParts, observation: Observation, preview: dict) -> None:
    """抽取场景整体状态事实。"""

    scene_status = str(preview.get("status", "")).upper()
    if scene_status:
        parts.facts.append(
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
        parts.missing_facts.append("scene.status")


def _collect_business_result(parts: EvidenceParts, observation: Observation, preview: dict) -> bool:
    """优先采信场景自身业务判定结果，返回是否已命中该分支。"""

    business = preview.get("businessResult")
    if not business:
        return False

    is_success = bool(business.get("isSuccess"))
    failed_rules = business.get("failedRules") or []
    parts.facts.append(
        EvidenceFact(
            subject="scene.business_success",
            predicate=FactPredicate.EQUALS,
            expected=True,
            actual=is_success,
            passed=is_success,
            detail="；".join(str(r) for r in failed_rules) or str(business.get("reason") or ""),
            source_observation_id=observation.observation_id,
        )
    )
    return True


def _collect_create_paid_order_facts(parts: EvidenceParts, observation: Observation, preview: dict) -> None:
    """create_paid_order 专用纵切片：按订单字段契约兜底抽取。"""

    final_output = preview.get("finalOutput", preview)

    order_id = final_output.get("order_id")
    if order_id is not None:
        parts.facts.append(
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
        parts.missing_facts.append("order.order_id")

    pay_status = final_output.get("pay_status")
    if pay_status is not None:
        parts.facts.append(
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
        parts.missing_facts.append("order.pay_status")


def _collect_generic_final_output_facts(parts: EvidenceParts, observation: Observation, preview: dict) -> None:
    """抽取通用 finalOutput 字段，供多步骤变量绑定使用。"""

    final_output = preview.get("finalOutput")
    if not isinstance(final_output, dict):
        return

    if "order_id" in final_output:
        parts.facts.append(
            EvidenceFact(
                subject="finalOutput.order_id",
                predicate=FactPredicate.EXISTS,
                expected=True,
                actual=final_output.get("order_id"),
                passed=final_output.get("order_id") is not None,
                source_observation_id=observation.observation_id,
            )
        )

    if "pay_status" in final_output:
        pay_status = final_output.get("pay_status")
        parts.facts.append(
            EvidenceFact(
                subject="finalOutput.pay_status",
                predicate=FactPredicate.EQUALS,
                expected="PAID",
                actual=pay_status,
                passed=(pay_status == "PAID"),
                source_observation_id=observation.observation_id,
            )
        )
