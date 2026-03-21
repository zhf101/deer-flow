import os
import threading

from pydantic import BaseModel, Field

_config_lock = threading.Lock()

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


class TracingConfig(BaseModel):
    """DeerFlow tracing configuration."""

    enabled: bool = Field(default=False)
    trace_log_path: str = Field(default="./logs/traces.jsonl")


class LangfuseConfig(BaseModel):
    """Configuration for Langfuse-based tracing."""

    public_key: str | None = Field(default=None)
    secret_key: str | None = Field(default=None)
    base_url: str = Field(default="https://cloud.langfuse.com")
    environment: str | None = Field(default=None)
    release: str | None = Field(default=None)

    @property
    def is_configured(self) -> bool:
        """Return ``True`` when Langfuse credentials are present."""
        return bool(self.public_key and self.secret_key)


_tracing_config: TracingConfig | None = None
_langfuse_config: LangfuseConfig | None = None


def _env_flag_preferred(*names: str) -> bool:
    """Return the boolean value of the first non-empty environment variable."""
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip().lower() in _TRUTHY_VALUES
    return False


def _first_env_value(*names: str) -> str | None:
    """Return the first non-empty environment value from candidate names."""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def get_tracing_config() -> TracingConfig:
    """Return the current DeerFlow tracing configuration."""
    global _tracing_config
    if _tracing_config is not None:
        return _tracing_config

    with _config_lock:
        if _tracing_config is not None:
            return _tracing_config

        _tracing_config = TracingConfig(
            enabled=_env_flag_preferred("DEERFLOW_TRACING_ENABLED", "LANGFUSE_TRACING_ENABLED"),
            trace_log_path=_first_env_value("DEERFLOW_TRACE_LOG_PATH") or "./logs/traces.jsonl",
        )
        return _tracing_config


def get_langfuse_config() -> LangfuseConfig:
    """Return the current Langfuse configuration."""
    global _langfuse_config
    if _langfuse_config is not None:
        return _langfuse_config

    with _config_lock:
        if _langfuse_config is not None:
            return _langfuse_config

        _langfuse_config = LangfuseConfig(
            public_key=_first_env_value("LANGFUSE_PUBLIC_KEY"),
            secret_key=_first_env_value("LANGFUSE_SECRET_KEY"),
            base_url=_first_env_value("LANGFUSE_BASE_URL", "LANGFUSE_HOST") or "https://cloud.langfuse.com",
            environment=_first_env_value("LANGFUSE_TRACING_ENVIRONMENT"),
            release=_first_env_value("LANGFUSE_RELEASE"),
        )
        return _langfuse_config


def is_tracing_enabled() -> bool:
    """Return ``True`` when DeerFlow tracing is enabled."""
    return get_tracing_config().enabled


def is_langfuse_enabled() -> bool:
    """Return ``True`` when tracing is enabled and Langfuse is fully configured."""
    return is_tracing_enabled() and get_langfuse_config().is_configured
