"""The job container template holds the ADR 0006 flags. A security test: it pins down exactly what a
job's container may do, so loosening any flag has to change this file too."""

from pathlib import Path
from typing import Any

import pytest

from agentic_core.enums import GpuJobKind
from agentic_executor.template import (
    JobMounts,
    SandboxLimits,
    container_name,
    container_spec,
)

LIMITS = SandboxLimits(
    memory_mb=3072, cpus=3.0, pids=256, shm_mb=2048, tmp_mb=1024, out_mb=512, gpu_device="0"
)
MOUNTS = JobMounts(
    dataset_name="nyu2",
    dataset_path=Path("/srv/datasets/nyu2"),
    code_dir=Path("/srv/arp/jobs/j1/code"),
    config_file=Path("/srv/arp/jobs/j1/config.json"),
)


def spec(kind: GpuJobKind = GpuJobKind.TRAIN) -> dict[str, Any]:
    return container_spec(
        image="arp-sandbox-pytorch:dev",
        job_id="j1",
        run_id="r1",
        kind=kind,
        mounts=MOUNTS,
        limits=LIMITS,
    )


def test_the_template_sets_these_keys_and_no_others() -> None:
    body = spec()
    assert set(body) == {
        "Image",
        "Entrypoint",
        "Cmd",
        "User",
        "WorkingDir",
        "Env",
        "Labels",
        "NetworkDisabled",
        "StopSignal",
        "HostConfig",
    }
    assert set(body["HostConfig"]) == {
        "NetworkMode",
        "ReadonlyRootfs",
        "Privileged",
        "Init",
        "CapDrop",
        "SecurityOpt",
        "PidsLimit",
        "Memory",
        "MemorySwap",
        "NanoCpus",
        "ShmSize",
        "IpcMode",
        "Ulimits",
        "OomScoreAdj",
        "RestartPolicy",
        "AutoRemove",
        "LogConfig",
        "Tmpfs",
        "Mounts",
        "DeviceRequests",
    }


def test_no_network_read_only_root_unprivileged_user() -> None:
    body = spec()
    host = body["HostConfig"]
    assert body["NetworkDisabled"] is True
    assert host["NetworkMode"] == "none"
    assert host["ReadonlyRootfs"] is True
    assert host["Privileged"] is False
    assert body["User"] == "10001:10001"
    assert host["CapDrop"] == ["ALL"]
    # Only no-new-privileges: Docker's default seccomp and AppArmor profiles stay on.
    assert host["SecurityOpt"] == ["no-new-privileges"]
    assert host["IpcMode"] == "private"
    assert host["RestartPolicy"] == {"Name": "no"}


def test_resource_limits() -> None:
    host = spec()["HostConfig"]
    assert host["Memory"] == host["MemorySwap"] == 3072 * 1024**2  # no swap
    assert host["PidsLimit"] == 256
    assert host["NanoCpus"] == 3_000_000_000
    assert host["ShmSize"] == 2048 * 1024**2
    assert host["Tmpfs"] == {"/tmp": "rw,nosuid,nodev,size=1073741824"}  # noqa: S108
    assert host["Ulimits"] == [{"Name": "core", "Soft": 0, "Hard": 0}]
    assert host["OomScoreAdj"] > 0


def test_every_bind_mount_is_read_only_and_the_output_is_a_tmpfs_volume() -> None:
    mounts = spec()["HostConfig"]["Mounts"]
    binds = [mount for mount in mounts if mount["Type"] == "bind"]
    assert {(mount["Source"], mount["Target"]) for mount in binds} == {
        ("/srv/datasets/nyu2", "/data/nyu2"),
        ("/srv/arp/jobs/j1/code", "/job/code"),
        ("/srv/arp/jobs/j1/config.json", "/job/config.json"),
    }
    assert all(mount["ReadOnly"] is True for mount in binds)
    (out,) = [mount for mount in mounts if mount["Type"] == "volume"]
    assert len(mounts) == len(binds) + 1
    assert out["Target"] == "/workspace/out"
    assert "Source" not in out  # anonymous, so it is removed with the container
    driver = out["VolumeOptions"]["DriverConfig"]
    assert driver["Name"] == "local"
    assert driver["Options"]["type"] == driver["Options"]["device"] == "tmpfs"
    assert driver["Options"]["o"].split(",") == [
        "size=536870912",
        "uid=10001",
        "gid=10001",
        "mode=0700",
        "nosuid",
        "nodev",
    ]


def test_nothing_from_the_executors_environment_reaches_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARP_GATEWAY_TOKEN", "not-for-the-sandbox")
    monkeypatch.setenv("ARP_DATABASE_URL", "postgresql://not-for-the-sandbox")
    assert spec()["Env"] == ["NVIDIA_DRIVER_CAPABILITIES=compute,utility"]


def test_one_gpu_by_index() -> None:
    assert spec()["HostConfig"]["DeviceRequests"] == [
        {"Driver": "", "Count": 0, "DeviceIDs": ["0"], "Capabilities": [["gpu"]]}
    ]


def test_labels_and_name_identify_the_job() -> None:
    assert spec()["Labels"] == {"arp.job": "j1", "arp.kind": "train", "arp.run": "r1"}
    assert container_name("j1") == "arp-job-j1"


@pytest.mark.parametrize(("kind", "dry_run"), [(GpuJobKind.SMOKE, True), (GpuJobKind.TRAIN, False)])
def test_jobs_run_through_harness_job_and_smoke_jobs_are_dry_runs(
    kind: GpuJobKind, dry_run: bool
) -> None:
    body = spec(kind)
    assert body["Entrypoint"] == ["python", "-m", "harness.job"]
    assert body["Cmd"][:4] == ["--config", "/job/config.json", "--out", "/workspace/out"]
    assert ("--dry-run" in body["Cmd"]) is dry_run
    assert body["Labels"]["arp.kind"] == kind.value
