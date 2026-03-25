"""历史 Zhipu 对话模型测试保留文件。

当前部署已统一为标准 OpenAI 兼容格式接入，Zhipu 专项对话测试不再参与执行。
以下原始测试代码按注释保留，便于后续需要时恢复。
"""

# """Test cases for Zhipu LLM implementation."""
#
# from unittest.mock import MagicMock, patch
#
# import pytest
#
# from xagent.core.model.chat.basic.zhipu import ZhipuLLM
#
#
# class TestZhipuLLM:
#     """Test cases for ZhipuLLM class."""
#
#     @pytest.fixture
#     def mock_zhipu_client(self):
#         pass
#
#     @pytest.fixture
#     def zhipu_llm(self, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_normal_text_response(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_none_content_response(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_empty_content_response(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_tool_call_response(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_none_api_response(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_response_missing_choices(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_thinking_mode_disabled(self, zhipu_llm, mock_zhipu_client):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_empty_string_api_key_fallback(self, monkeypatch):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_none_api_key_with_env_fallback(self, monkeypatch):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_none_api_key_with_openai_env_fallback(self, monkeypatch):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_missing_api_key_initialization(self, monkeypatch):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_explicit_api_key_not_overridden(self, monkeypatch):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_list_available_models_with_default_base_url(self, mocker):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_list_available_models_with_custom_base_url(self, mocker):
#         pass
#
#     @pytest.mark.asyncio
#     async def test_list_available_models_unauthorized(self, mocker):
#         pass
