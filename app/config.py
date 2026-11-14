"""Application settings, loaded from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Never a real secret. Only tolerated outside production, and the validator
# below refuses to boot in production while this is still in place.
_DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Nawa"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False

    # Auth
    secret_key: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    audio_token_minutes: int = 60

    # Data
    database_url: str = "sqlite:///./nawa.db"

    # Limits
    max_text_chars: int = 4000
    max_chunks: int = 24
    max_generations_per_day: int = 40
    synth_concurrency: int = 3

    # Web
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    rate_limit_enabled: bool = True

    @field_validator("secret_key")
    @classmethod
    def _reject_default_in_production(cls, value: str, info) -> str:
        environment = (info.data or {}).get("environment", "development")
        if environment == "production" and value == _DEV_SECRET:
            raise ValueError(
                "SECRET_KEY must be set to a unique value in production. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
