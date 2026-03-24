from __future__ import annotations

from typing import Any, Optional

from .base import ASRResult, ASRSegment, BaseASR


def get_asr_model_instance(db_model: Any) -> BaseASR:
    """
    Create a BaseASR instance from a database model record.

    Args:
        db_model: Database model instance with fields: model_name, model_provider,
                  api_key, base_url, abilities, timeout, max_retries

    Returns:
        BaseASR instance

    Raises:
        ValueError: If provider is not supported or required fields are missing
    """
    _ = db_model
    # 当前部署已移除 xinference 依赖，语音识别能力不再从该入口创建。
    raise ValueError("Unsupported ASR provider: current deployment only keeps OpenAI-compatible text/image model chains.")


def get_asr_model(
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> BaseASR:
    """
    Factory function to get ASR model instance by provider.

    Args:
        provider: Model provider name
        model: Model name/identifier
        api_key: API key for the provider
        **kwargs: Additional provider-specific parameters

    Returns:
        ASR model instance

    Raises:
        ValueError: If provider is not supported
    """
    _ = provider, model, api_key, kwargs
    raise ValueError("Unsupported ASR provider: current deployment only keeps OpenAI-compatible text/image model chains.")


__all__ = [
    "get_asr_model_instance",
    "get_asr_model",
    "BaseASR",
    "ASRResult",
    "ASRSegment",
]
