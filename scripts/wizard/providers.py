"""LLM provider definitions for the Setup Wizard."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMProvider:
    name: str
    display_name: str
    description: str
    use: str
    models: list[str]
    default_model: str
    env_var: str | None
    package: str | None
    # Optional: some providers use a different field name for the API key in YAML
    api_key_field: str = "api_key"
    # Extra config fields beyond the common ones (merged into YAML)
    extra_config: dict = field(default_factory=dict)
    auth_hint: str | None = None


LLM_PROVIDERS: list[LLMProvider] = [
    LLMProvider(
        name="openai",
        display_name="OpenAI",
        description="GPT-4o, GPT-4.1, o3",
        use="langchain_openai:ChatOpenAI",
        models=["gpt-4o", "gpt-4.1", "o3"],
        default_model="gpt-4o",
        env_var="OPENAI_API_KEY",
        package="langchain-openai",
    ),
    LLMProvider(
        name="anthropic",
        display_name="Anthropic",
        description="Claude Opus 4, Sonnet 4",
        use="langchain_anthropic:ChatAnthropic",
        models=["claude-opus-4-5", "claude-sonnet-4-5"],
        default_model="claude-sonnet-4-5",
        env_var="ANTHROPIC_API_KEY",
        package="langchain-anthropic",
        extra_config={"max_tokens": 8192},
    ),
    LLMProvider(
        name="deepseek",
        display_name="DeepSeek",
        description="V3, R1",
        use="langchain_deepseek:ChatDeepSeek",
        models=["deepseek-chat", "deepseek-reasoner"],
        default_model="deepseek-chat",
        env_var="DEEPSEEK_API_KEY",
        package="langchain-deepseek",
    ),
    LLMProvider(
        name="google",
        display_name="Google Gemini",
        description="2.0 Flash, 2.5 Pro",
        use="langchain_google_genai:ChatGoogleGenerativeAI",
        models=["gemini-2.0-flash", "gemini-2.5-pro"],
        default_model="gemini-2.0-flash",
        env_var="GEMINI_API_KEY",
        package="langchain-google-genai",
        api_key_field="gemini_api_key",
    ),
    LLMProvider(
        name="openrouter",
        display_name="OpenRouter",
        description="OpenAI-compatible gateway with broad model catalog",
        use="langchain_openai:ChatOpenAI",
        models=["google/gemini-2.5-flash-preview", "openai/gpt-5-mini", "anthropic/claude-sonnet-4"],
        default_model="google/gemini-2.5-flash-preview",
        env_var="OPENROUTER_API_KEY",
        package="langchain-openai",
        extra_config={
            "base_url": "https://openrouter.ai/api/v1",
            "request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 8192,
            "temperature": 0.7,
        },
    ),
    LLMProvider(
        name="vllm",
        display_name="vLLM",
        description="Self-hosted OpenAI-compatible serving",
        use="deerflow.models.vllm_provider:VllmChatModel",
        models=["Qwen/Qwen3-32B", "Qwen/Qwen2.5-Coder-32B-Instruct"],
        default_model="Qwen/Qwen3-32B",
        env_var="VLLM_API_KEY",
        package=None,
        extra_config={
            "base_url": "http://localhost:8000/v1",
            "request_timeout": 600.0,
            "max_retries": 2,
            "max_tokens": 8192,
            "supports_thinking": True,
            "supports_vision": False,
            "when_thinking_enabled": {
                "extra_body": {
                    "chat_template_kwargs": {
                        "enable_thinking": True,
                    }
                }
            },
        },
    ),
    LLMProvider(
        name="codex",
        display_name="Codex CLI",
        description="Uses Codex CLI local auth (~/.codex/auth.json)",
        use="deerflow.models.openai_codex_provider:CodexChatModel",
        models=["gpt-5.4", "gpt-5-mini"],
        default_model="gpt-5.4",
        env_var=None,
        package=None,
        api_key_field="api_key",
        extra_config={"supports_thinking": True, "supports_reasoning_effort": True},
        auth_hint="Uses existing Codex CLI auth from ~/.codex/auth.json",
    ),
    LLMProvider(
        name="claude_code",
        display_name="Claude Code OAuth",
        description="Uses Claude Code local OAuth credentials",
        use="deerflow.models.claude_provider:ClaudeChatModel",
        models=["claude-sonnet-4-6", "claude-opus-4-1"],
        default_model="claude-sonnet-4-6",
        env_var=None,
        package=None,
        extra_config={"max_tokens": 4096, "supports_thinking": True},
        auth_hint="Uses Claude Code OAuth credentials from your local machine",
    ),
    LLMProvider(
        name="other",
        display_name="Other OpenAI-compatible",
        description="Custom gateway with base_url and model name",
        use="langchain_openai:ChatOpenAI",
        models=["gpt-4o"],
        default_model="gpt-4o",
        env_var="OPENAI_API_KEY",
        package="langchain-openai",
    ),
]
