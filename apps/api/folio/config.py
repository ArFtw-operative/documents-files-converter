from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FOLIO_", env_file=".env.folio", extra="ignore")

    app_name: str = "Verso Folio"
    env: Literal["development", "test", "production"] = "development"
    public_url: str = "http://localhost:5173"
    secret_key: str = "development-only-secret-change-me-before-production-use"
    database_url: str = "sqlite:///./data-folio/folio.db"
    valkey_url: str | None = None  # redis:// URL of Valkey; None = in-process events (dev/test)
    data_dir: str = "./data-folio/storage"

    # "inline" runs the document engine in the API process (dev/test). "worker" dispatches every
    # PDF parse/mutation to the sandboxed CPU worker (production, architecture §44.2).
    engine_mode: Literal["inline", "worker"] = "inline"
    engine_timeout_seconds: int = 180

    max_upload_bytes: int = 200 * 1024 * 1024
    max_pages: int = 2000
    default_quota_bytes: int = 10 * 1024 * 1024 * 1024
    registration_open: bool = False

    session_idle_hours: int = 12
    session_absolute_days: int = 7
    cookie_secure: bool = False
    login_max_failures: int = 8
    login_lock_minutes: int = 15

    @field_validator("secret_key")
    @classmethod
    def strong_secret(cls, value: str, info):
        if info.data.get("env") == "production" and (len(value) < 48 or "change-me" in value):
            raise ValueError("FOLIO_SECRET_KEY must be a random value of at least 48 characters")
        return value

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
