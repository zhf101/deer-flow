"""GDP Agent Runtime 第二阶段可选 LLM 重排边界。

默认关闭，不接真实模型。该模块只定义建议数据结构和返回 LMProposal 包装，
用于保证 LLM 输出不能直接写事实。
"""

from __future__ import annotations

from .models import LMProposal, RequirementProposal, SceneSelectionSuggestion


async def suggest_scene_rerank(
    proposal: RequirementProposal,
    goal: str,
) -> LMProposal[SceneSelectionSuggestion]:
    """返回一个最小 LMProposal 包装的重排建议。

    第二阶段默认关闭真实模型调用，因此这里只根据现有候选顺序构造建议，
    证明 LLM 边界存在且输出被包裹，不能直接进入事实写接口。
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
