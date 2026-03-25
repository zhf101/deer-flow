from ....model import ChatModelConfig, ModelConfig
from ....retry import create_retry_wrapper
from ..error import retry_on
from .base import BaseLLM
from .openai import OpenAILLM
# 历史多 provider 导入先保留为注释，避免直接删除原始实现。
# import os
# from .azure_openai import AzureOpenAILLM
# from .claude import ClaudeLLM
# from .gemini import GeminiLLM
# from .xinference import XinferenceLLM
# from .zhipu import ZhipuLLM


def create_base_llm(model: ModelConfig) -> BaseLLM:
    """
    Creates a custom BaseLLM instance from a ModelConfig.
    """
    if not isinstance(model, ChatModelConfig):
        raise TypeError(f"Invalid model type: {type(model).__name__}")

    if model.model_provider == "openai":
        llm: BaseLLM = OpenAILLM(
            model_name=model.model_name,
            api_key=model.api_key,
            base_url=model.base_url,
            default_temperature=model.default_temperature,
            default_max_tokens=model.default_max_tokens,
            timeout=model.timeout,
            abilities=model.abilities,
        )
    # 下面这组历史 OpenAI 兼容 provider 分支先保留为注释，当前部署不启用。
    # elif model.model_provider in (
    #     "alibaba-coding-plan",
    #     "alibaba-coding-plan-cn",
    #     "zai-coding-plan",
    #     "zhipuai-coding-plan",
    # ):
    #     llm = OpenAILLM(
    #         model_name=model.model_name,
    #         api_key=model.api_key,
    #         base_url=model.base_url,
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    # 下面这组 coding plan 历史实现先保留为注释，避免直接删除你的原始代码。
    # 若后续要重新启用，需要恢复 ClaudeLLM 导入并重新安装对应 SDK。
    # elif model.model_provider in (
    #     "minimax-coding-plan",
    #     "minimax-cn-coding-plan",
    #     "kimi-for-coding",
    # ):
    #     llm = ClaudeLLM(
    #         model_name=model.model_name,
    #         api_key=model.api_key,
    #         base_url=model.base_url,
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    # elif model.model_provider == "azure_openai":
    #     llm = AzureOpenAILLM(
    #         model_name=model.model_name,
    #         azure_endpoint=model.base_url,  # Reuse base_url as azure_endpoint
    #         api_key=model.api_key,
    #         api_version=os.getenv("OPENAI_API_VERSION", "2024-08-01-preview"),
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    # 以下历史 provider 分支先保留为注释，当前部署不启用。
    # elif model.model_provider == "zhipu":
    #     llm = ZhipuLLM(
    #         model_name=model.model_name,
    #         api_key=model.api_key,
    #         base_url=model.base_url,
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    # elif model.model_provider == "gemini":
    #     llm = GeminiLLM(
    #         model_name=model.model_name,
    #         api_key=model.api_key,
    #         base_url=model.base_url,
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    # elif model.model_provider == "claude":
    #     llm = ClaudeLLM(
    #         model_name=model.model_name,
    #         api_key=model.api_key,
    #         base_url=model.base_url,
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    # elif model.model_provider == "xinference":
    #     llm = XinferenceLLM(
    #         model_name=model.model_name,
    #         base_url=model.base_url,
    #         api_key=model.api_key,
    #         default_temperature=model.default_temperature,
    #         default_max_tokens=model.default_max_tokens,
    #         timeout=model.timeout,
    #         abilities=model.abilities,
    #     )
    else:
        raise TypeError(f"Unsupported LLM model type: {model.model_provider}")

    return create_retry_wrapper(
        llm,
        BaseLLM,  # type: ignore[type-abstract]
        retry_methods={"chat", "vision_chat", "stream_chat"},
        retry_on=retry_on,
    )
