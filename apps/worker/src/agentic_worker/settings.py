"""Worker settings from ARP_* environment variables or the repo-root .env (see .env.example)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Outside the repo: the Next dev server watches the repo and would reload on every new PDF.
DEFAULT_DATA_DIR = "~/.local/share/arp"


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
    # The method and writing stages. "demo" keeps their generated demo outputs, for working
    # offline; coding and experiment stay demo until Phase 3 either way.
    llm_stages: Literal["real", "demo"] = "real"

    # Literature stage (docs/design/literature.md). "demo" keeps the real plan with a generated
    # search, for working offline.
    literature_search: Literal["real", "demo"] = "real"
    data_dir: Path = Field(default=Path(DEFAULT_DATA_DIR), validate_default=True)  # PDFs
    # The contact in the scholarly APIs' User-Agent and the email Unpaywall needs (skipped
    # without one).
    contact_email: str = ""
    openalex_api_key: SecretStr = SecretStr("")
    s2_api_key: SecretStr = SecretStr("")
    core_api_key: SecretStr = SecretStr("")  # CORE is skipped without one
    grobid_url: str = "http://127.0.0.1:8070"

    @field_validator("data_dir", mode="before")
    @classmethod
    def _data_dir(cls, value: object) -> Path:
        # .env.example leaves ARP_DATA_DIR empty: that means the default.
        text = str(value).strip() if value is not None else ""
        return Path(text or DEFAULT_DATA_DIR).expanduser()

    @field_validator("contact_email")
    @classmethod
    def _contact(cls, value: str) -> str:
        return value.strip()
