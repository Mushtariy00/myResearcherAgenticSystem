"""The one container template GPU jobs run in (docs/adr/0006-gpu-sandbox-hardened-docker.md).

Only this module decides what a job's container may do. Every value comes from the executor's
settings and the job's id, run, kind and dataset, never from the job's code or config.

The output folder is a tmpfs volume, which gives a hard size quota that WSL's ext4 can't give a
bind mount. It must be a volume rather than a plain tmpfs mount: Docker's archive API reads a
volume of a running container but not its tmpfs mounts. Its contents are gone once the container
stops, so harness.job keeps the container up after training until the executor has copied them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_core.enums import GpuJobKind
from agentic_core.gpu_jobs import (
    CODE_MOUNT,
    CONFIG_MOUNT,
    DATA_ROOT,
    JOB_LABEL,
    KIND_LABEL,
    OUT_DIR,
    RUN_LABEL,
)

SANDBOX_UID = 10001  # the image's unprivileged "sandbox" user and group
MIB = 1024**2
# If the host itself runs out of memory, a job's processes are killed before the dev stack's.
OOM_SCORE_ADJ = 500


@dataclass(frozen=True)
class SandboxLimits:
    memory_mb: int  # also the memory+swap limit: no swap
    cpus: float
    pids: int
    shm_mb: int
    tmp_mb: int  # /tmp, a tmpfs
    out_mb: int  # the output folder's quota, a tmpfs volume
    gpu_device: str  # the host GPU's index, such as "0"


@dataclass(frozen=True)
class JobMounts:
    """The host side of a job's read-only mounts."""

    dataset_name: str  # mounted at /data/<name>
    dataset_path: Path
    code_dir: Path  # ARP_DATA_DIR/jobs/<id>/code
    config_file: Path  # ARP_DATA_DIR/jobs/<id>/config.json


def container_name(job_id: object) -> str:
    """A job's container name. Docker refuses a second container of the same name, so a job can
    never get two containers, whatever crashes in between."""
    return f"arp-job-{job_id}"


def harness_args(kind: GpuJobKind) -> list[str]:
    """harness.job's arguments, which it passes on to harness.train. A smoke job is a dry run."""
    args = ["--config", CONFIG_MOUNT, "--out", OUT_DIR]
    return [*args, "--dry-run"] if kind is GpuJobKind.SMOKE else args


def container_spec(
    *,
    image: str,
    job_id: str,
    run_id: str,
    kind: GpuJobKind,
    mounts: JobMounts,
    limits: SandboxLimits,
) -> dict[str, Any]:
    """The POST /containers/create body for one job."""
    out_options = (
        f"size={limits.out_mb * MIB},uid={SANDBOX_UID},gid={SANDBOX_UID},mode=0700,nosuid,nodev"
    )
    return {
        "Image": image,
        "Entrypoint": ["python", "-m", "harness.job"],
        "Cmd": harness_args(kind),
        "User": f"{SANDBOX_UID}:{SANDBOX_UID}",
        "WorkingDir": "/workspace",
        # The image's own variables (PYTHONPATH, HOME=/tmp, ...) stay. Nothing secret is added:
        # the executor's environment never reaches the container.
        "Env": ["NVIDIA_DRIVER_CAPABILITIES=compute,utility"],
        "Labels": {JOB_LABEL: job_id, KIND_LABEL: kind.value, RUN_LABEL: run_id},
        "NetworkDisabled": True,
        "StopSignal": "SIGTERM",
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            # docker-init as PID 1 passes SIGTERM on to harness.job, which stops the training.
            "Init": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "PidsLimit": limits.pids,
            "Memory": limits.memory_mb * MIB,
            "MemorySwap": limits.memory_mb * MIB,
            "NanoCpus": round(limits.cpus * 1e9),
            "ShmSize": limits.shm_mb * MIB,
            "IpcMode": "private",
            "Ulimits": [{"Name": "core", "Soft": 0, "Hard": 0}],
            "OomScoreAdj": OOM_SCORE_ADJ,
            "RestartPolicy": {"Name": "no"},
            "AutoRemove": False,  # the executor removes it, once it has copied the output
            "LogConfig": {"Type": "local", "Config": {"max-size": "20m", "max-file": "2"}},
            # The container's own /tmp, a size-limited tmpfs, not the host's.
            "Tmpfs": {"/tmp": f"rw,nosuid,nodev,size={limits.tmp_mb * MIB}"},  # noqa: S108
            "Mounts": [
                _read_only_bind(mounts.dataset_path, f"{DATA_ROOT}/{mounts.dataset_name}"),
                _read_only_bind(mounts.code_dir, CODE_MOUNT),
                _read_only_bind(mounts.config_file, CONFIG_MOUNT),
                {
                    # Anonymous, so removing the container with v=1 removes it too.
                    "Type": "volume",
                    "Target": OUT_DIR,
                    "VolumeOptions": {
                        "DriverConfig": {
                            "Name": "local",
                            "Options": {"type": "tmpfs", "device": "tmpfs", "o": out_options},
                        }
                    },
                },
            ],
            # --gpus device=<index>
            "DeviceRequests": [
                {
                    "Driver": "",
                    "Count": 0,
                    "DeviceIDs": [limits.gpu_device],
                    "Capabilities": [["gpu"]],
                }
            ],
        },
    }


def _read_only_bind(source: Path, target: str) -> dict[str, Any]:
    return {"Type": "bind", "Source": str(source), "Target": target, "ReadOnly": True}
