"""Runtime settings, read from ``ARP_*`` environment variables (and `.env` in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = "~/.local/share/arp"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARP_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    # Origin the browser uses (Caddy). State-changing requests must come from it (CSRF check).
    public_origin: str = "http://localhost:8080"
    database_url: str = ""
    temporal_address: str = "localhost:7233"
    valkey_url: str = "redis://localhost:6379/0"
    # Base URL of the Next.js app, where Better Auth checks session cookies.
    auth_url: str = "http://127.0.0.1:3000"
    auth_cache_seconds: int = 60
    # Internal LLM gateway (the workers call it); the admin health page checks its /v1/health.
    gateway_url: str = "http://127.0.0.1:8100"
    # The gateway's model chains and free-tier limit, read from the same ARP_* variables so the
    # admin pages and the cost estimate show what the gateway uses. Empty chains: its defaults.
    paid_models: str = ""
    free_models: str = ""
    free_requests_per_day: int = 50
    # Where the worker stores files: the papers' PDFs under papers/ (agentic_scholarly.storage).
    # Empty means the default, outside the repo, because the Next dev server watches the repo.
    data_dir: Path = Field(default=Path(DEFAULT_DATA_DIR), validate_default=True)

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: object) -> Path:
        # The worker's rule (agentic_worker.settings), so both find the same files.
        text = str(value).strip() if value is not None else ""
        return Path(text or DEFAULT_DATA_DIR).expanduser()


@lru_cache
def get_settings() -> Settings:
    return Settings()
