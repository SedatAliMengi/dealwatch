"""App settings, read from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database. Docker uses PostgreSQL; SQLite works for quick local runs.
    database_url: str = "sqlite:///./dealwatch.db"

    # Which PriceSource plug-in to use ("cheapshark" or "fake").
    price_source: str = "cheapshark"

    # Background price checker.
    scheduler_enabled: bool = True
    check_interval_hours: float = Field(default=6.0, gt=0)
    run_check_on_startup: bool = False

    # CheapShark etiquette: cache responses and space out requests.
    cheapshark_base_url: str = "https://www.cheapshark.com/api/1.0"
    cheapshark_cache_seconds: int = Field(default=600, ge=0)
    cheapshark_min_interval_seconds: float = Field(default=1.0, ge=0)
    http_timeout_seconds: float = Field(default=10.0, gt=0)

    # Comma-separated list of origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
