"""Reading the jobs' GPU with nvidia-smi: the VRAM preflight and the queue page's telemetry."""

from __future__ import annotations

from agentic_executor.ports import GpuSample


class NvidiaSmi:
    """agentic_executor.ports.GpuProbe: one ``nvidia-smi --query-gpu`` per sample."""

    def __init__(
        self, executable: str = "nvidia-smi", *, device: str = "0", timeout_seconds: float = 5.0
    ) -> None:
        self.executable = executable
        self.device = device
        self.timeout_seconds = timeout_seconds

    async def sample(self) -> GpuSample | None:
        raise NotImplementedError
