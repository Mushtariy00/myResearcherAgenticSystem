"""Executor settings from ARP_* environment variables or the repo-root .env (see .env.example)."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentic_core.gpu_jobs import DEFAULT_MAX_TRAIN_HOURS
from agentic_executor.template import SandboxLimits

# The same default as the worker's: job files live next to the paper library.
DEFAULT_DATA_DIR = "~/.local/share/arp"


class ExecutorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARP_", env_file=".env", extra="ignore")

    database_url: str = ""
    # Wake-ups for SSE streams after an experiment.epoch event (best effort, as the worker's).
    valkey_url: str = "redis://localhost:6379/0"
    data_dir: Path = Field(default=Path(DEFAULT_DATA_DIR), validate_default=True)  # jobs/<id>
    # The Docker API, through the socket proxy's Unix socket (infra/compose/compose.yaml). The
    # executor never opens /var/run/docker.sock itself.
    docker_socket: Path = Path(".data/docker-proxy/docker.sock")
    docker_api_version: str = "v1.47"
    sandbox_image: str = "arp-sandbox-pytorch:dev"

    # The container template's limits (docs/adr/0006-gpu-sandbox-hardened-docker.md). tmpfs counts
    # against the memory limit, so the memory must hold the training plus /tmp and the output.
    gpu_device: str = "0"
    sandbox_memory_mb: int = Field(default=3072, ge=512)
    sandbox_cpus: float = Field(default=3.0, gt=0)
    sandbox_pids: int = Field(default=256, ge=32)
    sandbox_shm_mb: int = Field(default=2048, ge=64)
    sandbox_tmp_mb: int = Field(default=1024, ge=64)
    sandbox_out_mb: int = Field(default=512, ge=64)
    max_train_hours: float = Field(default=DEFAULT_MAX_TRAIN_HOURS, gt=0, le=72)

    # The VRAM preflight: a job starts only once this much GPU memory is free (another process
    # may be using the GPU). nvidia-smi is found on PATH; under WSL it is /usr/lib/wsl/lib.
    nvidia_smi: str = "nvidia-smi"
    min_free_vram_mb: int = Field(default=3072, ge=0)

    poll_seconds: float = Field(default=2.0, gt=0)  # how often an idle executor looks at the queue
    cancel_check_seconds: float = Field(default=1.0, gt=0)  # a cancel ends a job within 5 s
    stop_grace_seconds: int = Field(default=2, ge=0)  # SIGTERM, then SIGKILL after this long

    # Dataset folders on this machine, by dataset name, for datasets registered without a
    # host_path (the datasets table).
    dataset_nyu2: Path | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def _data_dir(cls, value: object) -> Path:
        # .env.example leaves ARP_DATA_DIR empty: that means the default.
        text = str(value).strip() if value is not None else ""
        return Path(text or DEFAULT_DATA_DIR).expanduser()

    @field_validator("dataset_nyu2", mode="before")
    @classmethod
    def _optional_path(cls, value: object) -> Path | None:
        text = str(value).strip() if value is not None else ""
        return Path(text).expanduser() if text else None

    def dataset_path(self, name: str) -> Path | None:
        """This machine's folder for a dataset registered without a host_path, if set."""
        return {"nyu2": self.dataset_nyu2}.get(name)

    def limits(self) -> SandboxLimits:
        return SandboxLimits(
            memory_mb=self.sandbox_memory_mb,
            cpus=self.sandbox_cpus,
            pids=self.sandbox_pids,
            shm_mb=self.sandbox_shm_mb,
            tmp_mb=self.sandbox_tmp_mb,
            out_mb=self.sandbox_out_mb,
            gpu_device=self.gpu_device,
        )
