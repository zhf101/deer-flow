"""LLM 输出的安全隔离边界。

业务目标：防止 AI 模型的"幻觉"建议直接污染用户的任务数据和事实账本。
当前动作：AI 模型的任何建议只能被包装为 LMProposal（模型建议信封），不能直接写入事实。
预期结果：模型建议与事实数据之间有明确的隔离层，系统必须经过验证才能采纳建议。

默认关闭，不接真实模型。当前仅定义建议数据结构和 LMProposal 包装边界。
"""

from __future__ import annotations

from .models import LMProposal, RequirementProposal, SceneSelectionSuggestion


async def suggest_scene_rerank(
    proposal: RequirementProposal,
    goal: str,
) -> LMProposal[SceneSelectionSuggestion]:
    """为候选场景生成 AI 重排建议，并用 LMProposal 信封安全包装。

    业务目标：未来接入真实 LLM 后，让模型对搜索到的候选场景做二次排序，提升匹配精度。
    当前动作：默认关闭真实模型调用，沿用候选原始顺序构造建议信封，证明隔离边界存在。
    预期结果：返回的建议被标记为"模型建议"而非"事实"，下游必须显式采纳才能生效。
    """
    ranked_scene_codes = [candidate.scene_code for candidate in proposal.candidates]
    return LMProposal(
        proposal_id=f"lm-{proposal.proposal_id}",
        payload=SceneSelectionSuggestion(
            ranked_scene_codes=ranked_scene_codes,
            explanation=f"默认关闭真实 LLM，沿用当前候选顺序。目标：{goal}",
        ),
        prompt_hash="disabled-by-default",
        model_name="disabled",
        confidence=0.0,
    )
