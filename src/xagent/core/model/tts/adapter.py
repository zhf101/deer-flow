"""TTS model adapter factory."""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseTTS


def get_tts_model_instance(db_model: Any) -> BaseTTS:
    """
    Create a BaseTTS instance from a database model record.

    Args:
        db_model: Database model instance with fields: model_name, model_provider,
                  api_key, base_url, abilities, timeout, max_retries

    Returns:
        BaseTTS instance

    Raises:
        ValueError: If provider is not supported or required fields are missing
    """
    _ = db_model
    # 当前部署已移除 xinference 依赖，语音合成能力不再从该入口创建。
    raise ValueError("Unsupported TTS provider: current deployment only keeps OpenAI-compatible text/image model chains.")


def get_tts_model(
    provider: str = "openai",
    model: Optional[str] = None,
    **kwargs: Any,
) -> BaseTTS:
    """
    Get a TTS model instance by provider.

    Args:
        provider: TTS provider name
        model: Model name (provider-specific)
        **kwargs: Additional provider-specific parameters

    Returns:
        A TTS model instance

    Raises:
        ValueError: If provider is not supported

    """
    _ = provider, model, kwargs
    raise ValueError("Unsupported TTS provider: current deployment only keeps OpenAI-compatible text/image model chains.")


__all__ = [
    "get_tts_model_instance",
    "get_tts_model",
]
