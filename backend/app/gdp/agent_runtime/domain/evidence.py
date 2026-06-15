"""证据链领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .identifiers import ActionId, AttemptId, EvidenceId, StepId, StorageRef, TaskRunId


class Observation(BaseModel):
    """场景执行后的原始观察数据，是证据链的起点。

    业务目标：完整保存场景调用的原始返回结果（HTTP 状态、响应体、错误信息等），
    作为后续证据抽取的唯一数据源，确保判定基于真实观察而非推测。
    """

    observation_id: str = Field(description="观察唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    action_id: ActionId = Field(description="所属动作 ID。")
    attempt_id: AttemptId = Field(description="所属执行尝试 ID，标识这次观察来自哪次调用。")
    raw_ref: StorageRef = Field(description="完整原始响应的安全存储引用，供审计人员查看原始返回数据。")
    preview: dict[str, Any] = Field(default_factory=dict, description="可展示的观察摘要，包含场景状态码、业务结果和输出数据。")
    created_at: datetime = Field(description="观察生成时间。")


class FactPredicate(StrEnum):
    """证据事实的判定方式，定义如何验证一个事实是否成立。"""

    EXISTS = "EXISTS"        # 判定某个值是否存在（如"订单号是否存在"）
    EQUALS = "EQUALS"        # 判定某个值是否等于期望值（如"支付状态是否等于 PAID"）
    IN = "IN"                # 判定某个值是否属于某个集合
    NON_EMPTY = "NON_EMPTY"  # 判定某个值是否非空


class EvidenceFact(BaseModel):
    """一条可判定的事实，是 Verdict 做出判定的最小单元。

    业务目标：把场景执行的原始结果转化为结构化的"预期 vs 实际"对比，
    让用户和系统都能清晰看到"哪里通过了、哪里没通过、为什么没通过"。
    """

    subject: str = Field(description="事实主体标识，如 order.pay_status，指明这条事实在检查什么。")
    predicate: FactPredicate = Field(description="判定方式，如 EQUALS 表示期望等于某值")
    expected: Any = Field(description="期望值，如 PAID 表示期望支付状态为已支付。")
    actual: Any = Field(description="实际值，从场景执行结果中提取的真实数据。")
    passed: bool = Field(description="是否通过判定，true 表示实际值满足期望。")
    # detail 承载场景自己算出的精确原因（如命中的失败规则描述）。
    # 业务失败时 Scene 把原因放在 businessResult 里，必须透传到这里，
    # 否则 Verdict 只能给出"执行失败"这种无信息量的结论。
    detail: str | None = Field(default=None, description="事实的补充说明，如命中的业务规则描述或步骤级友好错误提示，让用户看到'为什么没通过'。")
    source_observation_id: str = Field(description="事实来源的观察 ID，确保每条事实都能追溯到原始数据。")


class Evidence(BaseModel):
    """从观察中抽取的可判定证据集合，是 Verdict 的唯一输入。

    业务目标：把原始执行结果结构化为"已知事实""缺失事实""未知事实"三类，
    确保判定结论完全基于证据，杜绝 LLM 凭感觉宣布造数成功或失败。
    当前动作：由 evidence.py 的 build_evidence() 从 Observation 中抽取。
    预期结果：Evidence 产出后交给 judge() 做出最终判定。
    """

    evidence_id: EvidenceId = Field(description="证据集合唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId = Field(description="所属业务步骤 ID。")
    action_id: ActionId = Field(description="所属动作 ID。")
    facts: list[EvidenceFact] = Field(default_factory=list, description="已抽取的已知事实，每条事实包含期望值和实际值的对比。")
    missing_facts: list[str] = Field(default_factory=list, description="无法抽取的事实（如场景没有返回某字段），缺失将导致判定为 NEED_USER。")
    unknown_facts: list[str] = Field(default_factory=list, description="结果不确定的事实（如超时导致不知道执行是否成功），将导致判定为 UNKNOWN_STATE。")
    created_at: datetime = Field(description="证据生成时间。")
