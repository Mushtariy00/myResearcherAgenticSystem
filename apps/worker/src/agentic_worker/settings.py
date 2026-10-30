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
    # offline (coding and experiment are then demo too).
    llm_stages: Literal["real", "demo"] = "real"
    # The coding and experiment stages (docs/design/experiments.md). "real" writes the model with
    # the LLM and runs it on the GPU through the executor (make executor); "demo" keeps their
    # generated outputs, for machines without a GPU.
    gpu_stages: Literal["real", "demo"] = "real"
    # The experiment's training run: its epochs, and the training steps of each, a share of the
    # dataset's training split per epoch, so that one run fits in an hour or so on one GPU.
    experiment_epochs: int = Field(default=3, ge=1, le=50)
    experiment_steps_per_epoch: int = Field(default=1000, ge=10, le=100_000)
    # Its wall clock, which the executor caps at its own ARP_MAX_TRAIN_HOURS.
    max_train_hours: float = Field(default=6.0, gt=0, le=72)

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
