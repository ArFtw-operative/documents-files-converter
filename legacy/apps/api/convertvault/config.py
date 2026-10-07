from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "ConvertVault"
    app_env: Literal["development", "test", "production"] = "development"
    app_url: str = "http://localhost:3000"
    secret_key: str = "development-only-secret-change-before-production"
    database_url: str = "sqlite:///./data/convertvault.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    storage_provider: Literal["local", "s3"] = "local"
    local_storage_path: str = "./data/files"
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "convertvault"
    s3_secret_key: str = "development-only"
    s3_bucket: str = "convertvault"
    s3_region: str = "us-east-1"
    max_upload_size: int = 512 * 1024 * 1024
    max_batch_size: int = 20
    default_user_quota: int = 10 * 1024 * 1024 * 1024
    trash_retention_days: int = 30
    enable_public_sharing: bool = False
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_cookie_secure: bool = False
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    job_timeout_image: int = 600
    job_timeout_pdf: int = 1800
    job_timeout_office: int = 900
    job_timeout_general: int = 900

    @field_validator("secret_key")
    @classmethod
    def secure_production_key(cls, value: str, info):
        if info.data.get("app_env") == "production" and len(value) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters in production")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
