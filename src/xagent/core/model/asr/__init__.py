from .adapter import get_asr_model
from .base import ASRResult, ASRSegment, BaseASR
# 历史导出先保留为注释，避免直接删除原始实现。
# from .xinference import XinferenceASR

__all__ = [
    "get_asr_model",
    "ASRResult",
    "ASRSegment",
    "BaseASR",
    # "XinferenceASR",
]
