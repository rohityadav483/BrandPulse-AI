"""Application settings, loaded from environment variables and an optional `.env` file."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = ""
    database_url_direct: str = ""

    # SerpApi
    serpapi_api_key: SecretStr = SecretStr("")
    serpapi_account_label: str = "default"
    allow_live_serpapi: bool = False
    serp_monthly_limit: int = Field(250, ge=0)
    serp_monthly_reserve: int = Field(20, ge=0)
    serp_budget_per_analysis: int = Field(12, ge=0)
    serp_budget_per_investigation: int = Field(8, ge=0)
    serp_cache_ttl_hours: int = Field(720, ge=0)
    live_access_code: SecretStr = SecretStr("")

    # Limits
    max_analyses_per_day: int = Field(3, ge=0)
    max_concurrent_analyses: int = Field(1, ge=1)

    # Local NLP
    sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    hf_home: str = ""

    # Groq
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = ""
    llm_max_concurrency: int = Field(1, ge=1)
    llm_max_calls_per_investigation: int = Field(8, ge=0)

    # App
    demo_mode: bool = False
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_LOG_LEVELS)}")
        return level

    @model_validator(mode="after")
    def _check_reserve(self) -> "Settings":
        if self.serp_monthly_reserve > self.serp_monthly_limit:
            raise ValueError("serp_monthly_reserve must not exceed serp_monthly_limit")
        return self

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key.get_secret_value())

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key.get_secret_value())

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
