"""AI 模型输出安全边界。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .identifiers import HashValue

T = TypeVar("T")


class LMProposal(BaseModel, Generic[T]):  # noqa: UP046
    """AI 模型输出的候选建议，是系统安全边界的核心机制。

    业务目标：防止 AI 模型的"幻觉"或错误输出直接操控造数任务状态。
    所有模型输出必须包装为 LMProposal，经过规则校验和事实接口过滤后，
    才能被采纳为系统中的可信数据。未经校验的 Proposal 只能被丢弃或重新生成。
    """

    proposal_id: str = Field(description="建议唯一标识，用于审计追踪模型输出到最终采纳的完整链路。")
    payload: T = Field(description="模型给出的结构化建议内容，例如场景排序、参数推荐等，尚未被验证为事实。")
    prompt_hash: HashValue = Field(description="生成该建议时所用 Prompt 的哈希，用于复现和审计模型的决策上下文。")
    model_name: str = Field(description="生成该建议的模型名称，用于区分不同模型的建议质量和追溯问题来源。")
    confidence: float = Field(ge=0.0, le=1.0, description="模型自评分数，仅用于候选排序参考，绝不可作为事实依据或直接展示给用户。")


def reject_lm_proposal(value: object) -> None:
    """事实写入接口的安全守卫。

    在所有事实写入路径上拦截 LMProposal 类型，阻止 AI 模型的未验证输出
    绕过安全边界直接写入系统账本。一旦发现 LMProposal 试图写入，立即抛出异常。
    """
    if isinstance(value, LMProposal):
        raise TypeError("LMProposal 不能作为事实写入。")

