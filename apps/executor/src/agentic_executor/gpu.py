"""Reading the jobs' GPU with nvidia-smi: the VRAM preflight and the queue page's telemetry."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from agentic_executor.ports import GpuSample

logger = logging.getLogger(__name__)

# GpuSample's readings, in its order. With nounits: MiB, %, degrees C and W.
QUERY = (
    "index,name,memory.total,memory.used,utilization.gpu,temperature.gpu,"
    "power.draw,power.limit,fan.speed"
)
_READINGS_AFTER_NAME = 7
# What nvidia-smi prints for a reading this GPU or driver doesn't give, such as the fan speed
# of a passively cooled card or the power draw under WSL.
_NOT_AVAILABLE = frozenset({"N/A", "[N/A]", "[Not Supported]"})


class NvidiaSmi:
    """agentic_executor.ports.GpuProbe: one ``nvidia-smi --query-gpu`` per sample."""

    def __init__(
        self, executable: str = "nvidia-smi", *, device: str = "0", timeout_seconds: float = 5.0
    ) -> None:
        self.executable = executable
        self.device = device
        self.timeout_seconds = timeout_seconds
        self._last_problem: str | None = None

    async def sample(self) -> GpuSample | None:
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                f"--query-gpu={QUERY}",
                "--format=csv,noheader,nounits",
                "-i",
                self.device,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            return self._failed(f"cannot run {self.executable}: {exc}")
        try:
            async with asyncio.timeout(self.timeout_seconds):
                stdout, stderr = await process.communicate()
        except TimeoutError:
            # A wedged driver can leave nvidia-smi hanging for minutes.
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            return self._failed(f"{self.executable} gave no answer in {self.timeout_seconds} s")
        if process.returncode != 0:
            # nvidia-smi explains most failures on stdout ("No devices were found").
            detail = (stderr or stdout).decode(errors="replace").strip()[:300]
            return self._failed(f"{self.executable} exited with {process.returncode}: {detail}")
        sample = parse_sample(stdout.decode(errors="replace"))
        if sample is None:
            return self._failed(f"unreadable output from {self.executable}: {stdout[:300]!r}")
        self._last_problem = None
        return sample

    def _failed(self, problem: str) -> None:
        """Logs a problem once, not at every sample while it lasts."""
        if problem != self._last_problem:
            logger.warning("No GPU reading: %s", problem)
            self._last_problem = problem


def parse_sample(output: str, sampled_at: datetime | None = None) -> GpuSample | None:
    """The reading in ``output``, one CSV line of QUERY (noheader, nounits), or None when it is
    anything else. A reading nvidia-smi doesn't give is None, except the memory: without it the
    preflight can't decide, so the sample is None."""
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) < 2 + _READINGS_AFTER_NAME:
        return None
    # The name is the only free text; rejoin it should it hold a comma.
    index = fields[0]
    name = ", ".join(fields[1:-_READINGS_AFTER_NAME])
    total, used, utilization, temperature, draw, limit, fan = fields[-_READINGS_AFTER_NAME:]
    if not name:
        return None
    try:
        return GpuSample(
            index=int(index),
            name=name,
            memory_total_mb=int(total),
            memory_used_mb=int(used),
            utilization_percent=_optional_int(utilization),
            temperature_c=_optional_int(temperature),
            power_draw_w=_optional_float(draw),
            power_limit_w=_optional_float(limit),
            fan_percent=_optional_int(fan),
            sampled_at=sampled_at or datetime.now(UTC),
        )
    except ValueError:
        return None


def _optional_int(value: str) -> int | None:
    return None if value in _NOT_AVAILABLE else int(value)


def _optional_float(value: str) -> float | None:
    return None if value in _NOT_AVAILABLE else float(value)
