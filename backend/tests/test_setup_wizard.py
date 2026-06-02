"""Unit tests for the Setup Wizard (scripts/wizard/)."""

from __future__ import annotations

import yaml
from wizard.providers import LLM_PROVIDERS
from wizard.steps import search as search_step
from wizard.writer import (
    build_minimal_config,
    read_env_file,
    write_config_yaml,
    write_env_file,
)


class TestProviders:
    def test_llm_providers_not_empty(self):
        assert len(LLM_PROVIDERS) >= 8

    def test_llm_providers_have_required_fields(self):
        for provider in LLM_PROVIDERS:
            assert provider.name
            assert provider.display_name
            assert provider.use
            assert ":" in provider.use
            assert provider.models
            assert provider.default_model in provider.models


class TestBuildMinimalConfig:
    def test_produces_valid_yaml(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI / gpt-4o",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(content)
        model = data["models"][0]
        assert model["name"] == "gpt-4o"
        assert model["use"] == "langchain_openai:ChatOpenAI"
        assert model["model"] == "gpt-4o"
        assert model["api_key"] == "$OPENAI_API_KEY"

    def test_gemini_uses_gemini_api_key_field(self):
        content = build_minimal_config(
            provider_use="langchain_google_genai:ChatGoogleGenerativeAI",
            model_name="gemini-2.0-flash",
            display_name="Gemini",
            api_key_field="gemini_api_key",
            env_var="GEMINI_API_KEY",
        )
        data = yaml.safe_load(content)
        model = data["models"][0]
        assert model["gemini_api_key"] == "$GEMINI_API_KEY"
        assert "api_key" not in model

    def test_does_not_emit_removed_web_tools(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(content)
        tool_names = [tool["name"] for tool in data.get("tools", [])]
        assert set(tool_names) == {"ls", "read_file", "glob", "grep", "write_file", "str_replace"}

    def test_sandbox_included(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(content)
        assert data["sandbox"]["use"] == "deerflow.sandbox.local:LocalSandboxProvider"
        assert data["sandbox"]["allow_host_bash"] is False

    def test_bash_tool_disabled_by_default(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(content)
        tool_names = [tool["name"] for tool in data.get("tools", [])]
        assert "bash" not in tool_names

    def test_can_enable_container_sandbox_and_bash(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
            sandbox_use="deerflow.community.aio_sandbox:AioSandboxProvider",
            include_bash_tool=True,
        )
        data = yaml.safe_load(content)
        assert data["sandbox"]["use"] == "deerflow.community.aio_sandbox:AioSandboxProvider"
        assert "allow_host_bash" not in data["sandbox"]
        assert any(tool["name"] == "bash" for tool in data["tools"])

    def test_can_disable_write_tools(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
            include_write_tools=False,
        )
        data = yaml.safe_load(content)
        tool_names = [tool["name"] for tool in data.get("tools", [])]
        assert "write_file" not in tool_names
        assert "str_replace" not in tool_names

    def test_config_version_present(self):
        content = build_minimal_config(
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
            config_version=5,
        )
        data = yaml.safe_load(content)
        assert data["config_version"] == 5

    def test_cli_provider_does_not_emit_fake_api_key(self):
        content = build_minimal_config(
            provider_use="deerflow.models.openai_codex_provider:CodexChatModel",
            model_name="gpt-5.4",
            display_name="Codex CLI",
            api_key_field="api_key",
            env_var=None,
        )
        data = yaml.safe_load(content)
        assert "api_key" not in data["models"][0]


class TestEnvFileHelpers:
    def test_write_and_read_new_file(self, tmp_path):
        env_file = tmp_path / ".env"
        write_env_file(env_file, {"OPENAI_API_KEY": "sk-test123"})
        pairs = read_env_file(env_file)
        assert pairs["OPENAI_API_KEY"] == "sk-test123"

    def test_update_existing_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=old-key\n")
        write_env_file(env_file, {"OPENAI_API_KEY": "new-key"})
        pairs = read_env_file(env_file)
        assert pairs["OPENAI_API_KEY"] == "new-key"
        assert env_file.read_text().count("OPENAI_API_KEY") == 1

    def test_preserve_existing_keys(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("CUSTOM_KEY=custom-val\n")
        write_env_file(env_file, {"OPENAI_API_KEY": "sk-new"})
        pairs = read_env_file(env_file)
        assert pairs["CUSTOM_KEY"] == "custom-val"
        assert pairs["OPENAI_API_KEY"] == "sk-new"

    def test_preserve_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# My .env file\nOPENAI_API_KEY=old\n")
        write_env_file(env_file, {"OPENAI_API_KEY": "new"})
        assert "# My .env file" in env_file.read_text()

    def test_read_ignores_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\nKEY=value\n")
        pairs = read_env_file(env_file)
        assert "# comment" not in pairs
        assert pairs["KEY"] == "value"


class TestWriteConfigYaml:
    def test_generated_config_loadable_by_appconfig(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        write_config_yaml(
            config_path,
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI / gpt-4o",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(config_path.read_text())
        assert isinstance(data, dict)
        assert "models" in data

    def test_copies_example_defaults_for_unconfigured_sections(self, tmp_path):
        example_path = tmp_path / "config.example.yaml"
        example_path.write_text(
            yaml.safe_dump(
                {
                    "config_version": 5,
                    "log_level": "info",
                    "token_usage": {"enabled": True},
                    "tool_groups": [
                        {"name": "web"},
                        {"name": "file:read"},
                        {"name": "file:write"},
                        {"name": "bash"},
                    ],
                    "tools": [
                        {"name": "ls", "group": "file:read", "use": "deerflow.sandbox.tools:ls_tool"},
                        {"name": "write_file", "group": "file:write", "use": "deerflow.sandbox.tools:write_file_tool"},
                        {"name": "bash", "group": "bash", "use": "deerflow.sandbox.tools:bash_tool"},
                    ],
                    "sandbox": {
                        "use": "deerflow.sandbox.local:LocalSandboxProvider",
                        "allow_host_bash": False,
                    },
                    "summarization": {"max_tokens": 2048},
                },
                sort_keys=False,
            )
        )

        config_path = tmp_path / "config.yaml"
        write_config_yaml(
            config_path,
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI / gpt-4o",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(config_path.read_text())
        assert data["log_level"] == "info"
        assert data["token_usage"]["enabled"] is True
        assert all(group["name"] != "web" for group in data["tool_groups"])
        assert data["summarization"]["max_tokens"] == 2048
        assert {tool["name"] for tool in data["tools"]} == {"ls", "write_file", "str_replace"}

    def test_config_version_read_from_example(self, tmp_path):
        example_path = tmp_path / "config.example.yaml"
        example_path.write_text("config_version: 99\n")

        config_path = tmp_path / "config.yaml"
        write_config_yaml(
            config_path,
            provider_use="langchain_openai:ChatOpenAI",
            model_name="gpt-4o",
            display_name="OpenAI",
            api_key_field="api_key",
            env_var="OPENAI_API_KEY",
        )
        data = yaml.safe_load(config_path.read_text())
        assert data["config_version"] == 99

    def test_model_base_url_from_extra_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        write_config_yaml(
            config_path,
            provider_use="langchain_openai:ChatOpenAI",
            model_name="google/gemini-2.5-flash-preview",
            display_name="OpenRouter",
            api_key_field="api_key",
            env_var="OPENROUTER_API_KEY",
            extra_model_config={"base_url": "https://openrouter.ai/api/v1"},
        )
        data = yaml.safe_load(config_path.read_text())
        assert data["models"][0]["base_url"] == "https://openrouter.ai/api/v1"


class TestSearchStep:
    def test_returns_no_external_web_providers(self, monkeypatch):
        messages: list[str] = []
        monkeypatch.setattr(search_step, "print_header", lambda *args, **kwargs: None)
        monkeypatch.setattr(search_step, "print_info", lambda message: messages.append(message))

        result = search_step.run_search_step()

        assert result.search_provider is None
        assert result.search_api_key is None
        assert result.fetch_provider is None
        assert result.fetch_api_key is None
        assert messages
