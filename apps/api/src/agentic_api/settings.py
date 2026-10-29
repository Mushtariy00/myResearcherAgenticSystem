"""Runtime settings, read from ``ARP_*`` environment variables.

Secrets (database password, session secret) are added in Phase 1 and come from Docker secret
files, never from defaults in code.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARP_", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    # Origin the browser uses (Caddy). State-changing requests must come from it (CSRF check).
    public_origin: str = "http://localhost:8080"
    temporal_address: str = "localhost:7233"
    valkey_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
