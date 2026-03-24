import os

JWT_SECRET_KEY = os.getenv("XAGENT_JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("XAGENT_JWT_ALGORITHM", "HS256")


def _get_positive_int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed = int(value)
        if parsed <= 0:
            return default
        return parsed
    except ValueError:
        return default


def _get_bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


ACCESS_TOKEN_EXPIRE_MINUTES = _get_positive_int_from_env(
    "XAGENT_ACCESS_TOKEN_EXPIRE_MINUTES", 120
)
REFRESH_TOKEN_EXPIRE_DAYS = _get_positive_int_from_env(
    "XAGENT_REFRESH_TOKEN_EXPIRE_DAYS", 7
)
PASSWORD_MIN_LENGTH = _get_positive_int_from_env("XAGENT_PASSWORD_MIN_LENGTH", 6)
LOCAL_REGISTRATION_ENABLED = _get_bool_from_env(
    "XAGENT_LOCAL_REGISTRATION_ENABLED", False
)

# 旧系统 SSO 验票配置。
# 这里不直接把旧系统地址写死在代码里，避免不同环境切换时还要改代码。
LEGACY_SSO_VERIFY_URL = os.getenv("XAGENT_LEGACY_SSO_VERIFY_URL", "").strip()
LEGACY_SSO_SUCCESS_CODE = os.getenv("XAGENT_LEGACY_SSO_SUCCESS_CODE", "GDP001").strip()
LEGACY_SSO_TIMEOUT_SECONDS = _get_positive_int_from_env(
    "XAGENT_LEGACY_SSO_TIMEOUT_SECONDS", 10
)
