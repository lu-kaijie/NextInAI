"""Application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="NEXTINAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development")
    data_dir: Path = Field(default=Path("./data"))
    github_token: str | None = Field(default=None)
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "NEXTINAI_OPENAI_API_KEY"),
    )
    openai_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_BASE_URL", "NEXTINAI_OPENAI_BASE_URL"),
    )
    ai_provider: str = Field(default="openai")
    ai_model: str | None = Field(default=None)
    default_notification_email: EmailStr | None = Field(default=None)
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_username: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    webhook_base_url: str | None = Field(default=None)
    report_output_dir: Path = Field(default=Path("./artifacts/reports"))
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
