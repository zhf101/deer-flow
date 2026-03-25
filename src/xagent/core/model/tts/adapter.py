"""TTS model adapter factory."""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseTTS
# 历史多 provider 导入先保留为注释，避免直接删除原始实现。
# from .xinference import XinferenceTTS


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
    # 以下历史 xinference 实现先保留为注释，当前部署不启用。
    # provider = str(db_model.model_provider).lower()
    # model_name = str(db_model.model_name)
    # api_key = str(db_model.api_key) if db_model.api_key else None
    # base_url = str(db_model.base_url) if db_model.base_url else None
    #
    # if provider == "xinference":
    #     return XinferenceTTS(
    #         model=model_name,
    #         model_uid=model_name,
    #         base_url=base_url,
    #         api_key=api_key,
    #     )
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
    # 以下历史 xinference 工厂逻辑先保留为注释，当前部署不启用。
    # if provider == "xinference":
    #     return XinferenceTTS(model=model or "chat-tts", **kwargs)
    _ = provider, model, kwargs
    raise ValueError("Unsupported TTS provider: current deployment only keeps OpenAI-compatible text/image model chains.")


__all__ = [
    "get_tts_model_instance",
    "get_tts_model",
]
