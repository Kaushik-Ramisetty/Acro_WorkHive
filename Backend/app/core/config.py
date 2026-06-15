import logging
import warnings
from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)

# Tokens that indicate a dev placeholder is still in use. We refuse to start
# in production with any of these, and warn loudly in non-production envs.
_INSECURE_SECRET_TOKENS = ("change-me", "dev-only", "replace-with", "your-")


def _looks_insecure(val: str) -> bool:
    if not val:
        return True
    lower = val.lower()
    return any(tok in lower for tok in _INSECURE_SECRET_TOKENS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "HRMS Backend"
    APP_ENV: str = "dev"
    DEBUG: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    DATABASE_URL: str = "sqlite:///./hrms.db"

    # Dev-friendly defaults preserved so `python run.py` works out of the box,
    # but we validate in __init__ that production environments override them.
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # 2FA OTP
    OTP_PEPPER: str = "change-me-pepper"
    OTP_TTL_SECONDS: int = 120

    # SMTP (Gmail / generic). When SMTP_USERNAME + SMTP_PASSWORD are empty,
    # the dispatcher falls back to logging the email to stdout (dev mode).
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""        # defaults to SMTP_USERNAME if empty
    SMTP_FROM_NAME: str = "WorkHive HRMS"
    SMTP_USE_TLS: bool = True
    CLIENT_ACTION_BASE_URL: str = "http://localhost:8000"

    @property
    def allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return (self.APP_ENV or "").lower() in ("production", "prod")

    def validate_secrets(self) -> None:
        """Refuse to operate with dev placeholders in production.

        In non-production environments we only warn so that local dev keeps
        working with the shipped defaults. This is a Phase-1 hardening that
        does not change runtime behaviour for dev, but stops a misconfigured
        production deploy at startup before any token is ever issued.
        """
        problems: List[str] = []
        if _looks_insecure(self.JWT_SECRET):
            problems.append("JWT_SECRET")
        if _looks_insecure(self.OTP_PEPPER):
            problems.append("OTP_PEPPER")
        if not problems:
            return
        if self.is_production:
            raise RuntimeError(
                "Refusing to start in production with insecure placeholder "
                f"value(s) for: {', '.join(problems)}. Set strong random "
                "values in the environment (see .env.example)."
            )
        msg = (
            "Using dev placeholder value(s) for "
            f"{', '.join(problems)}; OK for local development but MUST be "
            "overridden before deploying to production."
        )
        logger.warning(msg)
        warnings.warn(msg, RuntimeWarning, stacklevel=2)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.validate_secrets()
    return s


settings = get_settings()
