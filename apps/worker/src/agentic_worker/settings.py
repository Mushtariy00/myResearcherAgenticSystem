"""Worker settings from ARP_* environment variables or the repo-root .env (see .env.example)."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARP_", env_file=".env", extra="ignore")

    database_url: str = ""
    valkey_url: str = "redis://localhost:6379/0"
    temporal_address: str = "localhost:7233"
    gateway_url: str = "http://127.0.0.1:8100"
    gateway_token: SecretStr = SecretStr("")
    max_concurrent_activities: int = 4  # the dev box has 4 cores and 7.7 GiB
    # How long each simulated (demo) stage takes; a run's config may override it per run.
    demo_stage_seconds: float = Field(default=6.0, ge=0)
