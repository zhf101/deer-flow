"""Text-to-Speech (TTS) model implementations."""

from .adapter import get_tts_model
from .base import BaseTTS, TTSResult
# 历史导出先保留为注释，避免直接删除原始实现。
# from .adapter import XinferenceTTS

__all__ = [
    "get_tts_model",
    "BaseTTS",
    "TTSResult",
    # "XinferenceTTS",
]
