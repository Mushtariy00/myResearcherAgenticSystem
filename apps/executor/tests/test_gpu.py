"""nvidia-smi readings: one CSV line becomes a GpuSample, and a missing, failing, hanging or
garbled nvidia-smi gives None with one warning. A shell script stands in for nvidia-smi."""

import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentic_executor.gpu import NvidiaSmi, parse_sample
from agentic_executor.ports import GpuSample

# This machine's real answer (a GTX 1060 under WSL).
GTX_1060 = "0, NVIDIA GeForce GTX 1060 6GB, 6144, 1010, 23, 34, 7.79, 120.00, 25"
QUERY = (
    "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,"
    "power.draw,power.limit,fan.speed"
)


def fake_smi(folder: Path, script: str) -> str:
    """An executable that records its arguments in ``folder/args``, then runs ``script``."""
    executable = folder / "nvidia-smi"
    executable.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{folder}/args"\n{script}\n')
    executable.chmod(0o755)
    return str(executable)


async def test_a_reading_of_the_jobs_gpu(tmp_path: Path) -> None:
    smi = NvidiaSmi(fake_smi(tmp_path, f"echo '{GTX_1060}'"), device="0")
    before = datetime.now(UTC)
    sample = await smi.sample()
    assert sample is not None
    assert sample == GpuSample(
        index=0,
        name="NVIDIA GeForce GTX 1060 6GB",
        memory_total_mb=6144,
        memory_used_mb=1010,
        utilization_percent=23,
        temperature_c=34,
        power_draw_w=7.79,
        power_limit_w=120.0,
        fan_percent=25,
        sampled_at=sample.sampled_at,
    )
    assert before <= sample.sampled_at <= datetime.now(UTC)
    assert sample.memory_free_mb == 5134
    args = (tmp_path / "args").read_text().splitlines()
    assert args == [QUERY, "--format=csv,noheader,nounits", "-i", "0"]


async def test_it_asks_for_its_own_device(tmp_path: Path) -> None:
    smi = NvidiaSmi(fake_smi(tmp_path, f"echo '{GTX_1060}'"), device="1")
    await smi.sample()
    assert (tmp_path / "args").read_text().splitlines()[-2:] == ["-i", "1"]


async def test_readings_the_gpu_does_not_give_are_none(tmp_path: Path) -> None:
    line = "0, NVIDIA GeForce GTX 1060 6GB, 6144, 1010, [N/A], 34, [Not Supported], N/A, [N/A]"
    sample = await NvidiaSmi(fake_smi(tmp_path, f"echo '{line}'")).sample()
    assert sample is not None
    assert (sample.memory_total_mb, sample.memory_used_mb, sample.temperature_c) == (6144, 1010, 34)
    assert sample.utilization_percent is None
    assert sample.power_draw_w is None
    assert sample.power_limit_w is None
    assert sample.fan_percent is None


async def test_a_failing_nvidia_smi_gives_none_and_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    smi = NvidiaSmi(fake_smi(tmp_path, "echo 'No devices were found'; exit 6"))
    with caplog.at_level(logging.WARNING, logger="agentic_executor.gpu"):
        assert await smi.sample() is None
        assert await smi.sample() is None
    assert len(caplog.messages) == 1
    assert "exited with 6: No devices were found" in caplog.messages[0]


async def test_a_missing_nvidia_smi_gives_none_and_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    smi = NvidiaSmi(str(tmp_path / "no-nvidia-smi-here"))
    with caplog.at_level(logging.WARNING, logger="agentic_executor.gpu"):
        assert await smi.sample() is None
        assert await smi.sample() is None
    assert len(caplog.messages) == 1
    assert "cannot run" in caplog.messages[0]


async def test_a_hanging_nvidia_smi_is_killed_at_the_timeout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pid_file = tmp_path / "pid"
    smi = NvidiaSmi(
        fake_smi(tmp_path, f'echo $$ > "{pid_file}"\nexec sleep 30'), timeout_seconds=0.3
    )
    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="agentic_executor.gpu"):
        assert await smi.sample() is None
    assert time.monotonic() - started < 5
    assert "gave no answer in 0.3 s" in caplog.text
    with pytest.raises(ProcessLookupError):  # killed and reaped, not left sleeping
        os.kill(int(pid_file.read_text()), 0)


async def test_garbled_output_gives_none(tmp_path: Path) -> None:
    assert await NvidiaSmi(fake_smi(tmp_path, "echo 'Segmentation fault'")).sample() is None


async def test_after_a_good_reading_a_new_failure_is_logged_again(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    flag = tmp_path / "fail"
    script = f"if [ -e '{flag}' ]; then exit 9; fi\necho '{GTX_1060}'"
    smi = NvidiaSmi(fake_smi(tmp_path, script))
    with caplog.at_level(logging.WARNING, logger="agentic_executor.gpu"):
        flag.touch()
        assert await smi.sample() is None
        flag.unlink()
        assert await smi.sample() is not None
        flag.touch()
        assert await smi.sample() is None
    assert len(caplog.messages) == 2


@pytest.mark.parametrize(
    "output",
    [
        "",
        "garbage",
        f"{GTX_1060}\n{GTX_1060}",  # two GPUs: -i should have picked one
        "0, NVIDIA GeForce GTX 1060 6GB, 6144, 1010",  # readings missing
        "0, , 6144, 1010, 23, 34, 7.79, 120.00, 25",  # no name
        "0, GTX 1060, [N/A], 1010, 23, 34, 7.79, 120.00, 25",  # no memory total
        "0, GTX 1060, 6144, [N/A], 23, 34, 7.79, 120.00, 25",  # no memory used
        "zero, GTX 1060, 6144, 1010, 23, 34, 7.79, 120.00, 25",
        "0, GTX 1060, 6144 MiB, 1010 MiB, 23 %, 34, 7.79 W, 120.00 W, 25 %",  # units
    ],
)
def test_anything_but_one_reading_is_none(output: str) -> None:
    assert parse_sample(output) is None


def test_a_name_with_a_comma_is_kept_whole() -> None:
    sample = parse_sample("0, Some GPU, Rev 2, 6144, 1010, 23, 34, 7.79, 120.00, 25\n")
    assert sample is not None
    assert (sample.name, sample.memory_total_mb, sample.fan_percent) == (
        "Some GPU, Rev 2",
        6144,
        25,
    )
