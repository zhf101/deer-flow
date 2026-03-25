"""历史 Azure LangChain 适配器测试保留文件。

当前部署已统一为标准 OpenAI 兼容格式接入，Azure LangChain 适配器测试不再参与执行。
以下原始测试代码按注释保留，便于后续需要时恢复。
"""

# """Tests for Azure OpenAI LangChain adapter."""
#
# import pytest
#
# from xagent.core.model import ChatModelConfig
# from xagent.core.model.chat.langchain import create_base_chat_model
#
#
# class TestAzureOpenAILangChainAdapter:
#     """Test suite for Azure OpenAI LangChain adapter."""
#
#     def test_create_azure_chat_model(self, mocker, monkeypatch):
#         pass
#
#     def test_azure_chat_model_with_temperature_override(self, mocker, monkeypatch):
#         pass
#
#     def test_azure_chat_model_uses_default_temperature(self, mocker, monkeypatch):
#         pass
#
#     def test_azure_api_version_from_env(self, mocker, monkeypatch):
#         pass
#
#     def test_azure_api_version_default(self, mocker, monkeypatch):
#         pass
#
#     def test_unsupported_provider_raises_error(self):
#         pass
#
#     def test_invalid_config_type_raises_error(self):
#         pass
#
#     def test_azure_openai_preserves_none_values(self, mocker, monkeypatch):
#         pass
